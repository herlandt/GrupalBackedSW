"""Embeddings de Google Gemini (tier gratuito) para la coherencia discurso↔documento.

Mide la similitud semántica entre lo que el estudiante DIJO y los fragmentos de su tesis,
usando `text-embedding-004` (gratis) en vez de Titan/Bedrock (en cuota 0). Una sola llamada
`batchEmbedContents` para el discurso + todos los fragmentos. Reutiliza el pool de claves de
`GEMINI_API_KEY` con failover (al agotarse una, prueba la siguiente). Stdlib `urllib`, sin
dependencias nuevas. Es BLOQUEANTE: se invoca dentro de un hilo (lo llama el cierre de sesión).
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request

import numpy as np

from app.core.config import settings

logger = logging.getLogger(__name__)

_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:batchEmbedContents"


class GeminiEmbedError(Exception):
    """No se pudieron obtener embeddings de Gemini (sin claves, cuota agotada o error)."""


# Calibración del coseno → 0..1. Dos textos del MISMO IDIOMA sin relación dan ~0.50-0.55 (el
# "piso" del espacio de embeddings); uno que cubre bien el documento, ~0.80-0.85. Mapeamos esa
# banda real a [0,1] para que algo SIN relación quede bajo de verdad (no 54) y una buena defensa
# quede alto. Empírico de gemini-embedding-001; si cambias de modelo, reajusta estos valores.
_PISO_COSENO = 0.50
_TECHO_COSENO = 0.85


def _calibrar(coseno: float) -> float:
    """Lleva el coseno crudo (~0.50 sin relación … ~0.85 muy relacionado) a un 0..1 intuitivo."""
    return max(0.0, min(1.0, (coseno - _PISO_COSENO) / (_TECHO_COSENO - _PISO_COSENO)))


def _batch_embed(textos: list[str]) -> list[list[float]]:
    """Embebe varios textos en una sola petición, con failover entre claves (sin `taskType`:
    empíricamente da la mejor separación discurso↔documento)."""
    claves = settings.gemini_api_keys
    if not claves:
        raise GeminiEmbedError("No hay GEMINI_API_KEY para embeddings.")
    modelo = settings.gemini_embed_model
    body = json.dumps(
        {
            "requests": [
                {"model": f"models/{modelo}", "content": {"parts": [{"text": t[:8000]}]}}
                for t in textos
            ]
        }
    ).encode("utf-8")
    url = _ENDPOINT.format(model=modelo)
    ultimo: Exception | None = None
    for i, clave in enumerate(claves, start=1):
        req = urllib.request.Request(
            url,
            data=body,
            method="POST",
            headers={"Content-Type": "application/json", "x-goog-api-key": clave},
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:  # noqa: S310 (URL fija HTTPS)
                data = json.loads(resp.read().decode("utf-8"))
            return [list(e["values"]) for e in data["embeddings"]]
        except urllib.error.HTTPError as exc:
            detalle = exc.read().decode("utf-8", errors="replace")
            agotada = exc.code == 429 or "RESOURCE_EXHAUSTED" in detalle
            logger.warning(
                "Embeddings Gemini: clave %d/%d %s, probando la siguiente.",
                i, len(claves), "agotada (429)" if agotada else f"falló (HTTP {exc.code})",
            )
            ultimo = GeminiEmbedError(f"HTTP {exc.code}: {detalle[:150]}")
        except Exception as exc:  # red / respuesta inesperada
            logger.warning("Embeddings Gemini: clave %d/%d error (%s).", i, len(claves), exc)
            ultimo = GeminiEmbedError(str(exc))
    raise ultimo or GeminiEmbedError("Embeddings de Gemini no disponibles.")


def _coseno(a: list[float], b: list[float]) -> float:
    va, vb = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    norma = float(np.linalg.norm(va) * np.linalg.norm(vb))
    return float(np.dot(va, vb) / norma) if norma else 0.0


def coherencia(discurso: str, fragmentos: list[str]) -> float:
    """Similitud (0..1) entre el discurso y el documento: promedio de las 3 mejores secciones.

    Embebe discurso + fragmentos en una llamada y compara por coseno. Lanza `GeminiEmbedError`
    si no se pudo medir (aguas arriba se trata como NEUTRO → la UI muestra "no medible").
    """
    if not fragmentos:
        raise GeminiEmbedError("Sin fragmentos para comparar.")
    vectores = _batch_embed([discurso, *fragmentos])
    if len(vectores) < 2:
        raise GeminiEmbedError("Respuesta de embeddings incompleta.")
    v_disc, v_frags = vectores[0], vectores[1:]
    sims = [_coseno(v_disc, vf) for vf in v_frags]
    mejores = sorted(sims, reverse=True)[:3]
    bruto = sum(mejores) / len(mejores)
    return round(_calibrar(bruto), 3)
