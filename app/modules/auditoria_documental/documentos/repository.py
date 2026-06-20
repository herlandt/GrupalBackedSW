"""Acceso a datos — submódulo documentos (CU-08, CU-09, CU-11)."""

from collections.abc import Sequence

from sqlalchemy import func, select

from app.core.repository import BaseRepository
from app.modules.auditoria_documental.documentos.models import Documento, VersionDocumento


class DocumentoRepository(BaseRepository[Documento]):
    model = Documento

    async def por_usuario(self, usuario_id: int) -> Sequence[Documento]:
        result = await self.db.execute(
            select(Documento)
            .where(Documento.usuario_id == usuario_id)
            .order_by(Documento.created_at.desc())
        )
        return result.scalars().all()


class VersionRepository(BaseRepository[VersionDocumento]):
    model = VersionDocumento

    async def por_documento(self, documento_id: int) -> Sequence[VersionDocumento]:
        result = await self.db.execute(
            select(VersionDocumento)
            .where(VersionDocumento.documento_id == documento_id)
            .order_by(VersionDocumento.numero_version.desc())
        )
        return result.scalars().all()

    async def ultimo_numero(self, documento_id: int) -> int:
        """Devuelve el mayor numero_version del documento (0 si no hay ninguna)."""
        result = await self.db.execute(
            select(func.coalesce(func.max(VersionDocumento.numero_version), 0)).where(
                VersionDocumento.documento_id == documento_id
            )
        )
        return int(result.scalar_one())
