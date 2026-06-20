"""Extracción de texto y partición por secciones de la tesis (local, sin AWS).

Permite procesar documentos de cientos de páginas **por partes** (map-reduce): se extrae
el texto, se parte en secciones lógicas y cada parte se analiza por separado. No hay
límite de "tokens" — eso es de los LLM; aquí solo se procesa más texto agregando.
"""

from __future__ import annotations

import re
from pathlib import Path

from app.core.config import settings

# Encabezados que delimitan las secciones esperadas de una tesis (en español). Incluye
# títulos descriptivos reales ("PRESENTACIÓN Y ANÁLISIS DE RESULTADOS", "MARCO METODOLÓGICO").
_SECCIONES: dict[str, tuple[str, ...]] = {
    "introduccion": ("introduccion", "introducción", "introduction"),
    "problema": (
        "planteamiento",
        "problema",
        "pregunta de investigacion",
        "marco teorico",
        "marco teórico",
    ),
    "objetivos": ("objetivos", "objetivo general", "objetivo"),
    "metodologia": (
        "metodologia",
        "metodología",
        "metodo",
        "materiales y metodos",
        "marco metodologico",
        "marco metodológico",
    ),
    "resultados": (
        "resultados",
        "hallazgos",
        "presentacion y analisis",
        "presentación y análisis",
        "analisis de resultados",
        "análisis de resultados",
        "discusion",
        "discusión",
    ),
    "conclusiones": (
        "conclusiones",
        "conclusion",
        "conclusiones y recomendaciones",
        "recomendaciones",
    ),
    "referencias": ("referencias", "bibliografia", "bibliografía"),
}

SECCIONES_ESPERADAS: tuple[str, ...] = (
    "introduccion",
    "objetivos",
    "metodologia",
    "resultados",
    "conclusiones",
)


def resolver_path(archivo_url: str) -> Path:
    """Convierte la URL de storage (`/media/...`) en una ruta local legible."""
    if archivo_url.startswith("/media/"):
        return Path(settings.local_media_dir) / archivo_url[len("/media/") :]
    return Path(archivo_url)


def extraer_texto(path: Path, formato: str) -> str:
    """Extrae el texto plano de un DOCX o PDF."""
    if formato.upper() == "DOCX":
        from docx import Document

        documento = Document(str(path))
        return "\n".join(p.text for p in documento.paragraphs)

    from pypdf import PdfReader

    reader = PdfReader(str(path))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def particionar(texto: str) -> dict[str, str]:
    """Parte el texto en secciones según encabezados. Lo no clasificado va a 'otros'."""
    secciones: dict[str, list[str]] = {}
    actual = "otros"
    for linea in texto.splitlines():
        clave = _seccion_de_encabezado(linea)
        if clave is not None:
            actual = clave
            continue
        secciones.setdefault(actual, []).append(linea)
    return {k: "\n".join(v).strip() for k, v in secciones.items() if "\n".join(v).strip()}


def _seccion_de_encabezado(linea: str) -> str | None:
    """Detecta si una línea es un encabezado de sección y devuelve su clave.

    Tolera formatos reales de tesis: 'CAPÍTULO I. INTRODUCCIÓN', 'V. CONCLUSIONES...',
    '4. PRESENTACIÓN Y ANÁLISIS DE RESULTADOS', títulos en MAYÚSCULAS. El match es ANCLADO
    (startswith tras quitar prefijos) para no clasificar prosa del cuerpo como encabezado.
    """
    raw = linea.strip()
    s = raw.lower()
    if not s or len(s) > 80:
        return None
    # Un encabezado es corto o va en MAYÚSCULAS; así evitamos falsos positivos en prosa.
    if not (raw.isupper() or len(s.split()) <= 8):
        return None
    s = re.sub(r"^(cap[ií]tulo|secci[óo]n)\b[\s.:)\-]*", "", s)  # quita 'CAPÍTULO'/'SECCIÓN'
    s = re.sub(r"^[ivxlcdm]+[\s.:)\-]+", "", s)  # quita numeral romano (I, III, IV, V...)
    s = re.sub(r"^[\d.\s):\-]+", "", s).strip()  # quita numeración "1.", "2.3 "
    for clave, variantes in _SECCIONES.items():
        if any(s.startswith(v) for v in variantes):
            return clave
    return None


def trozos(texto: str, max_bytes: int = 4500) -> list[str]:
    """Parte un texto en trozos bajo el límite de Comprehend (5000 bytes UTF-8)."""
    if not texto.strip():
        return []
    resultado: list[str] = []
    actual = ""
    for parrafo in texto.split("\n"):
        for unidad in _dividir_largo(parrafo, max_bytes):
            candidato = f"{actual}\n{unidad}" if actual else unidad
            if actual and len(candidato.encode("utf-8")) > max_bytes:
                resultado.append(actual)
                actual = unidad
            else:
                actual = candidato
    if actual:
        resultado.append(actual)
    return resultado


def _dividir_largo(texto: str, max_bytes: int) -> list[str]:
    """Parte por palabras un fragmento que por sí solo ya excede el límite."""
    if len(texto.encode("utf-8")) <= max_bytes:
        return [texto]
    partes: list[str] = []
    actual = ""
    for palabra in texto.split(" "):
        candidato = f"{actual} {palabra}" if actual else palabra
        if actual and len(candidato.encode("utf-8")) > max_bytes:
            partes.append(actual)
            actual = palabra
        else:
            actual = candidato
    if actual:
        partes.append(actual)
    return partes
