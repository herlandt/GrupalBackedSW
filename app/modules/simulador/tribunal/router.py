"""Capa API (router) — submódulo tribunal (CU-16, CU-17, RF-06, RF-07)."""

from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.core.database import DbDep
from app.integrations.factory import get_tribunal_llm
from app.integrations.llm.port import TribunalLLMPort
from app.modules.administracion.suscripciones.dependencies import SuscripcionActiva
from app.modules.administracion.usuarios.dependencies import RequireEstudiante
from app.modules.simulador.tribunal.models import (
    EvaluacionRespuesta,
    PreguntaTribunal,
)
from app.modules.simulador.tribunal.schemas import (
    EvaluacionRead,
    PreguntaRead,
    RespuestaCreate,
)
from app.modules.simulador.tribunal.service import TribunalService

router = APIRouter(prefix="/tribunal", tags=["tribunal"])


def get_tribunal_service(
    db: DbDep,
    llm: Annotated[TribunalLLMPort, Depends(get_tribunal_llm)],
) -> TribunalService:
    return TribunalService(db, llm)


ServiceDep = Annotated[TribunalService, Depends(get_tribunal_service)]


@router.post(
    "/sesiones/{sesion_id}/preguntas",
    response_model=list[PreguntaRead],
    status_code=status.HTTP_201_CREATED,
)
async def generar_preguntas(
    sesion_id: int,
    service: ServiceDep,
    user: RequireEstudiante,
    _sub: SuscripcionActiva,
) -> list[PreguntaTribunal]:
    return list(await service.generar_preguntas(sesion_id, user))


@router.get("/sesiones/{sesion_id}/preguntas", response_model=list[PreguntaRead])
async def listar_preguntas(
    sesion_id: int,
    service: ServiceDep,
    user: RequireEstudiante,
    _sub: SuscripcionActiva,
) -> list[PreguntaTribunal]:
    return list(await service.listar_preguntas(sesion_id, user))


@router.post(
    "/preguntas/{pregunta_id}/respuesta",
    response_model=EvaluacionRead,
    status_code=status.HTTP_201_CREATED,
)
async def responder(
    pregunta_id: int,
    data: RespuestaCreate,
    service: ServiceDep,
    user: RequireEstudiante,
    _sub: SuscripcionActiva,
) -> EvaluacionRespuesta:
    _respuesta, evaluacion = await service.responder(pregunta_id, user, data.texto, data.audio_url)
    return evaluacion


@router.get("/preguntas/{pregunta_id}/evaluacion", response_model=EvaluacionRead)
async def obtener_evaluacion(
    pregunta_id: int,
    service: ServiceDep,
    user: RequireEstudiante,
    _sub: SuscripcionActiva,
) -> EvaluacionRespuesta:
    return await service.obtener_evaluacion(pregunta_id, user)
