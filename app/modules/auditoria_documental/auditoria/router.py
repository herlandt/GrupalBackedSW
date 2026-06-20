"""Capa API (router) — submódulo auditoria (CU-10, RF-01, RF-02)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from app.core.database import DbDep
from app.core.enums import CategoriaObservacion, EstadoAnalisis
from app.core.internal_auth import RequireInternalToken
from app.integrations.analysis.port import AnalysisServiceError, AnalysisServicePort
from app.integrations.factory import get_analysis_service
from app.modules.administracion.suscripciones.dependencies import SuscripcionActiva
from app.modules.administracion.usuarios.dependencies import RequireEstudiante
from app.modules.auditoria_documental.auditoria.schemas import (
    EstadoAnalisisRead,
    ObservacionRead,
    ResultadoRead,
)
from app.modules.auditoria_documental.auditoria.service import AuditoriaService

router = APIRouter(prefix="/auditoria", tags=["auditoria"])


def get_auditoria_service(
    db: DbDep,
    analysis: Annotated[AnalysisServicePort, Depends(get_analysis_service)],
) -> AuditoriaService:
    return AuditoriaService(db, analysis)


ServiceDep = Annotated[AuditoriaService, Depends(get_auditoria_service)]


@router.get("/versiones/{version_id}/resultado", response_model=ResultadoRead)
async def obtener_resultado(
    version_id: int,
    service: ServiceDep,
    user: RequireEstudiante,
    _sub: SuscripcionActiva,
    categoria: Annotated[CategoriaObservacion | None, Query()] = None,
) -> ResultadoRead:
    resultado, observaciones = await service.obtener_resultado(version_id, user, categoria)
    return ResultadoRead(
        id=resultado.id,
        version_id=resultado.version_id,
        nivel_documento=resultado.nivel_documento,
        resumen=resultado.resumen,
        created_at=resultado.created_at,
        observaciones=[ObservacionRead.model_validate(o) for o in observaciones],
    )


@router.get("/versiones/{version_id}/estado", response_model=EstadoAnalisisRead)
async def estado_analisis(
    version_id: int, service: ServiceDep, user: RequireEstudiante, _sub: SuscripcionActiva
) -> EstadoAnalisisRead:
    estado = await service.estado(version_id, user)
    return EstadoAnalisisRead(
        version_id=version_id,
        estado_analisis=estado,
        tiene_resultado=estado == EstadoAnalisis.COMPLETADO,
    )


@router.post("/versiones/{version_id}/analizar", response_model=EstadoAnalisisRead)
async def analizar(
    version_id: int,
    service: ServiceDep,
    user: RequireEstudiante,
    _sub: SuscripcionActiva,
) -> EstadoAnalisisRead | JSONResponse:
    """CU-08: el estudiante dispara el análisis de su propia versión (idempotente)."""
    try:
        await service.analizar(version_id, user)
    except AnalysisServiceError:
        return JSONResponse(
            status_code=502, content={"detail": "El servicio de análisis no está disponible."}
        )
    return EstadoAnalisisRead(
        version_id=version_id,
        estado_analisis=EstadoAnalisis.COMPLETADO,
        tiene_resultado=True,
    )


# --- Endpoint interno (worker): procesa la versión encolada ---------------
# Protegido por secreto interno (no es un endpoint de usuario). Ante un fallo del
# servicio de análisis devolvemos una respuesta normal (no excepción) para que la
# sesión COMMITEE el estado ERROR en vez de revertirlo con el rollback de get_db.
@router.post("/internal/procesar/{version_id}", include_in_schema=False)
async def procesar_interno(
    version_id: int, service: ServiceDep, _token: RequireInternalToken
) -> JSONResponse:
    try:
        resultado = await service.procesar_version(version_id)
    except AnalysisServiceError:
        return JSONResponse(
            status_code=502, content={"status": "error", "version_id": version_id}
        )
    return JSONResponse(
        status_code=200, content={"status": "ok", "resultado_id": str(resultado.id)}
    )
