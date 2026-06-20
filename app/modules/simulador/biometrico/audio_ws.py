"""Endpoint WebSocket de AUDIO en vivo (CU-14, RF-05).

El navegador transmite el micrófono como PCM (16 kHz, 16-bit, mono) por este socket;
el backend lo reenvía a AWS Transcribe Streaming y, por cada frase reconocida, persiste
una métrica de expresión oral (muletillas + ritmo) y devuelve la transcripción para
mostrarla en vivo. La autenticación viaja como `?token=<JWT>` (el WS no admite cabeceras).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator

from fastapi import HTTPException, WebSocket, WebSocketDisconnect, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import SessionLocal
from app.core.exceptions import BusinessRuleError, ResourceNotFoundError
from app.core.security import decode_token
from app.integrations.biometric.port import BiometricServiceError
from app.integrations.biometric.transcribe import transcribir_en_vivo
from app.integrations.factory import get_biometric_service
from app.modules.administracion.usuarios.models import Usuario
from app.modules.administracion.usuarios.repository import UsuarioRepository
from app.modules.simulador.biometrico.service import BiometricoService

logger = logging.getLogger(__name__)


async def _autenticar(db: AsyncSession, token: str) -> Usuario | None:
    """Resuelve el Usuario del JWT (query param). Devuelve None si es inválido/inactivo."""
    try:
        payload = decode_token(token)
    except HTTPException:
        return None
    sub = payload.get("sub")
    if sub is None:
        return None
    user = await UsuarioRepository(db).get(int(sub))
    if user is None or not user.activo:
        return None
    return user


async def audio_streaming(websocket: WebSocket, sesion_id: int) -> None:
    await websocket.accept()
    token = websocket.query_params.get("token", "")
    logger.info("WS audio: conexión aceptada (sesion=%s)", sesion_id)

    # Auth + validación inicial (sesión propia y EN_CURSO) con una sesión de DB efímera.
    async with SessionLocal() as db:
        usuario = await _autenticar(db, token)
        if usuario is None:
            logger.warning("WS audio: token inválido (sesion=%s) -> cierre 1008", sesion_id)
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        usuario_id = usuario.id
        try:
            await BiometricoService(db, get_biometric_service()).asegurar_en_curso(
                sesion_id, usuario
            )
        except (ResourceNotFoundError, BusinessRuleError) as exc:
            logger.warning("WS audio: sesión no analizable (%s) -> cierre 1008", exc)
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

    # Cola que desacopla la recepción del WS del envío a Transcribe.
    cola: asyncio.Queue[bytes | None] = asyncio.Queue()
    recibidos = {"chunks": 0, "bytes": 0}

    async def receptor() -> None:
        """Lee fragmentos PCM del navegador hasta 'stop' o desconexión."""
        try:
            while True:
                mensaje = await websocket.receive()
                if mensaje["type"] == "websocket.disconnect":
                    break
                datos = mensaje.get("bytes")
                if datos:
                    recibidos["chunks"] += 1
                    recibidos["bytes"] += len(datos)
                    if recibidos["chunks"] % 25 == 0:  # confirmación en vivo (~cada 2 s)
                        logger.info("WS audio: %d chunks recibidos…", recibidos["chunks"])
                    await cola.put(datos)
                elif mensaje.get("text") == "stop":
                    break
        except WebSocketDisconnect:
            pass
        finally:
            logger.info(
                "WS audio: recibidos %d chunks (%d bytes) del navegador",
                recibidos["chunks"],
                recibidos["bytes"],
            )
            await cola.put(None)  # señal de fin para el iterador de audio

    async def audio() -> AsyncIterator[bytes]:
        while True:
            fragmento = await cola.get()
            if fragmento is None:
                break
            yield fragmento

    async def on_segmento(
        transcripcion: str, muletillas: int, wpm: int | None, pausas: int
    ) -> None:
        """Persiste el segmento (sesión de DB propia) y lo refleja al navegador."""
        async with SessionLocal() as db_seg:
            user = await UsuarioRepository(db_seg).get(usuario_id)
            if user is None:
                return
            try:
                await BiometricoService(db_seg, get_biometric_service()).registrar_audio(
                    sesion_id,
                    user,
                    muletillas=muletillas,
                    wpm=wpm,
                    pausas=pausas,
                    transcripcion=transcripcion,
                )
                await db_seg.commit()
            except (ResourceNotFoundError, BusinessRuleError):
                return  # la sesión se cerró mientras hablaba: dejamos de persistir
        with contextlib.suppress(Exception):
            await websocket.send_json(
                {
                    "transcripcion": transcripcion,
                    "muletillas": muletillas,
                    "ritmo_wpm": wpm,
                    "pausas": pausas,
                }
            )

    tarea_receptor = asyncio.create_task(receptor())
    try:
        await transcribir_en_vivo(audio(), on_segmento=on_segmento)
    except BiometricServiceError as exc:
        logger.warning("WS audio: Transcribe falló -> %s", exc)
        with contextlib.suppress(Exception):
            await websocket.send_json({"error": str(exc)})
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("WS audio: fallo inesperado en el stream")
        with contextlib.suppress(Exception):
            await websocket.send_json({"error": "Fallo interno del análisis de voz."})
    finally:
        tarea_receptor.cancel()
        with contextlib.suppress(Exception):
            await tarea_receptor
        with contextlib.suppress(Exception):
            await websocket.close()
