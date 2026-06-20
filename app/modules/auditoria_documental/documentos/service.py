"""Lógica de negocio — submódulo documentos (CU-08, CU-09, CU-11)."""

from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit.service import AuditService
from app.core.enums import EstadoAnalisis, FormatoDocumento
from app.core.exceptions import BusinessRuleError, ResourceNotFoundError
from app.integrations.analysis.port import AnalysisQueuePort
from app.integrations.storage.port import StoragePort
from app.modules.auditoria_documental.documentos.models import Documento, VersionDocumento
from app.modules.auditoria_documental.documentos.repository import (
    DocumentoRepository,
    VersionRepository,
)

# 20 MB. Límite defensivo (también conviene limitarlo en el proxy/servidor).
MAX_TAMANO_BYTES = 20 * 1024 * 1024

# Formato permitido -> content-type esperado.
_FORMATOS: dict[FormatoDocumento, set[str]] = {
    FormatoDocumento.PDF: {"application/pdf"},
    FormatoDocumento.DOCX: {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    },
}
_EXTENSIONES: dict[str, FormatoDocumento] = {
    ".pdf": FormatoDocumento.PDF,
    ".docx": FormatoDocumento.DOCX,
}


def _detectar_formato(filename: str, content_type: str) -> FormatoDocumento:
    """Determina DOCX/PDF por extensión y verifica el content-type. 409 si no es válido."""
    nombre = filename.lower()
    formato = next((f for ext, f in _EXTENSIONES.items() if nombre.endswith(ext)), None)
    if formato is None:
        raise BusinessRuleError("Formato no soportado: solo se aceptan archivos DOCX o PDF")
    # El content-type es una pista; algunos navegadores envían octet-stream.
    if content_type and content_type not in _FORMATOS[formato] | {"application/octet-stream"}:
        raise BusinessRuleError("El contenido del archivo no coincide con su extensión")
    return formato


class DocumentoService:
    def __init__(
        self, db: AsyncSession, storage: StoragePort, queue: AnalysisQueuePort
    ) -> None:
        self.db = db
        self.documentos = DocumentoRepository(db)
        self.versiones = VersionRepository(db)
        self.audit = AuditService(db)
        self.storage = storage
        self.queue = queue

    async def subir_documento(
        self, *, usuario_id: int, titulo: str, filename: str, content: bytes, content_type: str
    ) -> VersionDocumento:
        """CU-08: crea Documento + VersionDocumento(numero_version=1) y encola el análisis."""
        formato = _detectar_formato(filename, content_type)
        self._validar_tamano(content)

        documento = Documento(usuario_id=usuario_id, titulo=titulo.strip() or "Sin título")
        await self.documentos.add(documento)  # flush -> documento.id

        version = await self._crear_version(
            documento, numero=1, filename=filename, content=content,
            content_type=content_type, formato=formato,
        )
        await self.audit.log(
            actor_id=usuario_id, accion="DOCUMENTO_SUBIDO",
            entidad="documento", entidad_id=documento.id,
        )
        return version

    async def subir_version(
        self, *, usuario_id: int, documento_id: int, filename: str,
        content: bytes, content_type: str,
    ) -> VersionDocumento:
        """CU-09: incrementa numero_version sobre un documento del usuario y encola."""
        documento = await self.documentos.get_or_404(documento_id)
        if documento.usuario_id != usuario_id:
            raise ResourceNotFoundError(f"Documento {documento_id} no existe")
        formato = _detectar_formato(filename, content_type)
        self._validar_tamano(content)

        siguiente = await self.versiones.ultimo_numero(documento_id) + 1
        version = await self._crear_version(
            documento, numero=siguiente, filename=filename, content=content,
            content_type=content_type, formato=formato,
        )
        await self.audit.log(
            actor_id=usuario_id, accion="VERSION_SUBIDA",
            entidad="version_documento", entidad_id=version.id,
        )
        return version

    async def listar_documentos(self, usuario_id: int) -> Sequence[Documento]:
        """CU-11: documentos del estudiante."""
        return await self.documentos.por_usuario(usuario_id)

    async def historial_versiones(
        self, *, usuario_id: int, documento_id: int
    ) -> Sequence[VersionDocumento]:
        """CU-11: versiones de un documento (validando que sea del usuario)."""
        documento = await self.documentos.get_or_404(documento_id)
        if documento.usuario_id != usuario_id:
            raise ResourceNotFoundError(f"Documento {documento_id} no existe")
        return await self.versiones.por_documento(documento_id)

    # -- internos --

    def _validar_tamano(self, content: bytes) -> None:
        if not content:
            raise BusinessRuleError("El archivo está vacío")
        if len(content) > MAX_TAMANO_BYTES:
            raise BusinessRuleError("El archivo supera el tamaño máximo permitido (20 MB)")

    async def _crear_version(
        self, documento: Documento, *, numero: int, filename: str,
        content: bytes, content_type: str, formato: FormatoDocumento,
    ) -> VersionDocumento:
        key = f"documentos/{documento.id}/v{numero}/{filename}"
        url = await self.storage.save(key=key, data=content, content_type=content_type)
        version = VersionDocumento(
            documento_id=documento.id,
            numero_version=numero,
            archivo_url=url,
            formato=formato,
            estado_analisis=EstadoAnalisis.PENDIENTE,
        )
        await self.versiones.add(version)  # flush -> version.id
        await self.queue.enqueue_analysis(documento_id=documento.id, version_id=version.id)
        return version
