"""Lógica de negocio del submódulo Suscripciones (CU-02)."""

from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit.service import AuditService
from app.integrations.email.port import EmailPort
from app.modules.administracion.notificaciones.models import NotificacionUsuario
from app.modules.administracion.suscripciones.models import PlanSuscripcion
from app.modules.administracion.suscripciones.repository import (
    PlanRepository,
    SuscripcionRepository,
)
from app.modules.administracion.suscripciones.schemas import PlanCreate, PlanUpdate
from app.modules.administracion.usuarios.repository import UsuarioRepository


class SuscripcionService:
    def __init__(self, db: AsyncSession, email: EmailPort) -> None:
        self.db = db
        self.planes = PlanRepository(db)
        self.suscripciones = SuscripcionRepository(db)
        self.usuarios = UsuarioRepository(db)
        self.audit = AuditService(db)
        self.email = email

    async def listar_planes(self, *, solo_activos: bool = True) -> Sequence[PlanSuscripcion]:
        if solo_activos:
            return await self.planes.list_activos()
        return await self.planes.list()

    async def crear_plan(self, data: PlanCreate, actor_id: int) -> PlanSuscripcion:
        plan = PlanSuscripcion(
            nombre=data.nombre,
            precio=data.precio,
            moneda=data.moneda,
            periodo_dias=data.periodo_dias,
            activo=True,
        )
        await self.planes.add(plan)
        await self.audit.log(
            actor_id=actor_id, accion="PLAN_CREADO", entidad="plan_suscripcion", entidad_id=plan.id
        )
        return plan

    async def actualizar_plan(
        self, plan_id: int, data: PlanUpdate, actor_id: int
    ) -> PlanSuscripcion:
        plan = await self.planes.get_or_404(plan_id)
        precio_anterior = plan.precio
        if data.nombre is not None:
            plan.nombre = data.nombre
        if data.precio is not None:
            plan.precio = data.precio
        if data.periodo_dias is not None:
            plan.periodo_dias = data.periodo_dias
        if data.activo is not None:
            plan.activo = data.activo
        await self.db.flush()

        if data.precio is not None and data.precio != precio_anterior:
            await self._notificar_cambio_tarifa(plan)
            await self.audit.log(
                actor_id=actor_id,
                accion="TARIFA_MODIFICADA",
                entidad="plan_suscripcion",
                entidad_id=plan.id,
                metadata={"anterior": str(precio_anterior), "nuevo": str(plan.precio)},
            )
        else:
            await self.audit.log(
                actor_id=actor_id,
                accion="PLAN_ACTUALIZADO",
                entidad="plan_suscripcion",
                entidad_id=plan.id,
            )
        return plan

    async def _notificar_cambio_tarifa(self, plan: PlanSuscripcion) -> None:
        """Avisa a los usuarios con suscripción activa por DOS canales (CU-02 postcond.):
        correo y notificación EN EL SISTEMA (in-app)."""
        cuerpo = (
            f"La tarifa de tu plan '{plan.nombre}' cambió a {plan.precio} {plan.moneda}."
        )
        for suscripcion in await self.suscripciones.activas_por_plan(plan.id):
            usuario = await self.usuarios.get(suscripcion.usuario_id)
            if usuario is not None:
                await self.email.send(
                    to=usuario.email, subject="Cambio de tarifa — TesisGuard", body=cuerpo
                )
                self.db.add(
                    NotificacionUsuario(
                        usuario_id=usuario.id, titulo="Cambio de tarifa de tu plan", cuerpo=cuerpo
                    )
                )
        await self.db.flush()
