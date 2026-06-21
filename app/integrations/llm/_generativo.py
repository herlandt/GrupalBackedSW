"""Helpers compartidos por los adaptadores generativos del tribunal (Claude, Gemini, ...).

Todos siguen el mismo patrón barato y coherente: arman un contexto con la prosa LIMPIA de las
secciones del documento (sin índice/ruido), piden N preguntas de defensa como array JSON, y
parsean la respuesta de forma tolerante. La evaluación NO usa LLM (sigue por similitud local),
y si el proveedor falla, el adaptador cae a las plantillas de `DocumentoTribunal`.
"""

from __future__ import annotations

import json

from app.integrations.llm.documento import _MAX_TOTAL, _SECCIONES_ORDEN, _cuerpo_analizable

# Etiquetas legibles de cada sección, para dar contexto al modelo.
_ETIQUETAS = {
    "problema": "Planteamiento del problema",
    "objetivos": "Objetivos",
    "metodologia": "Metodología",
    "resultados": "Resultados",
    "conclusiones": "Conclusiones",
}
_MAX_CHARS_SECCION = 1200  # recorte por sección (controla tokens de entrada → costo)
_MAX_CHARS_TOTAL = 6000  # tope global del contexto enviado al modelo

SISTEMA = (
    "Eres un miembro de un tribunal de defensa de tesis. A partir de fragmentos REALES del "
    "documento, formulas preguntas de defensa claras, específicas y coherentes con el "
    "contenido (no genéricas, no sobre términos sueltos). Cada pregunta debe poder "
    "responderse defendiendo la tesis. Responde ÚNICAMENTE con un array JSON de strings en "
    "español, sin texto adicional."
)


def n_preguntas(nivel_dificultad: str) -> int:
    return _MAX_TOTAL.get(nivel_dificultad, 5)


def construir_contexto(secciones: dict[str, str]) -> str:
    """Arma el contexto: prosa LIMPIA y recortada de cada sección de tesis."""
    partes: list[str] = []
    total = 0
    for clave in _SECCIONES_ORDEN:
        cuerpo = _cuerpo_analizable(secciones.get(clave, "")).strip()
        if not cuerpo:
            continue
        bloque = f"## {_ETIQUETAS.get(clave, clave)}\n{cuerpo[:_MAX_CHARS_SECCION]}"
        if total + len(bloque) > _MAX_CHARS_TOTAL:
            break
        partes.append(bloque)
        total += len(bloque)
    return "\n\n".join(partes)


def construir_prompt(contexto: str, n: int) -> str:
    return (
        f"Genera exactamente {n} preguntas de defensa para esta tesis, repartidas entre sus "
        "secciones (problema, objetivos, metodología, resultados, conclusiones) según el "
        "contenido disponible. Devuelve solo el array JSON.\n\n"
        f"Fragmentos del documento:\n{contexto}"
    )


def parsear_preguntas(texto: str, n: int) -> list[str]:
    """Extrae el array JSON de strings de la respuesta del modelo, tolerante a envoltura."""
    inicio, fin = texto.find("["), texto.rfind("]")
    if inicio == -1 or fin == -1 or fin <= inicio:
        return []
    try:
        datos = json.loads(texto[inicio : fin + 1])
    except json.JSONDecodeError:
        return []
    preguntas = [str(p).strip() for p in datos if isinstance(p, str) and str(p).strip()]
    return preguntas[:n]
