"""Acceso a datos del submódulo Pagos."""

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import select

from app.core.enums import EstadoPago
from app.core.repository import BaseRepository
from app.modules.administracion.pagos.models import EventoWebhook, Pago


class PagoRepository(BaseRepository[Pago]):
    model = Pago

    async def por_usuario(
        self,
        usuario_id: int,
        *,
        desde: datetime | None = None,
        hasta: datetime | None = None,
        estado: EstadoPago | None = None,
    ) -> Sequence[Pago]:
        """Pagos del usuario (CU-04). `desde`/`hasta`/`estado` filtran opcionalmente."""
        stmt = select(Pago).where(Pago.usuario_id == usuario_id)
        if desde is not None:
            stmt = stmt.where(Pago.created_at >= desde)
        if hasta is not None:
            stmt = stmt.where(Pago.created_at <= hasta)
        if estado is not None:
            stmt = stmt.where(Pago.estado == estado)
        result = await self.db.execute(stmt.order_by(Pago.created_at.desc()))
        return result.scalars().all()

    async def por_sesion(self, session_id: str) -> Pago | None:
        result = await self.db.execute(
            select(Pago).where(Pago.stripe_checkout_session_id == session_id)
        )
        return result.scalar_one_or_none()


class WebhookRepository(BaseRepository[EventoWebhook]):
    model = EventoWebhook

    async def ya_procesado(self, stripe_event_id: str) -> bool:
        result = await self.db.execute(
            select(EventoWebhook.id).where(EventoWebhook.stripe_event_id == stripe_event_id)
        )
        return result.first() is not None

    async def registrar(self, stripe_event_id: str, tipo: str, pago_id: int | None) -> None:
        self.db.add(EventoWebhook(stripe_event_id=stripe_event_id, tipo=tipo, pago_id=pago_id))
        await self.db.flush()
