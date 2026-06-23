"""Acceso a datos — submódulo etica (CU-12)."""

from collections.abc import Sequence

from sqlalchemy import select

from app.core.enums import EstadoAlertaEtica
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

    async def documento_de_version(self, version_id: int) -> Documento | None:
        """El Documento al que pertenece la versión (para actualizar su estado ético)."""
        result = await self.db.execute(
            select(Documento)
            .join(VersionDocumento, VersionDocumento.documento_id == Documento.id)
            .where(VersionDocumento.id == version_id)
        )
        return result.scalar_one_or_none()

    async def estados_de_documento(self, documento_id: int) -> list[EstadoAlertaEtica]:
        """Estados de TODAS las alertas del documento (todas sus versiones).

        Permite derivar el estado ético de la tesis del conjunto, no de una sola alerta.
        """
        result = await self.db.execute(
            select(AlertaEtica.estado)
            .join(VersionDocumento, VersionDocumento.id == AlertaEtica.version_id)
            .where(VersionDocumento.documento_id == documento_id)
        )
        return list(result.scalars().all())

    async def existe_por_version_tipo(self, version_id: int, tipo: str) -> bool:
        """¿Ya hay una alerta de ese tipo para esa versión? (evita duplicados al reanalizar)."""
        result = await self.db.execute(
            select(AlertaEtica.id)
            .where(AlertaEtica.version_id == version_id, AlertaEtica.tipo == tipo)
            .limit(1)
        )
        return result.scalar_one_or_none() is not None
