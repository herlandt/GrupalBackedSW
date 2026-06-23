"""Tests del adaptador DeepSeek (respaldo del tribunal cuando Gemini agota su cuota)."""

import json

import pytest

from app.core.config import settings
from app.integrations.llm import deepseek


class _FakeResp:
    """Context manager mínimo que imita la respuesta de urlopen."""

    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def __enter__(self) -> "_FakeResp":
        return self

    def __exit__(self, *_a: object) -> None:
        return None

    def read(self) -> bytes:
        return self._payload


def test_sin_clave_lanza_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "deepseek_api_key", "")
    with pytest.raises(deepseek.DeepSeekError):
        deepseek.generar_preguntas("## Metodología\nEstudio cuantitativo.", 3)


def test_parsea_respuesta_estilo_openai(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "deepseek_api_key", "sk-fake")
    contenido = json.dumps(["¿Pregunta uno?", "¿Pregunta dos?"])
    payload = json.dumps({"choices": [{"message": {"content": contenido}}]}).encode("utf-8")
    monkeypatch.setattr(
        deepseek.urllib.request, "urlopen", lambda *_a, **_k: _FakeResp(payload)
    )
    preguntas = deepseek.generar_preguntas("## Metodología\nX", 3)
    assert preguntas == ["¿Pregunta uno?", "¿Pregunta dos?"]


def test_gemini_cae_a_deepseek(monkeypatch: pytest.MonkeyPatch) -> None:
    # El respaldo del tribunal: GeminiTribunal._intentar_deepseek usa el adaptador DeepSeek.
    from app.integrations.llm.gemini import GeminiTribunal

    monkeypatch.setattr(settings, "deepseek_api_key", "sk-fake")
    contenido = json.dumps(["¿P1?", "¿P2?"])
    payload = json.dumps({"choices": [{"message": {"content": contenido}}]}).encode("utf-8")
    monkeypatch.setattr(
        deepseek.urllib.request, "urlopen", lambda *_a, **_k: _FakeResp(payload)
    )
    preguntas = GeminiTribunal()._intentar_deepseek("## Metodología\nX", "ESTANDAR")
    assert preguntas == ["¿P1?", "¿P2?"]
