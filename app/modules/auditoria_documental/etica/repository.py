"""Acceso a datos — submódulo etica (CU-12)."""

from collections.abc import Sequence

from sqlalchemy import select

from app.core.repository import BaseRepository
from app.modules.auditoria_documental.documentos.models import Documento, VersionDocumento
from app.modules.auditoria_documental.etica.models import AlertaEtica


class AlertaEticaRepository(BaseRepository[AlertaEtica]):
    model = AlertaEtica

    async def listar_todas(self) -> Sequence[AlertaEtica]:
        result = await self.db.execute(
            select(AlertaEtica).order_by(AlertaEtica.created_at.desc())
        )
        return result.scalars().all()

    async def por_estudiante(self, usuario_id: int) -> Sequence[AlertaEtica]:
        """Alertas de versiones de documentos cuyo dueño es `usuario_id`."""
        result = await self.db.execute(
            select(AlertaEtica)
            .join(VersionDocumento, VersionDocumento.id == AlertaEtica.version_id)
            .join(Documento, Documento.id == VersionDocumento.documento_id)
            .where(Documento.usuario_id == usuario_id)
            .order_by(AlertaEtica.created_at.desc())
        )
        return result.scalars().all()

    async def dueno_de_version(self, version_id: int) -> int | None:
        """usuario_id dueño del documento al que pertenece la versión (o None)."""
        result = await self.db.execute(
            select(Documento.usuario_id)
            .join(VersionDocumento, VersionDocumento.documento_id == Documento.id)
            .where(VersionDocumento.id == version_id)
        )
        return result.scalar_one_or_none()
