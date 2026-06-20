"""Capa API (router) — submódulo biometrico (CU-14, RF-03/04/05).

Expone los endpoints HTTP y delega al service. Sin lógica de negocio.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, File, UploadFile, status
from fastapi.responses import JSONResponse

from app.core.database import DbDep
from app.integrations.biometric.port import BiometricServiceError, BiometricServicePort
from app.integrations.factory import get_biometric_service
from app.modules.administracion.suscripciones.dependencies import SuscripcionActiva
from app.modules.administracion.usuarios.dependencies import RequireEstudiante
from app.modules.simulador.biometrico.audio_ws import audio_streaming
from app.modules.simulador.biometrico.schemas import (
    MetricaRead,
    ResumenBiometrico,
    SegmentoIn,
)
from app.modules.simulador.biometrico.service import BiometricoService
from app.modules.simulador.biometrico.video_ws import video_streaming

router = APIRouter(prefix="/biometrico", tags=["biometrico"])

# Análisis EN VIVO por WebSocket (auth como ?token=<JWT>, pues el handshake del navegador
# no admite cabeceras): audio → Transcribe Streaming (RF-05); video → Rekognition por frame
# (RF-04). La IA evaluadora decide al final con las métricas agregadas.
router.add_api_websocket_route("/sesiones/{sesion_id}/audio", audio_streaming)
router.add_api_websocket_route("/sesiones/{sesion_id}/video", video_streaming)


def get_biometrico_service(
    db: DbDep,
    biometric: Annotated[BiometricServicePort, Depends(get_biometric_service)],
) -> BiometricoService:
    return BiometricoService(db, biometric)


ServiceDep = Annotated[BiometricoService, Depends(get_biometrico_service)]


@router.post(
    "/sesiones/{sesion_id}/segmentos",
    response_model=MetricaRead,
    status_code=status.HTTP_201_CREATED,
)
async def analizar_segmento(
    sesion_id: int,
    data: SegmentoIn,
    service: ServiceDep,
    user: RequireEstudiante,
    _sub: SuscripcionActiva,
) -> MetricaRead | JSONResponse:
    try:
        metrica = await service.analizar_segmento(sesion_id, user, data)
    except BiometricServiceError:
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content={"detail": "El servicio biométrico no está disponible."},
        )
    return MetricaRead.model_validate(metrica)


@router.post(
    "/sesiones/{sesion_id}/frame",
    response_model=MetricaRead,
    status_code=status.HTTP_201_CREATED,
)
async def analizar_frame(
    sesion_id: int,
    service: ServiceDep,
    user: RequireEstudiante,
    _sub: SuscripcionActiva,
    file: Annotated[UploadFile, File()],
) -> MetricaRead | JSONResponse:
    """Recibe un frame de la cámara (imagen) y lo analiza con Rekognition (RF-04)."""
    imagen = await file.read()
    try:
        metrica = await service.analizar_frame(sesion_id, user, imagen)
    except BiometricServiceError:
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content={"detail": "El servicio biométrico no está disponible."},
        )
    return MetricaRead.model_validate(metrica)


@router.get("/sesiones/{sesion_id}/metricas", response_model=list[MetricaRead])
async def listar_metricas(
    sesion_id: int,
    service: ServiceDep,
    user: RequireEstudiante,
    _sub: SuscripcionActiva,
) -> list[MetricaRead]:
    metricas = await service.listar_metricas(sesion_id, user)
    return [MetricaRead.model_validate(m) for m in metricas]


@router.get("/sesiones/{sesion_id}/resumen", response_model=ResumenBiometrico)
async def resumen(
    sesion_id: int,
    service: ServiceDep,
    user: RequireEstudiante,
    _sub: SuscripcionActiva,
) -> ResumenBiometrico:
    datos = await service.resumen(sesion_id, user)
    return ResumenBiometrico(**datos)
