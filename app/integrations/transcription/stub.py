"""Stub de transcripción para desarrollo/test: no llama a AWS.

Devuelve cadena vacía (en dev/test el tribunal por voz envía el texto ya transcrito en vivo;
no hay transcripción por lotes). En los tests se sustituye por un fake que devuelve texto.
"""


class StubTranscription:
    async def transcribir(self, audio_url: str) -> str:
        return ""
