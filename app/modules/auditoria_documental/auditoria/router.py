"""Capa API (router) — submódulo auditoria (CU-10, RF-01, RF-02)."""

import asyncio
import logging
from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from app.core.database import DbDep, SessionLocal
from app.core.enums import CategoriaObservacion, EstadoAnalisis
from app.core.exceptions import BusinessRuleError, ResourceNotFoundError
from app.core.internal_auth import RequireInternalToken
from app.integrations.analysis.port import AnalysisServiceError, AnalysisServicePort
from app.integrations.email.port import EmailPort
from app.integrations.factory import get_analysis_service, get_email_port
from app.modules.administracion.suscripciones.dependencies import SuscripcionActiva
from app.modules.administracion.usuarios.dependencies import RequireEstudiante
from app.modules.auditoria_documental.auditoria.schemas import (
    EstadoAnalisisRead,
    ObservacionRead,
    ResultadoRead,
)
from app.modules.auditoria_documental.auditoria.service import AuditoriaService
from app.modules.auditoria_documental.etica.service import EticaService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auditoria", tags=["auditoria"])


async def _procesar_en_segundo_plano(version_id: int) -> None:
    """Ejecuta el análisis FUERA del ciclo de la petición, con su propia sesión de DB.

    Así el trabajo vive en el servidor y NO se corta si el usuario cambia de pestaña o
    navega a otra pantalla; el front consulta GET /estado para saber cuándo termina.
    """
    logger.info("Análisis 2º plano: inicio (versión %s)", version_id)
    async with SessionLocal() as db:
        # CU-12: el worker abre por sí mismo las alertas de ética detectadas (notifica por
        # correo); por eso lleva un EticaService con el puerto de email real.
        etica = EticaService(db, get_email_port())
        service = AuditoriaService(db, get_analysis_service(), etica)
        try:
            await service.procesar_version(version_id)
            await db.commit()
            logger.info("Análisis 2º plano: COMPLETADO (versión %s)", version_id)
        except AnalysisServiceError:
            await db.commit()  # procesar_version ya marcó ERROR; persistirlo
            logger.warning("Análisis 2º plano: falló el análisis (versión %s)", version_id)
        except (BusinessRuleError, ResourceNotFoundError) as exc:
            await db.rollback()
            logger.info("Análisis 2º plano: omitido (versión %s): %s", version_id, exc)
        except Exception:
            await db.rollback()
            logger.exception("Análisis 2º plano: error inesperado (versión %s)", version_id)


# Mantiene viva la referencia a las tareas de fondo (asyncio podría recolectarlas si no).
_tareas_fondo: set[asyncio.Task[None]] = set()


def _encolar_procesamiento(version_id: int) -> None:
    """Lanza el análisis como tarea de fondo (fire-and-forget) en el event loop."""
    tarea = asyncio.create_task(_procesar_en_segundo_plano(version_id))
    _tareas_fondo.add(tarea)
    tarea.add_done_callback(_tareas_fondo.discard)


def get_auditoria_service(
    db: DbDep,
    analysis: Annotated[AnalysisServicePort, Depends(get_analysis_service)],
    email: Annotated[EmailPort, Depends(get_email_port)],
) -> AuditoriaService:
    return AuditoriaService(db, analysis, EticaService(db, email))


ServiceDep = Annotated[AuditoriaService, Depends(get_auditoria_service)]


def get_encolar_analisis() -> Callable[[int], None]:
    """Encolador del análisis en 2º plano. Es una dependencia para poder sustituirlo por
    un no-op en tests (la tarea de fondo abre su propia sesión y se saltaría el aislamiento)."""
    return _encolar_procesamiento


EncolarAnalisisDep = Annotated[Callable[[int], None], Depends(get_encolar_analisis)]


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
        comparacion=resultado.comparacion,
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
    encolar: EncolarAnalisisDep,
    user: RequireEstudiante,
    _sub: SuscripcionActiva,
) -> EstadoAnalisisRead:
    """CU-08: dispara el análisis EN SEGUNDO PLANO y responde de inmediato.

    No bloquea ni se corta si el usuario cambia de pestaña; el cliente consulta
    GET /versiones/{id}/estado para saber cuándo termina. Idempotente: si ya hay
    resultado devuelve COMPLETADO, y si ya hay un análisis en curso no lo duplica.
    """
    estado, debe_encolar = await service.solicitar_analisis(version_id, user)
    if debe_encolar:
        encolar(version_id)
    return EstadoAnalisisRead(
        version_id=version_id,
        estado_analisis=estado,
        tiene_resultado=estado == EstadoAnalisis.COMPLETADO,
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
