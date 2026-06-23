"""Puerto de transcripción de un audio grabado a texto (CU-16).

El tribunal por voz transcribe EN VIVO en el navegador (WebSocket → Transcribe streaming) y
envía el texto. Este puerto es el RESPALDO del backend: si llega una respuesta solo-audio
(sin texto), transcribe el archivo antes de evaluar, para no calificar contra una cadena vacía.
"""

from typing import Protocol


class TranscriptionServiceError(Exception):
    """La transcripción por lotes falló o no está disponible."""


class TranscriptionPort(Protocol):
    async def transcribir(self, audio_url: str) -> str:
        """Transcribe el audio en `audio_url` a texto ('' si no hay habla reconocible)."""
        ...
