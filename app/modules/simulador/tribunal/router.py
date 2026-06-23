"""Capa API (router) — submódulo tribunal (CU-16, CU-17, RF-06, RF-07)."""

from io import BytesIO
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from app.core.database import DbDep
from app.integrations.factory import get_transcription, get_tribunal_llm, get_tts
from app.integrations.llm.port import TribunalLLMPort
from app.integrations.transcription.port import TranscriptionPort
from app.integrations.tts.port import TTSPort, TTSServiceError
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
    transcripcion: Annotated[TranscriptionPort, Depends(get_transcription)],
) -> TribunalService:
    return TribunalService(db, llm, transcripcion)


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


@router.get("/preguntas/{pregunta_id}/voz")
async def voz_pregunta(
    pregunta_id: int,
    service: ServiceDep,
    tts: Annotated[TTSPort, Depends(get_tts)],
    user: RequireEstudiante,
    _sub: SuscripcionActiva,
) -> StreamingResponse:
    """Audio MP3 de la pregunta leída por el tribunal (Amazon Polly)."""
    pregunta = await service.obtener_pregunta(pregunta_id, user)
    try:
        audio = await tts.sintetizar(pregunta.texto)
    except TTSServiceError as exc:
        raise HTTPException(status_code=502, detail=f"No se pudo generar la voz: {exc}") from exc
    return StreamingResponse(BytesIO(audio), media_type="audio/mpeg")


@router.get("/sesiones/{sesion_id}/informe")
async def informe_tribunal(
    sesion_id: int,
    service: ServiceDep,
    user: RequireEstudiante,
    _sub: SuscripcionActiva,
) -> StreamingResponse:
    """CU-17: descarga el informe de evaluación del tribunal de la sesión en PDF."""
    contenido, filename = await service.informe_pdf(sesion_id, user)
    return StreamingResponse(
        BytesIO(contenido),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


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
    _respuesta, evaluacion = await service.responder(
        pregunta_id, user, data.texto, data.audio_url, data.atencion
    )
    return evaluacion


@router.post(
    "/preguntas/{pregunta_id}/timeout",
    response_model=EvaluacionRead,
    status_code=status.HTTP_201_CREATED,
)
async def registrar_timeout(
    pregunta_id: int,
    service: ServiceDep,
    user: RequireEstudiante,
    _sub: SuscripcionActiva,
) -> EvaluacionRespuesta:
    """CU-16 (excepción): se agotó el tiempo; registra la pregunta sin respuesta y avanza."""
    _respuesta, evaluacion = await service.registrar_sin_respuesta(pregunta_id, user)
    return evaluacion


@router.get("/preguntas/{pregunta_id}/evaluacion", response_model=EvaluacionRead)
async def obtener_evaluacion(
    pregunta_id: int,
    service: ServiceDep,
    user: RequireEstudiante,
    _sub: SuscripcionActiva,
) -> EvaluacionRespuesta:
    return await service.obtener_evaluacion(pregunta_id, user)
