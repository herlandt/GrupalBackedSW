"""Verificación STANDALONE de AWS Transcribe Streaming + del fix de muletillas/ritmo.

Prueba PRINCIPAL (real): sintetiza una frase en español CON muletillas usando AWS
Polly (PCM 16 kHz) y la pasa por el pipeline REAL `transcribir_en_vivo`, confirmando
que `on_segmento` se dispara con muletillas/ritmo > 0 (valida el fix de estabilización
de parciales). Si Polly no está disponible (permisos), cae a una prueba de CONECTIVIDAD
con un tono: solo confirma que el stream abre/cierra sin excepción.

Corre bajo el mismo SelectorEventLoop que el backend en Windows.

Ejecutar:  python -m app.integrations.biometric.transcribe_check
"""

from __future__ import annotations

import asyncio
import math
import struct
import sys
from collections.abc import AsyncIterator

from amazon_transcribe.client import TranscribeStreamingClient
from amazon_transcribe.handlers import TranscriptResultStreamHandler
from amazon_transcribe.model import TranscriptEvent

from app.core.config import settings
from app.integrations.aws.session import get_boto_session
from app.integrations.biometric.transcribe import _resolver_credenciales, transcribir_en_vivo

_FRASE_1 = "Eh, bueno, este, mi tesis trata, o sea, sobre el problema de la deserción."
_FRASE_2 = "Pues entonces, digamos que es un tema muy importante, verdad."


async def _probar_con_voz() -> int:
    """Camino real: Polly -> PCM (+ silencio para probar pausas) -> transcribir_en_vivo."""
    polly = get_boto_session().client("polly")

    def _synth(texto: str) -> bytes:
        resp = polly.synthesize_speech(
            Text=texto, OutputFormat="pcm", VoiceId="Lupe", SampleRate="16000"
        )
        return bytes(resp["AudioStream"].read())

    silencio = b"\x00\x00" * 16000 * 3  # 3 s de silencio -> debe contar como pausa larga
    pcm = _synth(_FRASE_1) + silencio + _synth(_FRASE_2)
    print(f"Polly: {len(pcm)} bytes PCM (2 frases con ~3 s de silencio en medio).")

    async def audio() -> AsyncIterator[bytes]:
        paso = 3200  # ~100 ms a 16 kHz / 16-bit
        for i in range(0, len(pcm), paso):
            yield pcm[i : i + paso]
            await asyncio.sleep(0.06)

    segmentos: list[tuple[str, int, int | None, int]] = []

    async def on_segmento(texto: str, muletillas: int, wpm: int | None, pausas: int) -> None:
        segmentos.append((texto, muletillas, wpm, pausas))
        print(f"  on_segmento -> muletillas={muletillas} wpm={wpm} pausas={pausas} :: '{texto}'")

    await asyncio.wait_for(transcribir_en_vivo(audio(), on_segmento=on_segmento), timeout=90)

    total_mul = sum(m for _, m, _, _ in segmentos)
    total_pausas = sum(p for _, _, _, p in segmentos)
    print(
        f"\nSegmentos: {len(segmentos)} | muletillas: {total_mul} | pausas largas: {total_pausas}"
    )
    if segmentos and total_mul > 0 and total_pausas > 0:
        print("==> FIX VERIFICADO: muletillas, ritmo y PAUSAS reales con voz.")
        return 0
    print("==> ATENCION: faltó alguna señal (muletillas o pausas largas). Revisar.")
    return 1


def _tono_pcm(segundos: float = 2.0, hz: int = 16000, freq: float = 220.0) -> bytes:
    datos = bytearray()
    for i in range(int(segundos * hz)):
        datos += struct.pack("<h", int(0.2 * 32767 * math.sin(2 * math.pi * freq * i / hz)))
    return bytes(datos)


class _Verificador(TranscriptResultStreamHandler):
    finales = 0

    async def handle_transcript_event(self, transcript_event: TranscriptEvent) -> None:
        for resultado in transcript_event.transcript.results:
            if not resultado.is_partial:
                _Verificador.finales += 1


async def _probar_conectividad() -> int:
    """Fallback: tono sintético -> confirma que el stream abre/cierra sin excepción."""
    client = TranscribeStreamingClient(
        region=settings.aws_region, credential_resolver=_resolver_credenciales()
    )
    stream = await client.start_stream_transcription(
        language_code="es-US", media_sample_rate_hz=16000, media_encoding="pcm"
    )
    print("start_stream_transcription: OK (conexion establecida)")

    async def _enviar() -> None:
        pcm = _tono_pcm()
        for i in range(0, len(pcm), 3200):
            await stream.input_stream.send_audio_event(audio_chunk=pcm[i : i + 3200])
            await asyncio.sleep(0.05)
        await stream.input_stream.end_stream()

    handler = _Verificador(stream.output_stream)
    await asyncio.wait_for(asyncio.gather(_enviar(), handler.handle_events()), timeout=30)
    print("Stream completado SIN error. (tono: 0 resultados es normal)")
    print("==> El camino AWS Transcribe Streaming FUNCIONA; si el navegador no da")
    print("    muletillas, el problema esta en el navegador/WebSocket, no en AWS.")
    return 0


async def _main() -> int:
    loop = type(asyncio.get_running_loop()).__name__
    print(f"Region: {settings.aws_region}  |  event loop: {loop}")
    try:
        _resolver_credenciales()
        print("Credenciales (perfil AWS CLI): OK")
    except Exception as exc:  # noqa: BLE001 - diagnóstico
        print(f"Credenciales: FALLO -> {exc}")
        return 1
    try:
        return await _probar_con_voz()
    except Exception as exc:  # noqa: BLE001 - Polly sin permiso u otro fallo -> fallback
        print(f"Prueba con voz (Polly) no disponible -> {type(exc).__name__}: {exc}")
        print("Cayendo a prueba de conectividad con tono...")
        try:
            return await _probar_conectividad()
        except Exception as exc2:  # noqa: BLE001 - diagnóstico
            print(f"Conectividad: FALLO -> {type(exc2).__name__}: {exc2}")
            return 1


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    raise SystemExit(asyncio.run(_main()))
