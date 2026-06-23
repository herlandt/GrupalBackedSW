"""Heurística de detección de alertas de ética e integridad (CU-12).

Sin LLM generativo: busca señales de investigación con **seres humanos**, **animales** o
**datos personales sensibles** y verifica si el documento declara las **salvaguardas**
correspondientes (consentimiento informado, comité de ética, anonimización...). Si aparece
una señal de riesgo SIN salvaguarda, se abre una alerta para que el administrador la revise.

Es deliberadamente conservadora (una alerta por categoría) y trabaja sobre el texto ya
extraído por el adaptador de análisis, igual estilo que el resto de features (sin terceros).
"""

from __future__ import annotations

import re

from app.integrations.analysis.port import AlertaEticaDTO

# Tabla 1:1 para emparejar sin acentos preservando la longitud (los índices siguen alineados
# con el texto original, así el fragmento se recorta del sitio correcto).
_ACENTOS = str.maketrans("áéíóúüñ", "aeiouun")

# tipo de incumplimiento -> palabras/expresiones que delatan el riesgo.
_RIESGOS: dict[str, tuple[str, ...]] = {
    "INVESTIGACION_SERES_HUMANOS": (
        "seres humanos", "sujetos humanos", "participantes", "pacientes",
        "encuestados", "entrevistados", "menores de edad", "ninos", "adolescentes",
        "muestra de personas", "voluntarios", "poblacion de estudio",
    ),
    "EXPERIMENTACION_ANIMAL": (
        "experimentacion animal", "modelo animal", "ensayo en animales",
        "ratas", "ratones", "roedores", "conejos", "especimenes animales",
    ),
    "DATOS_PERSONALES_SENSIBLES": (
        "datos personales", "datos sensibles", "historia clinica", "historias clinicas",
        "informacion medica", "datos biometricos", "datos geneticos",
        "orientacion sexual", "datos de salud",
    ),
}

# Si el documento menciona cualquiera de estas salvaguardas, asumimos que el tema ético
# está atendido y NO levantamos alertas (reduce los falsos positivos).
_SALVAGUARDAS: tuple[str, ...] = (
    "consentimiento informado", "asentimiento informado",
    "comite de etica", "comite de bioetica", "aprobacion etica", "aprobacion del comite",
    "anonimiz", "confidencialidad de los datos", "proteccion de datos",
    "declaracion de helsinki", "bienestar animal", "trato etico de los animales",
)


def _normalizar(texto: str) -> str:
    return texto.lower().translate(_ACENTOS)


def _fragmento(texto: str, norm: str, palabra: str) -> str:
    """~240 caracteres del texto ORIGINAL alrededor de la primera coincidencia."""
    i = norm.find(palabra)
    if i < 0:
        return ""
    ini = max(0, i - 80)
    fin = min(len(texto), i + len(palabra) + 160)
    return re.sub(r"\s+", " ", texto[ini:fin]).strip()


def detectar_alertas_etica(texto: str) -> list[AlertaEticaDTO]:
    """Una alerta por cada categoría de riesgo presente SIN salvaguarda declarada."""
    norm = _normalizar(texto)
    if not norm.strip():
        return []
    if any(s in norm for s in _SALVAGUARDAS):
        return []
    alertas: list[AlertaEticaDTO] = []
    for tipo, palabras in _RIESGOS.items():
        hit = next((p for p in palabras if p in norm), None)
        if hit:
            alertas.append(AlertaEticaDTO(tipo=tipo, fragmento=_fragmento(texto, norm, hit)))
    return alertas
