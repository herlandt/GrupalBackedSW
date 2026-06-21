"""Tribunal con Google Gemini (2.5 Flash) — COMPLEMENTO de las plantillas, muy bajo costo.

Gemini genera preguntas COHERENTES leyendo el contenido real del documento. Mismo patrón
barato que el adaptador de Claude: solo GENERA (la evaluación sigue local, sin tokens), manda
solo prosa limpia recortada, y si Gemini falla cae a las plantillas de `DocumentoTribunal`.

Usa la librería estándar (`urllib`) para no añadir dependencias de runtime. Se activa con
`settings.tribunal_llm_backend == "gemini"`.

FAILOVER DE CLAVES: `GEMINI_API_KEY` admite VARIAS keys separadas por coma. Cuando una se
agota (HTTP 429 / RESOURCE_EXHAUSTED) salta a la siguiente automáticamente. Si TODAS se agotan,
lo dice en el log ("se agotaron todas las claves... agrega/renueva") y cae a plantillas.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any

import anyio

from app.core.config import settings
from app.integrations.analysis.extraction import extraer_texto, particionar, resolver_path
from app.integrations.llm._generativo import (
    SISTEMA,
    construir_contexto,
    construir_prompt,
    n_preguntas,
    parsear_preguntas,
)
from app.integrations.llm.documento import DocumentoTribunal
from app.integrations.llm.port import PreguntaGeneradaDTO

logger = logging.getLogger(__name__)

_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


class _CuotaAgotada(Exception):
    """Se agotaron TODAS las claves de Gemini (HTTP 429 / RESOURCE_EXHAUSTED)."""


class GeminiTribunal(DocumentoTribunal):
    async def generar_preguntas(
        self, *, archivo_url: str, formato: str, nivel_dificultad: str
    ) -> list[PreguntaGeneradaDTO]:
        # Lectura del documento + llamadas HTTP son BLOQUEANTES → a un hilo.
        return await anyio.to_thread.run_sync(
            self._generar_con_gemini, archivo_url, formato, nivel_dificultad
        )

    def _generar_con_gemini(
        self, archivo_url: str, formato: str, nivel_dificultad: str
    ) -> list[PreguntaGeneradaDTO]:
        if not settings.gemini_api_keys:
            logger.warning("Tribunal Gemini: falta GEMINI_API_KEY, uso plantillas.")
            return self._generar(archivo_url, formato, nivel_dificultad)
        try:
            texto = extraer_texto(resolver_path(archivo_url), formato)
        except Exception:  # archivo ilegible → plantillas
            return self._generar(archivo_url, formato, nivel_dificultad)
        secciones = particionar(texto) if texto.strip() else {}
        contexto = construir_contexto(secciones)
        if not contexto:  # documento sin prosa aprovechable → plantillas (genéricas)
            return self._generar(archivo_url, formato, nivel_dificultad)
        try:
            preguntas = self._preguntas_gemini(contexto, nivel_dificultad)
        except _CuotaAgotada:
            logger.warning(
                "Tribunal Gemini: se AGOTARON TODAS las claves (HTTP 429). Agrega o renueva "
                "claves en GEMINI_API_KEY (separadas por coma). Uso plantillas mientras tanto."
            )
            return self._generar(archivo_url, formato, nivel_dificultad)
        except Exception as exc:  # red / todas las claves invalidas / respuesta rara → plantillas
            logger.warning("Tribunal Gemini no disponible, uso plantillas: %s", exc)
            return self._generar(archivo_url, formato, nivel_dificultad)
        if not preguntas:
            return self._generar(archivo_url, formato, nivel_dificultad)
        return [PreguntaGeneradaDTO(orden=i, texto=t) for i, t in enumerate(preguntas, start=1)]

    def _preguntas_gemini(self, contexto: str, nivel_dificultad: str) -> list[str]:
        n = n_preguntas(nivel_dificultad)
        body = json.dumps(
            {
                "systemInstruction": {"parts": [{"text": SISTEMA}]},
                "contents": [{"role": "user", "parts": [{"text": construir_prompt(contexto, n)}]}],
                "generationConfig": {
                    "temperature": 0.4,
                    "maxOutputTokens": 1024,
                    "thinkingConfig": {"thinkingBudget": 0},  # sin "thinking" → más barato/rápido
                },
            }
        ).encode("utf-8")
        url = _ENDPOINT.format(model=settings.gemini_model)

        claves = settings.gemini_api_keys
        solo_cuota = True  # si TODAS fallan por cuota → _CuotaAgotada; si no → RuntimeError
        ultimo: Exception | None = None
        for i, clave in enumerate(claves, start=1):
            try:
                data = _invocar(url, body, clave)
            except _CuotaAgotada as exc:
                ultimo = exc
                logger.warning(
                    "Tribunal Gemini: clave %d/%d agotada (429), probando la siguiente.",
                    i, len(claves),
                )
                continue
            except Exception as exc:  # clave inválida / red / etc. → probar la siguiente
                ultimo, solo_cuota = exc, False
                logger.warning(
                    "Tribunal Gemini: clave %d/%d falló (%s), probando la siguiente.",
                    i, len(claves), exc,
                )
                continue
            return parsear_preguntas(_texto_de_respuesta(data), n)

        if solo_cuota:
            raise _CuotaAgotada
        raise RuntimeError(f"Todas las claves de Gemini fallaron: {ultimo}")


def _invocar(url: str, body: bytes, clave: str) -> dict[str, Any]:
    """Llama a Gemini con una clave. HTTP 429 → _CuotaAgotada; otro error HTTP → RuntimeError."""
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", "x-goog-api-key": clave},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 (URL fija HTTPS)
            data: dict[str, Any] = json.loads(resp.read().decode("utf-8"))
            return data
    except urllib.error.HTTPError as exc:
        detalle = exc.read().decode("utf-8", errors="replace")
        if exc.code == 429 or "RESOURCE_EXHAUSTED" in detalle:
            raise _CuotaAgotada from exc
        raise RuntimeError(f"HTTP {exc.code}: {detalle[:200]}") from exc


def _texto_de_respuesta(data: dict[str, Any]) -> str:
    """Extrae el texto del primer candidato de la respuesta de Gemini (tolerante)."""
    try:
        partes = data["candidates"][0]["content"]["parts"]
    except (KeyError, IndexError, TypeError):
        return ""
    return "".join(p.get("text", "") for p in partes if isinstance(p, dict))
