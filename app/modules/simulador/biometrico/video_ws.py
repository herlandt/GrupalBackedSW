"""Endpoint WebSocket de VIDEO en vivo (CU-14, RF-04).

El navegador envía frames JPEG de la cámara por este socket; el backend analiza cada
frame con AWS Rekognition (postura + contacto visual), persiste la métrica y devuelve el
resultado para mostrarlo en vivo. Mismo transporte WebSocket que el audio, por consistencia.
La IA evaluadora NO interviene aquí: decide al final (`generar_resultado`) con las métricas
agregadas, sin importar si los frames llegaron por HTTP o WebSocket.
"""

from __future__ import annotations

import contextlib
import logging

from fastapi import WebSocket, WebSocketDisconnect, status

from app.core.database import SessionLocal
from app.core.exceptions import BusinessRuleError, ResourceNotFoundError
from app.integrations.biometric.port import BiometricServiceError
from app.integrations.factory import get_biometric_service
from app.modules.administracion.usuarios.repository import UsuarioRepository
from app.modules.simulador.biometrico.audio_ws import _autenticar  # reutiliza la auth del WS
from app.modules.simulador.biometrico.service import BiometricoService

logger = logging.getLogger(__name__)


async def video_streaming(websocket: WebSocket, sesion_id: int) -> None:
    await websocket.accept()
    token = websocket.query_params.get("token", "")
    logger.info("WS video: conexión aceptada (sesion=%s)", sesion_id)

    # Auth + validación inicial (sesión propia y EN_CURSO) con una sesión de DB efímera.
    async with SessionLocal() as db:
        usuario = await _autenticar(db, token)
        if usuario is None:
            logger.warning("WS video: token inválido (sesion=%s) -> cierre 1008", sesion_id)
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        usuario_id = usuario.id
        try:
            await BiometricoService(db, get_biometric_service()).asegurar_en_curso(
                sesion_id, usuario
            )
        except (ResourceNotFoundError, BusinessRuleError) as exc:
            logger.warning("WS video: sesión no analizable (%s) -> cierre 1008", exc)
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

    frames = 0
    try:
        while True:
            mensaje = await websocket.receive()
            if mensaje["type"] == "websocket.disconnect":
                break
            datos = mensaje.get("bytes")
            if not datos:
                if mensaje.get("text") == "stop":
                    break
                continue
            # Cada frame: Rekognition (en hilo) + persiste, con su propia sesión de DB.
            async with SessionLocal() as db_frame:
                user = await UsuarioRepository(db_frame).get(usuario_id)
                if user is None:
                    break
                try:
                    metrica = await BiometricoService(
                        db_frame, get_biometric_service()
                    ).analizar_frame(sesion_id, user, datos)
                    await db_frame.commit()
                except BiometricServiceError:
                    with contextlib.suppress(Exception):
                        await websocket.send_json({"error": "Rekognition no disponible."})
                    continue
                except (ResourceNotFoundError, BusinessRuleError):
                    break  # la sesión se cerró: dejamos de analizar
                postura = (
                    float(metrica.postura_score) if metrica.postura_score is not None else None
                )
                contacto = (
                    float(metrica.contacto_visual_pct)
                    if metrica.contacto_visual_pct is not None
                    else None
                )
            frames += 1
            with contextlib.suppress(Exception):
                await websocket.send_json({"postura": postura, "contacto_visual": contacto})
    except WebSocketDisconnect:
        pass
    finally:
        logger.info("WS video: %d frames analizados (sesion=%s)", frames, sesion_id)
        with contextlib.suppress(Exception):
            await websocket.close()
