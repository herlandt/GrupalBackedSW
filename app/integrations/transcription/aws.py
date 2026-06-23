"""Adaptador de transcripción por lotes con AWS Transcribe (CU-16, respaldo del backend).

Transcribe un audio almacenado en S3 (la respuesta del estudiante) arrancando un job de
Transcribe, esperando a que termine y leyendo el resultado. Es el camino de RESPALDO: el
tribunal por voz normalmente transcribe en vivo en el navegador; esto cubre las respuestas
que llegan solo como audio. Las credenciales salen del rol/perfil de AWS (boto3), no del código.
"""

from __future__ import annotations

import json
import time
import urllib.request
import uuid
from typing import Any

import anyio

from app.integrations.aws.session import get_aws_client
from app.integrations.transcription.port import TranscriptionServiceError

# Extensión del audio -> MediaFormat aceptado por Transcribe.
_FORMATOS: dict[str, str] = {
    "mp3": "mp3", "mp4": "mp4", "m4a": "mp4", "wav": "wav",
    "flac": "flac", "ogg": "ogg", "webm": "webm", "amr": "amr",
}
_MAX_INTENTOS = 60  # ~2 min (sondeo cada 2 s)


class AwsTranscription:
    async def transcribir(self, audio_url: str) -> str:
        # boto3 es síncrono y el job tarda: a un hilo para no bloquear el event loop.
        return await anyio.to_thread.run_sync(self._transcribir, audio_url)

    def _transcribir(self, audio_url: str) -> str:
        if not (audio_url.startswith("s3://") or "amazonaws.com" in audio_url):
            raise TranscriptionServiceError(
                "La transcripción por lotes requiere el audio almacenado en S3."
            )
        cliente = get_aws_client("transcribe")
        ext = audio_url.rsplit(".", 1)[-1].lower()
        job = f"tribunal-{uuid.uuid4().hex}"
        try:
            cliente.start_transcription_job(
                TranscriptionJobName=job,
                LanguageCode="es-US",
                MediaFormat=_FORMATOS.get(ext, "mp3"),
                Media={"MediaFileUri": audio_url},
            )
            for _ in range(_MAX_INTENTOS):
                trabajo = cliente.get_transcription_job(TranscriptionJobName=job)
                estado = trabajo["TranscriptionJob"]["TranscriptionJobStatus"]
                if estado == "COMPLETED":
                    uri = trabajo["TranscriptionJob"]["Transcript"]["TranscriptFileUri"]
                    return _leer_transcripcion(uri)
                if estado == "FAILED":
                    raise TranscriptionServiceError("Transcribe no pudo procesar el audio.")
                time.sleep(2)
            raise TranscriptionServiceError("Transcribe agotó el tiempo de espera.")
        except TranscriptionServiceError:
            raise
        except Exception as exc:  # red / credenciales / servicio
            raise TranscriptionServiceError(f"Transcribe no disponible: {exc}") from exc
        finally:
            try:
                cliente.delete_transcription_job(TranscriptionJobName=job)
            except Exception:  # limpieza best-effort
                pass


def _leer_transcripcion(uri: str) -> str:
    """Descarga el JSON de resultado de Transcribe y concatena los transcripts."""
    with urllib.request.urlopen(uri, timeout=30) as resp:  # noqa: S310  (URL de AWS)
        datos: dict[str, Any] = json.load(resp)
    transcripts = datos.get("results", {}).get("transcripts", [])
    return " ".join(t.get("transcript", "") for t in transcripts).strip()
