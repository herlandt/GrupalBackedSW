"""Adaptador de AWS Transcribe Streaming: transcribe el audio de la defensa EN VIVO
y deriva las métricas de expresión oral (RF-05): muletillas y ritmo (palabras/min).

Usa el SDK async `amazon-transcribe` (streaming sobre HTTP/2). Las credenciales salen
del mismo perfil de AWS CLI que el resto del sistema (boto3) — nunca del código. El
flujo lo orquesta el endpoint WebSocket (`audio_ws.py`), que alimenta el iterador de
audio PCM y persiste cada segmento reconocido.
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

import anyio
from amazon_transcribe.auth import StaticCredentialResolver
from amazon_transcribe.client import TranscribeStreamingClient
from amazon_transcribe.handlers import TranscriptResultStreamHandler
from amazon_transcribe.model import Item, TranscriptEvent

from app.core.config import settings
from app.integrations.aws.session import get_boto_session
from app.integrations.biometric.port import BiometricServiceError

logger = logging.getLogger(__name__)

# Muletillas LÉXICAS del español que AWS Transcribe sí transcribe (RF-05). Heurística:
# prioriza recuperar sobre precisión (algún falso positivo como el demostrativo "este"
# es aceptable). OJO: los rellenos puramente acústicos ("eh", "mmm") Transcribe los
# limpia a menudo, por eso se cuentan sobre todo los que son palabras reales.
MULETILLAS: tuple[str, ...] = (
    "por así decirlo",
    "como te digo",
    "es decir",
    "como que",
    "a ver",
    "es que",
    "no sé",
    "o sea",
    "este",
    "esto",
    # Sonidos de duda/hesitación tal como los transcribe Transcribe (interjecciones).
    "eh",
    "ehh",
    "eeh",
    "ehm",
    "em",
    "mmm",
    "hm",
    "hmm",
    "hum",
    "ah",
    "ajá",
    # Muletillas léxicas frecuentes.
    "pues",
    "bueno",
    "entonces",
    "digamos",
    "verdad",
    "mira",
    "tipo",
)

# Hueco de tiempo (s) entre palabras consecutivas que cuenta como "pausa larga" (RF-05).
UMBRAL_PAUSA_S = 2.0

# Recibe (transcripción, muletillas, ritmo_wpm, pausas_largas) de cada segmento estable.
OnSegmento = Callable[[str, int, "int | None", int], Awaitable[None]]


def contar_muletillas(texto: str) -> int:
    """Cuenta muletillas en un texto (con límites de palabra, sin distinguir mayúsculas)."""
    bajo = texto.lower()
    total = 0
    for muletilla in MULETILLAS:
        total += len(re.findall(rf"(?<!\w){re.escape(muletilla)}(?!\w)", bajo))
    return total


def _contar_palabras(texto: str) -> int:
    return len(re.findall(r"\w+", texto))


class _ColectorTranscripcion(TranscriptResultStreamHandler):
    """Procesa los eventos de Transcribe en vivo.

    Usa la ESTABILIZACIÓN de parciales: emite las palabras ya marcadas como estables
    (`item.stable`) en cuanto se confirman (~1-2 s), sin esperar a un resultado final
    (que Transcribe solo emite tras una pausa larga). Lleva un índice por `result_id` de
    los items ya procesados para no recontar, y mide PAUSAS LARGAS como huecos de tiempo
    entre palabras consecutivas (RF-05).
    """

    def __init__(self, output_stream: Any, on_segmento: OnSegmento) -> None:
        super().__init__(output_stream)
        self._on_segmento = on_segmento
        self._palabras_total = 0
        self._consumidos: dict[str, int] = {}  # result_id -> nº de items ya procesados
        self._primer_inicio: float | None = None  # start_time de la primera palabra (s)
        self._ultimo_fin: float | None = None  # end_time de la última palabra (s)

    async def handle_transcript_event(self, transcript_event: TranscriptEvent) -> None:
        for resultado in transcript_event.transcript.results:
            alternativas = resultado.alternatives or []
            if not alternativas:
                continue
            items = alternativas[0].items or []
            final = not resultado.is_partial
            rid = resultado.result_id or ""
            desde = self._consumidos.get(rid, 0)

            # Items NUEVOS: el prefijo estable (o todos, si el resultado ya es final). La
            # puntuación no bloquea; una palabra aún no estable sí corta el prefijo.
            nuevos: list[Item] = []
            consumidos = desde
            for idx in range(desde, len(items)):
                item = items[idx]
                if not (final or item.stable or item.item_type == "punctuation"):
                    break
                nuevos.append(item)
                consumidos = idx + 1
            if not nuevos:
                continue
            self._consumidos[rid] = consumidos

            # Pausas largas: huecos entre el fin de una palabra y el inicio de la siguiente.
            pausas = 0
            partes: list[str] = []
            for item in nuevos:
                if item.content:
                    partes.append(item.content)
                if item.item_type != "pronunciation":
                    continue
                if self._primer_inicio is None and item.start_time is not None:
                    self._primer_inicio = item.start_time
                if (
                    self._ultimo_fin is not None
                    and item.start_time is not None
                    and item.start_time - self._ultimo_fin > UMBRAL_PAUSA_S
                ):
                    pausas += 1
                if item.end_time is not None:
                    self._ultimo_fin = item.end_time

            nuevo = " ".join(partes).strip()
            if not nuevo:
                continue
            self._palabras_total += _contar_palabras(nuevo)
            # Ritmo sobre el TIEMPO DE AUDIO hablado (no el reloj de pared): el lag de red o
            # los silencios de arranque/cierre no deben distorsionar el wpm (RF-05).
            if self._primer_inicio is not None and self._ultimo_fin is not None:
                span_s = max(self._ultimo_fin - self._primer_inicio, 1.0)
            else:
                span_s = 1.0
            wpm = int(self._palabras_total / (span_s / 60.0))
            muletillas = contar_muletillas(nuevo)
            logger.info(
                "Transcribe segmento: '%s' (muletillas=%d, wpm=%d, pausas=%d)",
                nuevo,
                muletillas,
                wpm,
                pausas,
            )
            await self._on_segmento(nuevo, muletillas, wpm, pausas)


def _resolver_credenciales() -> StaticCredentialResolver:
    """Toma las credenciales del perfil de AWS CLI (boto3) y las adapta al SDK de streaming."""
    credenciales = get_boto_session().get_credentials()
    if credenciales is None:
        raise BiometricServiceError("No hay credenciales de AWS configuradas (perfil de AWS CLI).")
    congeladas = credenciales.get_frozen_credentials()
    if congeladas.access_key is None or congeladas.secret_key is None:
        raise BiometricServiceError("Credenciales de AWS incompletas (perfil de AWS CLI).")
    return StaticCredentialResolver(
        congeladas.access_key, congeladas.secret_key, congeladas.token
    )


async def transcribir_en_vivo(audio: AsyncIterator[bytes], *, on_segmento: OnSegmento) -> None:
    """Transcribe un flujo de audio PCM (16 kHz, 16-bit, mono) con Transcribe Streaming.

    `audio` produce los fragmentos PCM que llegan del navegador; `on_segmento` se invoca
    por cada frase reconocida con su conteo de muletillas y el ritmo (wpm) acumulado.
    Cualquier fallo de AWS se traduce a `BiometricServiceError`.
    """
    # Resolver credenciales puede hacer I/O (lee ~/.aws / refresca STS): a un hilo.
    resolver = await anyio.to_thread.run_sync(_resolver_credenciales)
    client = TranscribeStreamingClient(
        region=settings.aws_region, credential_resolver=resolver
    )
    try:
        stream = await client.start_stream_transcription(
            language_code="es-US",
            media_sample_rate_hz=16000,
            media_encoding="pcm",
            # Estabilización: entrega palabras estables en ~1-2 s, sin esperar al final.
            # "medium" equilibra responsividad/precisión: "high" tardaba tanto en marcar
            # estables que apenas emitía palabras (se veía "no capta bien"); "low" revisaría
            # demasiado. Medium emite más rápido sin recontar a cada momento.
            enable_partial_results_stabilization=True,
            partial_results_stability="medium",
        )
    except Exception as exc:  # red / credenciales / región sin Transcribe
        raise BiometricServiceError(f"Transcribe no pudo iniciar el stream: {exc}") from exc
    logger.info("Transcribe streaming iniciado (es-US, 16kHz, estabilización alta).")

    async def _enviar_audio() -> None:
        async for fragmento in audio:
            await stream.input_stream.send_audio_event(audio_chunk=fragmento)
        await stream.input_stream.end_stream()

    colector = _ColectorTranscripcion(stream.output_stream, on_segmento)
    try:
        await asyncio.gather(_enviar_audio(), colector.handle_events())
    except BiometricServiceError:
        raise
    except Exception as exc:  # corte de red / error del servicio durante el stream
        raise BiometricServiceError(f"Transcribe streaming falló: {exc}") from exc
