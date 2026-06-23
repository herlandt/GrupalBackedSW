"""Generación de preguntas del tribunal con DeepSeek — RESPALDO de pago de Gemini.

DeepSeek expone una API de chat compatible con OpenAI. Se usa como respaldo cuando se agota la
cuota gratuita de Gemini (o no hay clave de Gemini); si DeepSeek tampoco está disponible, el
adaptador cae a las plantillas de `DocumentoTribunal`. Reutiliza los helpers de `_generativo`
(mismo prompt y parseo que Claude/Gemini), así que solo cambia el transporte HTTP. La evaluación
de respuestas NO usa LLM. Stdlib `urllib`, sin dependencias nuevas.

DeepSeek NO ofrece embeddings: la coherencia discurso↔documento sigue en Gemini/Titan, no aquí.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any

from app.core.config import settings
from app.integrations.llm._generativo import SISTEMA, construir_prompt, parsear_preguntas

logger = logging.getLogger(__name__)

_ENDPOINT = "https://api.deepseek.com/chat/completions"


class DeepSeekError(Exception):
    """DeepSeek no disponible (sin clave, error HTTP o respuesta inválida)."""


def generar_preguntas(contexto: str, n: int) -> list[str]:
    """Genera `n` preguntas de defensa con DeepSeek. Lanza `DeepSeekError` si no hay clave o falla.

    Es BLOQUEANTE (HTTP síncrono): el llamador ya corre dentro de un hilo.
    """
    clave = settings.deepseek_api_key.strip()
    if not clave:
        raise DeepSeekError("No hay DEEPSEEK_API_KEY configurada.")
    body = json.dumps(
        {
            "model": settings.deepseek_model,
            "messages": [
                {"role": "system", "content": SISTEMA},
                {"role": "user", "content": construir_prompt(contexto, n)},
            ],
            "temperature": 0.4,
            "max_tokens": 1024,
            "stream": False,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        _ENDPOINT,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {clave}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=40) as resp:  # noqa: S310 (URL fija HTTPS)
            data: dict[str, Any] = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detalle = exc.read().decode("utf-8", errors="replace")
        raise DeepSeekError(f"HTTP {exc.code}: {detalle[:200]}") from exc
    except Exception as exc:  # red / timeout / respuesta no-JSON
        raise DeepSeekError(str(exc)) from exc
    return parsear_preguntas(_texto_de_respuesta(data), n)


def _texto_de_respuesta(data: dict[str, Any]) -> str:
    """Extrae el contenido del primer choice (formato OpenAI), tolerante a forma."""
    try:
        return str(data["choices"][0]["message"]["content"] or "")
    except (KeyError, IndexError, TypeError):
        return ""
