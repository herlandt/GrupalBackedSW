"""Capa API — submódulo documentos (CU-08, CU-09, CU-11)."""

from collections.abc import Sequence
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile, status

from app.core.database import DbDep
from app.integrations.analysis.port import AnalysisQueuePort
from app.integrations.factory import get_analysis_queue, get_storage_port
from app.integrations.storage.port import StoragePort
from app.modules.administracion.suscripciones.dependencies import require_suscripcion_activa
from app.modules.administracion.usuarios.dependencies import RequireEstudiante
from app.modules.auditoria_documental.documentos.models import Documento, VersionDocumento
from app.modules.auditoria_documental.documentos.schemas import DocumentoRead, VersionRead
from app.modules.auditoria_documental.documentos.service import DocumentoService

# Gating de pago aplicado a todo el router (devuelve 402 si no hay suscripción activa).
router = APIRouter(
    prefix="/documentos",
    tags=["documentos"],
    dependencies=[Depends(require_suscripcion_activa)],
)


def get_documento_service(
    db: DbDep,
    storage: Annotated[StoragePort, Depends(get_storage_port)],
    queue: Annotated[AnalysisQueuePort, Depends(get_analysis_queue)],
) -> DocumentoService:
    return DocumentoService(db, storage, queue)


ServiceDep = Annotated[DocumentoService, Depends(get_documento_service)]


@router.post("", response_model=VersionRead, status_code=status.HTTP_201_CREATED)
async def subir_documento(
    user: RequireEstudiante,
    service: ServiceDep,
    titulo: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
) -> VersionDocumento:
    content = await file.read()
    return await service.subir_documento(
        usuario_id=user.id,
        titulo=titulo,
        filename=file.filename or "documento",
        content=content,
        content_type=file.content_type or "application/octet-stream",
    )


@router.post(
    "/{documento_id}/versiones",
    response_model=VersionRead,
    status_code=status.HTTP_201_CREATED,
)
async def subir_version(
    documento_id: int,
    user: RequireEstudiante,
    service: ServiceDep,
    file: Annotated[UploadFile, File()],
) -> VersionDocumento:
    content = await file.read()
    return await service.subir_version(
        usuario_id=user.id,
        documento_id=documento_id,
        filename=file.filename or "documento",
        content=content,
        content_type=file.content_type or "application/octet-stream",
    )


@router.get("", response_model=list[DocumentoRead])
async def listar_documentos(user: RequireEstudiante, service: ServiceDep) -> Sequence[Documento]:
    return await service.listar_documentos(user.id)


@router.get("/{documento_id}/versiones", response_model=list[VersionRead])
async def historial_versiones(
    documento_id: int, user: RequireEstudiante, service: ServiceDep
) -> Sequence[VersionDocumento]:
    return await service.historial_versiones(usuario_id=user.id, documento_id=documento_id)
