"""Acceso a datos — submódulo auditoria (CU-10, RF-01, RF-02)."""

from collections.abc import Sequence

from sqlalchemy import select

from app.core.enums import CategoriaObservacion
from app.core.repository import BaseRepository
from app.modules.auditoria_documental.auditoria.models import (
    Observacion,
    ResultadoAuditoria,
)


class ResultadoRepository(BaseRepository[ResultadoAuditoria]):
    model = ResultadoAuditoria

    async def por_version(self, version_id: int) -> ResultadoAuditoria | None:
        result = await self.db.execute(
            select(ResultadoAuditoria).where(ResultadoAuditoria.version_id == version_id)
        )
        return result.scalar_one_or_none()


class ObservacionRepository(BaseRepository[Observacion]):
    model = Observacion

    async def por_resultado(
        self, resultado_id: int, categoria: CategoriaObservacion | None = None
    ) -> Sequence[Observacion]:
        stmt = select(Observacion).where(Observacion.resultado_id == resultado_id)
        if categoria is not None:
            stmt = stmt.where(Observacion.categoria == categoria)
        result = await self.db.execute(stmt.order_by(Observacion.id))
        return result.scalars().all()
