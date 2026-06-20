"""Acceso a datos del submódulo Suscripciones."""

from collections.abc import Sequence

from sqlalchemy import select

from app.core.enums import EstadoSuscripcion
from app.core.repository import BaseRepository
from app.modules.administracion.suscripciones.models import PlanSuscripcion, Suscripcion


class PlanRepository(BaseRepository[PlanSuscripcion]):
    model = PlanSuscripcion

    async def list_activos(self) -> Sequence[PlanSuscripcion]:
        result = await self.db.execute(
            select(PlanSuscripcion).where(PlanSuscripcion.activo.is_(True))
        )
        return result.scalars().all()


class SuscripcionRepository(BaseRepository[Suscripcion]):
    model = Suscripcion

    async def activa_de_usuario(self, usuario_id: int) -> Suscripcion | None:
        result = await self.db.execute(
            select(Suscripcion).where(
                Suscripcion.usuario_id == usuario_id,
                Suscripcion.estado == EstadoSuscripcion.ACTIVA,
            )
        )
        return result.scalars().first()

    async def activas_por_plan(self, plan_id: int) -> Sequence[Suscripcion]:
        result = await self.db.execute(
            select(Suscripcion).where(
                Suscripcion.plan_id == plan_id,
                Suscripcion.estado == EstadoSuscripcion.ACTIVA,
            )
        )
        return result.scalars().all()
