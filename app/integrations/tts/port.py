"""Puerto de síntesis de voz (TTS) para el tribunal por voz (CU-16)."""

from typing import Protocol


class TTSServiceError(Exception):
    """Fallo al sintetizar voz (servicio no disponible, texto inválido, etc.)."""


class TTSPort(Protocol):
    async def sintetizar(self, texto: str) -> bytes:
        """Devuelve el audio MP3 del texto. Lanza TTSServiceError si falla."""
        ...
