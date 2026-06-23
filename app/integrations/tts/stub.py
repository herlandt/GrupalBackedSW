"""TTS de desarrollo: no llama a AWS. Devuelve unos bytes fijos (no es audio real)."""

from __future__ import annotations

from app.integrations.tts.port import TTSServiceError


class StubTTS:
    async def sintetizar(self, texto: str) -> bytes:
        if not texto.strip():
            raise TTSServiceError("Texto vacío para sintetizar")
        # Marcador para el frontend de dev; en producción se usa Polly (TTS_BACKEND=aws).
        return b"STUB_TTS_AUDIO"
