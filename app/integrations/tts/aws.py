"""Adaptador de TTS sobre Amazon Polly (voz neural en español).

`synthesize_speech` es boto3 SÍNCRONO → se ejecuta en un hilo. Polly es un servicio
estándar (no requiere activar acceso a modelos como Bedrock); solo el permiso IAM
`polly:SynthesizeSpeech`.
"""

from __future__ import annotations

import anyio

from app.core.config import settings
from app.integrations.aws.session import get_aws_client
from app.integrations.tts.port import TTSServiceError

# Polly factura/limita por nº de caracteres por petición (3000 en texto plano).
_MAX_CHARS = 2900


class AwsPolly:
    async def sintetizar(self, texto: str) -> bytes:
        return await anyio.to_thread.run_sync(self._sintetizar, texto)

    def _sintetizar(self, texto: str) -> bytes:
        limpio = texto.strip()
        if not limpio:
            raise TTSServiceError("Texto vacío para sintetizar")
        try:
            polly = get_aws_client("polly")
            resp = polly.synthesize_speech(
                Text=limpio[:_MAX_CHARS],
                OutputFormat="mp3",
                VoiceId=settings.polly_voice,
                Engine=settings.polly_engine,
            )
            stream = resp.get("AudioStream")
            if stream is None:
                raise TTSServiceError("Polly no devolvió audio")
            return bytes(stream.read())
        except TTSServiceError:
            raise
        except Exception as exc:  # red / permisos / voz inválida
            raise TTSServiceError(f"Polly falló: {exc}") from exc
