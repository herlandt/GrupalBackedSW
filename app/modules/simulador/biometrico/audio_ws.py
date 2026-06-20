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
from typing import Any

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

# Un segmento reconocido pendiente de persistir: (transcripción, muletillas, wpm, pausas).
_Segmento = tuple[str, int, int | None, int]


def _encolar_fin(cola: asyncio.Queue[Any]) -> None:
    """Mete el sentinel de fin (None) SIN bloquear nunca.

    Si la cola está llena, descarta el elemento más antiguo para GARANTIZAR que el sentinel
    entre: un `await put` bloqueante aquí podría colgarse para siempre si el consumidor ya
    murió (cola llena, sin nadie que la drene), y sin sentinel el consumidor no terminaría.
    """
    try:
        cola.put_nowait(None)
    except asyncio.QueueFull:
        with contextlib.suppress(asyncio.QueueEmpty):
            cola.get_nowait()
        with contextlib.suppress(asyncio.QueueFull):
            cola.put_nowait(None)


async def _cerrar(
    websocket: WebSocket,
    tarea_receptor: asyncio.Task[None],
    tarea_persistidor: asyncio.Task[None],
    segmentos: asyncio.Queue[_Segmento | None],
) -> None:
    """Limpieza ordenada del WS de audio (cancela tareas, drena el persistidor y cierra).

    Se invoca BLINDADA con `asyncio.shield`: si el handler está siendo cancelado, esta
    corrutina NO debe interrumpirse a medias (dejaría tareas colgando o el WS sin cerrar).
    `gather(return_exceptions=True)` absorbe la cancelación/errores PROPIOS de las subtareas
    (las cancelamos nosotros), sin afectar a la cancelación del handler.
    """
    tarea_receptor.cancel()
    _encolar_fin(segmentos)  # sentinel para que el persistidor drene lo pendiente y salga
    with contextlib.suppress(TimeoutError):
        await asyncio.wait_for(
            asyncio.gather(tarea_receptor, tarea_persistidor, return_exceptions=True),
            timeout=5.0,
        )
    if not tarea_persistidor.done():  # no terminó en 5 s (BD lenta): se cancela
        tarea_persistidor.cancel()
        await asyncio.gather(tarea_persistidor, return_exceptions=True)
    with contextlib.suppress(Exception):
        await websocket.close()


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

    # Cola que desacopla la recepción del WS del envío a Transcribe. ACOTADA: si Transcribe
    # se atrasa, `put` espera (backpressure) en vez de acumular audio en RAM sin límite
    # (~200 chunks ≈ varios segundos de buffer; suficiente para un hipo de red).
    cola: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=200)
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
            _encolar_fin(cola)  # señal de fin para audio(), sin bloquear el cierre

    async def audio() -> AsyncIterator[bytes]:
        while True:
            fragmento = await cola.get()
            if fragmento is None:
                break
            yield fragmento

    # Segmentos reconocidos pendientes de PERSISTIR. Desacopla la persistencia (DB + audit)
    # del handler de Transcribe: si escribiéramos en BD dentro del callback, ese `await`
    # frenaría el drenado del stream HTTP/2 de AWS (backpressure → degradación/corte). El
    # callback solo encola (rápido); el worker `persistidor` persiste y refleja al navegador.
    segmentos: asyncio.Queue[_Segmento | None] = asyncio.Queue(maxsize=100)

    async def on_segmento(
        transcripcion: str, muletillas: int, wpm: int | None, pausas: int
    ) -> None:
        """Encola el segmento SIN bloquear el handler de Transcribe (best-effort)."""
        item: _Segmento = (transcripcion, muletillas, wpm, pausas)
        try:
            segmentos.put_nowait(item)
        except asyncio.QueueFull:
            # El persistidor se atrasó: descarta el más antiguo y prioriza lo reciente, sin
            # frenar nunca el drenado del stream de AWS (la persistencia es best-effort).
            with contextlib.suppress(asyncio.QueueEmpty):
                segmentos.get_nowait()
            with contextlib.suppress(asyncio.QueueFull):
                segmentos.put_nowait(item)

    async def persistidor() -> None:
        """Consume la cola: persiste cada segmento (sesión propia) y lo refleja al navegador."""
        while True:
            item = await segmentos.get()
            if item is None:  # señal de fin
                break
            transcripcion, muletillas, wpm, pausas = item
            async with SessionLocal() as db_seg:
                user = await UsuarioRepository(db_seg).get(usuario_id)
                if user is None:
                    break  # usuario eliminado: dejamos de persistir
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
                    break  # la sesión se cerró mientras hablaba: dejamos de persistir
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
    tarea_persistidor = asyncio.create_task(persistidor())
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
        # Limpieza BLINDADA: `shield` garantiza que _cerrar termine aunque el handler esté
        # siendo cancelado (no fuga tareas ni deja el WS abierto) y, a la vez, RE-PROPAGA esa
        # cancelación (cancelación estructurada: el task debe terminar como cancelado).
        limpieza = asyncio.ensure_future(
            _cerrar(websocket, tarea_receptor, tarea_persistidor, segmentos)
        )
        try:
            await asyncio.shield(limpieza)
        except asyncio.CancelledError:
            await limpieza  # espera a que la limpieza acabe pese a la cancelación
            raise
