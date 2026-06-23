"""Lógica de negocio del submódulo Pagos (CU-03 pago, CU-04 historial)."""

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit.service import AuditService
from app.core.config import settings
from app.core.enums import EstadoPago, EstadoSuscripcion
from app.core.exceptions import BusinessRuleError
from app.integrations.email.port import EmailPort
from app.integrations.payments.port import PaymentGatewayPort
from app.modules.administracion.pagos.models import Pago
from app.modules.administracion.pagos.repository import PagoRepository, WebhookRepository
from app.modules.administracion.suscripciones.models import Suscripcion
from app.modules.administracion.suscripciones.repository import (
    PlanRepository,
    SuscripcionRepository,
)
from app.modules.administracion.usuarios.models import Usuario
from app.modules.administracion.usuarios.repository import UsuarioRepository


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class PagoService:
    def __init__(self, db: AsyncSession, gateway: PaymentGatewayPort, email: EmailPort) -> None:
        self.db = db
        self.pagos = PagoRepository(db)
        self.webhooks = WebhookRepository(db)
        self.planes = PlanRepository(db)
        self.suscripciones = SuscripcionRepository(db)
        self.usuarios = UsuarioRepository(db)
        self.audit = AuditService(db)
        self.gateway = gateway
        self.email = email

    async def iniciar_checkout(self, usuario: Usuario, plan_id: int) -> str:
        """Crea la suscripción y el pago en estado PENDIENTE y devuelve la URL de pago."""
        if await self.suscripciones.activa_de_usuario(usuario.id) is not None:
            raise BusinessRuleError("Ya tienes una suscripción activa")
        plan = await self.planes.get_or_404(plan_id)
        if not plan.activo:
            raise BusinessRuleError("El plan no está disponible")

        suscripcion = Suscripcion(
            usuario_id=usuario.id, plan_id=plan.id, estado=EstadoSuscripcion.PENDIENTE
        )
        await self.suscripciones.add(suscripcion)
        pago = Pago(
            usuario_id=usuario.id,
            suscripcion_id=suscripcion.id,
            plan_id=plan.id,
            monto=plan.precio,
            moneda=plan.moneda,
            estado=EstadoPago.PENDIENTE,
        )
        await self.pagos.add(pago)

        session = await self.gateway.create_checkout_session(
            amount_cents=int(plan.precio * 100),
            currency=plan.moneda.lower(),
            metadata={"pago_id": str(pago.id), "plan_nombre": plan.nombre},
            success_url=settings.stripe_success_url,
            cancel_url=settings.stripe_cancel_url,
        )
        pago.stripe_checkout_session_id = session.id
        await self.db.flush()
        return session.url

    async def procesar_webhook(self, payload: bytes, sig_header: str) -> None:
        event = await self.gateway.parse_webhook_event(payload, sig_header)
        if await self.webhooks.ya_procesado(event.id):
            return  # idempotencia: Stripe reintenta

        pago = (
            await self.pagos.por_sesion(event.checkout_session_id)
            if event.checkout_session_id
            else None
        )
        await self.webhooks.registrar(event.id, event.type, pago.id if pago else None)
        if pago is None:
            return

        if event.type == "checkout.session.completed":
            await self._activar(pago.id, event.payment_intent_id)
        elif event.type in ("checkout.session.expired", "payment_intent.payment_failed"):
            await self._marcar_fallido(pago.id)

    async def _activar(self, pago_id: int, payment_intent_id: str | None) -> None:
        pago = await self.pagos.get(pago_id)
        if pago is None or pago.estado == EstadoPago.PAGADO:
            return
        pago.estado = EstadoPago.PAGADO
        pago.stripe_payment_intent_id = payment_intent_id

        plan = await self.planes.get(pago.plan_id)
        suscripcion = (
            await self.suscripciones.get(pago.suscripcion_id) if pago.suscripcion_id else None
        )
        if plan is not None and suscripcion is not None:
            inicio = _now()
            suscripcion.estado = EstadoSuscripcion.ACTIVA
            suscripcion.fecha_inicio = inicio
            suscripcion.fecha_fin = inicio + timedelta(days=plan.periodo_dias)
        await self.db.flush()

        usuario = await self.usuarios.get(pago.usuario_id)
        if usuario is not None:
            await self.email.send(
                to=usuario.email,
                subject="Pago confirmado — TesisGuard",
                body="Tu pago fue recibido y tu suscripción está activa. ¡Gracias!",
            )
        await self.audit.log(
            actor_id=pago.usuario_id, accion="PAGO_COMPLETADO", entidad="pago", entidad_id=pago.id
        )

    async def _marcar_fallido(self, pago_id: int) -> None:
        pago = await self.pagos.get(pago_id)
        if pago is not None and pago.estado == EstadoPago.PENDIENTE:
            pago.estado = EstadoPago.FALLIDO
            await self.db.flush()
            await self.audit.log(
                actor_id=pago.usuario_id,
                accion="PAGO_FALLIDO",
                entidad="pago",
                entidad_id=pago.id,
            )

    async def confirmar_pago(self, usuario: Usuario, session_id: str) -> Suscripcion | None:
        """Verifica el pago contra la pasarela al volver del checkout y activa la
        suscripción si ya está pagado (no depende del webhook). Idempotente."""
        pago = await self.pagos.por_sesion(session_id)
        if pago is None or pago.usuario_id != usuario.id:
            return None
        if pago.estado != EstadoPago.PAGADO:
            estado = await self.gateway.retrieve_checkout_session(session_id)
            if estado.payment_status == "paid":
                await self._activar(pago.id, estado.payment_intent_id)
        if pago.suscripcion_id is None:
            return None
        suscripcion = await self.suscripciones.get(pago.suscripcion_id)
        return (
            suscripcion if suscripcion and suscripcion.estado == EstadoSuscripcion.ACTIVA else None
        )

    async def mi_suscripcion(self, usuario: Usuario) -> Suscripcion | None:
        return await self.suscripciones.activa_de_usuario(usuario.id)

    async def historial(
        self,
        usuario: Usuario,
        *,
        desde: datetime | None = None,
        hasta: datetime | None = None,
        estado: EstadoPago | None = None,
    ) -> Sequence[Pago]:
        return await self.pagos.por_usuario(
            usuario.id, desde=desde, hasta=hasta, estado=estado
        )
