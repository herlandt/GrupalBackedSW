"""Tribunal con Claude (Amazon Bedrock) — COMPLEMENTO de las plantillas, bajo costo.

Claude genera preguntas COHERENTES leyendo el contenido real del documento (resuelve la
incoherencia del enfoque por plantillas). Para gastar lo mínimo:

- Solo se usa para GENERAR preguntas; la EVALUACIÓN sigue por similitud local/Titan (heredada
  de `DocumentoTribunal`), sin tokens de Claude.
- Se manda únicamente la prosa limpia de las secciones (recortada), no el documento entero;
  `max_tokens` de salida pequeño; modelo Haiku (el más barato).
- Si Claude falla, no hay acceso o devuelve algo inválido, cae automáticamente a las
  plantillas mejoradas (`DocumentoTribunal`). Nunca rompe el flujo.

Se activa con `settings.tribunal_llm_backend == "claude"`.
"""

from __future__ import annotations

import logging

import anyio

from app.core.config import settings
from app.integrations.analysis.extraction import extraer_texto, particionar, resolver_path
from app.integrations.aws.session import get_aws_client
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


class ClaudeTribunal(DocumentoTribunal):
    async def generar_preguntas(
        self, *, archivo_url: str, formato: str, nivel_dificultad: str
    ) -> list[PreguntaGeneradaDTO]:
        # Lectura del documento + llamada a Bedrock son BLOQUEANTES → a un hilo.
        return await anyio.to_thread.run_sync(
            self._generar_con_claude, archivo_url, formato, nivel_dificultad
        )

    def _generar_con_claude(
        self, archivo_url: str, formato: str, nivel_dificultad: str
    ) -> list[PreguntaGeneradaDTO]:
        try:
            texto = extraer_texto(resolver_path(archivo_url), formato)
        except Exception:  # archivo ilegible → plantillas
            return self._generar(archivo_url, formato, nivel_dificultad)
        secciones = particionar(texto) if texto.strip() else {}
        contexto = construir_contexto(secciones)
        if not contexto:  # documento sin prosa aprovechable → plantillas (genéricas)
            return self._generar(archivo_url, formato, nivel_dificultad)
        try:
            preguntas = self._preguntas_claude(contexto, nivel_dificultad)
        except Exception as exc:  # sin acceso a Bedrock / throttling / respuesta inválida
            logger.warning("Tribunal Claude no disponible, uso plantillas: %s", exc)
            return self._generar(archivo_url, formato, nivel_dificultad)
        if not preguntas:
            return self._generar(archivo_url, formato, nivel_dificultad)
        return [PreguntaGeneradaDTO(orden=i, texto=t) for i, t in enumerate(preguntas, start=1)]

    def _preguntas_claude(self, contexto: str, nivel_dificultad: str) -> list[str]:
        n = n_preguntas(nivel_dificultad)
        cliente = get_aws_client("bedrock-runtime")
        resp = cliente.converse(
            modelId=settings.tribunal_claude_model,
            system=[{"text": SISTEMA}],
            messages=[{"role": "user", "content": [{"text": construir_prompt(contexto, n)}]}],
            inferenceConfig={"maxTokens": 700, "temperature": 0.4},
        )
        texto = resp["output"]["message"]["content"][0]["text"]
        return parsear_preguntas(texto, n)
