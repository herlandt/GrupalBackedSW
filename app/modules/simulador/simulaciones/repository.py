"""Acceso a datos — submódulo simulaciones (CU-13, CU-15)."""

from collections.abc import Sequence

from sqlalchemy import select

from app.core.enums import EstadoSesion
from app.core.repository import BaseRepository
from app.modules.simulador.simulaciones.models import SesionSimulacion


class SesionSimulacionRepository(BaseRepository[SesionSimulacion]):
    model = SesionSimulacion

    async def por_usuario(self, usuario_id: int) -> Sequence[SesionSimulacion]:
        """Historial (CU-15): sesiones del estudiante, más recientes primero."""
        result = await self.db.execute(
            select(SesionSimulacion)
            .where(SesionSimulacion.usuario_id == usuario_id)
            .order_by(SesionSimulacion.fecha_inicio.desc())
        )
        return result.scalars().all()

    async def tiene_en_curso(self, usuario_id: int) -> bool:
        """¿El estudiante ya tiene una simulación EN_CURSO? (evita acumular sesiones)."""
        result = await self.db.execute(
            select(SesionSimulacion.id)
            .where(
                SesionSimulacion.usuario_id == usuario_id,
                SesionSimulacion.estado == EstadoSesion.EN_CURSO,
            )
            .limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def get_de_usuario(
        self, sesion_id: int, usuario_id: int
    ) -> SesionSimulacion | None:
        """Una sesión concreta SOLO si pertenece al usuario (anti-IDOR)."""
        result = await self.db.execute(
            select(SesionSimulacion).where(
                SesionSimulacion.id == sesion_id,
                SesionSimulacion.usuario_id == usuario_id,
            )
        )
        return result.scalar_one_or_none()
