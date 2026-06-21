"""Tribunal SIN LLM generativo: preguntas y evaluación a partir del CONTENIDO REAL del
documento (extracción de secciones + frases clave de Comprehend + embeddings Titan).

No requiere Bedrock Claude ni habilitar acceso a un modelo generativo: las preguntas se
construyen con plantillas rellenadas con frases clave de cada sección de la tesis, y la
evaluación mide qué tan PERTINENTE (similitud semántica con la pregunta, que ya incorpora
contenido del documento) y SUSTANCIAL es la respuesta. Se activa con
`settings.tribunal_llm_backend == "aws"`.
"""

from __future__ import annotations

import logging
import random

import anyio

from app.integrations.analysis.extraction import extraer_texto, particionar, resolver_path
from app.integrations.analysis.features import DocumentoFeatures
from app.integrations.aws.session import get_aws_client
from app.integrations.llm.port import EvaluacionDTO, PreguntaGeneradaDTO, TribunalLLMPort
from app.integrations.llm.stub import _PLANTILLA  # plantillas genéricas de respaldo

logger = logging.getLogger(__name__)

# Plantillas POR SECCIÓN: {frase} se rellena con una frase clave REAL de esa sección. Hay
# varias por sección y se eligen AL AZAR (junto con la frase) para que cada sesión varíe.
_PREGUNTAS_SECCION: dict[str, list[str]] = {
    "problema": [
        "Planteas el problema en torno a «{frase}». ¿Por qué es relevante investigarlo?",
        "¿Qué vacío o necesidad justifica estudiar «{frase}»?",
        "¿Cómo delimitaste el alcance de «{frase}» en tu investigación?",
        "¿Qué antecedentes te llevaron a centrarte en «{frase}»?",
    ],
    "objetivos": [
        "Tu objetivo apunta a «{frase}». ¿Cómo lo abordaste metodológicamente?",
        "¿En qué medida consideras logrado el objetivo sobre «{frase}»?",
        "¿Qué indicadores usaste para medir «{frase}»?",
        "¿Cómo se conecta «{frase}» con tu pregunta de investigación?",
    ],
    "metodologia": [
        "Usas «{frase}» en tu metodología. ¿Por qué elegiste ese enfoque frente a alternativas?",
        "¿Cómo garantizaste la validez y confiabilidad al trabajar con «{frase}»?",
        "¿Qué limitaciones tuvo emplear «{frase}» y cómo las mitigaste?",
        "Explica el procedimiento que seguiste con «{frase}».",
    ],
    "resultados": [
        "Sobre tu resultado «{frase}»: ¿qué evidencia lo respalda?",
        "¿Cómo interpretas «{frase}» a la luz de tu marco teórico?",
        "¿«{frase}» era el resultado esperado? Justifica.",
        "¿Qué tan generalizable es «{frase}» más allá de tu muestra?",
    ],
    "conclusiones": [
        "Tu conclusión sobre «{frase}»: ¿en qué medida responde a tu pregunta de investigación?",
        "¿Qué limitaciones reconoces respecto a «{frase}»?",
        "¿Qué líneas de trabajo futuro abre «{frase}»?",
        "¿Cómo defenderías «{frase}» ante una postura crítica?",
    ],
}

_SECCIONES_ORDEN = ("problema", "objetivos", "metodologia", "resultados", "conclusiones")
# Preguntas por sección y tope total según el nivel de dificultad (RF-06).
_POR_SECCION = {"EXPLORACION": 1, "ESTANDAR": 1, "RIGUROSO": 2}
_MAX_TOTAL = {"EXPLORACION": 3, "ESTANDAR": 5, "RIGUROSO": 8}


def _generic(nivel: str) -> list[PreguntaGeneradaDTO]:
    """Respaldo genérico por nivel cuando el documento no es legible/clasificable."""
    textos = _PLANTILLA.get(nivel, _PLANTILLA["ESTANDAR"])
    return [PreguntaGeneradaDTO(orden=i, texto=t) for i, t in enumerate(textos, start=1)]


def _resumen_corto(texto: str) -> str:
    """Primera frase significativa de una sección, como ancla si Comprehend no da frases."""
    frag = texto.strip().split(".")[0].strip()
    return (frag[:80] + "…") if len(frag) > 80 else frag or "tu investigación"


# Determinantes iniciales y palabras estructurales/genéricas que ensucian las frases clave.
_ARTICULOS = {"el", "la", "los", "las", "un", "una", "unos", "unas", "lo", "su", "sus", "este",
              "esta", "estos", "estas", "ese", "esa", "del", "de"}
_GENERICAS = {"figura", "figuras", "tabla", "tablas", "cuadro", "cuadros", "grafico", "gráfico",
              "anexo", "anexos", "pagina", "página", "fuente", "autor", "año", "años", "ejemplo",
              "dato", "datos", "valor", "valores", "parte", "partes", "caso", "casos", "cosa",
              # medidas/genéricas y nombres de sección (que harían preguntas circulares)
              "cantidad", "cantidades", "efecto", "efectos", "nivel", "niveles", "total", "totales",
              "promedio", "medida", "medidas", "resultado", "resultados", "objetivo", "objetivos",
              "metodo", "método", "metodologia", "metodología", "conclusion", "conclusión",
              "conclusiones", "introduccion", "introducción", "problema", "estudio", "trabajo"}


def _limpiar_frases(frases: list[str]) -> list[str]:
    """Limpia y prioriza frases clave de Comprehend para preguntas más naturales.

    Quita determinantes iniciales ('la muestra' -> 'muestra'), descarta frases muy cortas,
    numéricas o estructurales (figura/tabla/…) y ordena por ESPECIFICIDAD (más palabras y más
    largas primero), que suelen ser los conceptos sustantivos de la tesis.
    """
    limpias: list[str] = []
    vistas: set[str] = set()
    for f in frases:
        palabras = f.strip().lower().split()
        while palabras and palabras[0] in _ARTICULOS:
            palabras.pop(0)
        frase = " ".join(palabras).strip(" .,:;()«»\"'")
        # Descarta: cortas; largas o con puntos de relleno (líneas del índice del PDF);
        # genéricas; y casi-numéricas ("100 %", "2019"). Exige ≥3 letras.
        if (
            len(frase) < 4
            or len(frase) > 60
            or "…" in frase
            or "...." in frase
            or frase in _GENERICAS
            or sum(c.isalpha() for c in frase) < 3
        ):
            continue
        if frase in vistas:
            continue
        vistas.add(frase)
        limpias.append(frase)
    limpias.sort(key=lambda s: (len(s.split()), len(s)), reverse=True)
    return limpias


class DocumentoTribunal(TribunalLLMPort):
    async def generar_preguntas(
        self, *, archivo_url: str, formato: str, nivel_dificultad: str
    ) -> list[PreguntaGeneradaDTO]:
        # Lectura del documento + Comprehend son BLOQUEANTES → a un hilo.
        return await anyio.to_thread.run_sync(
            self._generar, archivo_url, formato, nivel_dificultad
        )

    def _generar(
        self, archivo_url: str, formato: str, nivel_dificultad: str
    ) -> list[PreguntaGeneradaDTO]:
        try:
            texto = extraer_texto(resolver_path(archivo_url), formato)
        except Exception:  # archivo ilegible / no encontrado -> respaldo genérico
            texto = ""
        secciones = particionar(texto) if texto.strip() else {}
        if not secciones:
            return _generic(nivel_dificultad)
        try:
            preguntas = self._desde_secciones(secciones, nivel_dificultad)
        except Exception as exc:  # AWS/Comprehend caído -> no romper: preguntas genéricas
            logger.warning("Tribunal: fallo extrayendo del documento, uso genéricas: %s", exc)
            return _generic(nivel_dificultad)
        if not preguntas:  # documento sin secciones reconocibles
            return _generic(nivel_dificultad)
        return [PreguntaGeneradaDTO(orden=i, texto=t) for i, t in enumerate(preguntas, start=1)]

    @staticmethod
    def _desde_secciones(secciones: dict[str, str], nivel_dificultad: str) -> list[str]:
        extractor = DocumentoFeatures(get_aws_client("comprehend"), None)
        por_seccion = _POR_SECCION.get(nivel_dificultad, 1)
        preguntas: list[str] = []
        usaron_fallback = 0
        for clave in _SECCIONES_ORDEN:  # orden lógico de la defensa
            cuerpo = secciones.get(clave, "").strip()
            if not cuerpo:
                continue
            # 1 llamada a Comprehend por sección (max_trozos=1): suficiente y mucho más barato.
            frases = _limpiar_frases(extractor.temas_clave(cuerpo, n=10, max_trozos=1))
            if not frases:
                frases = [_resumen_corto(cuerpo)]
                usaron_fallback += 1
            # Elige plantillas y frases AL AZAR (de las más específicas) sin repetir: cada
            # sesión produce un set DISTINTO, siempre anclado al contenido real del documento.
            plantillas = random.sample(
                _PREGUNTAS_SECCION[clave], k=min(por_seccion, len(_PREGUNTAS_SECCION[clave]))
            )
            pool = frases[: max(3, por_seccion)]  # conserva la priorización por especificidad
            elegidas = random.sample(pool, k=min(len(plantillas), len(pool)))
            for j, plantilla in enumerate(plantillas):
                preguntas.append(plantilla.format(frase=elegidas[j % len(elegidas)]))
        if usaron_fallback:
            logger.info("Tribunal: %d sección(es) usaron respaldo", usaron_fallback)
        return preguntas[: _MAX_TOTAL.get(nivel_dificultad, 5)]

    async def evaluar_respuesta(self, *, pregunta: str, respuesta: str) -> EvaluacionDTO:
        return await anyio.to_thread.run_sync(self._evaluar, pregunta, respuesta)

    def _evaluar(self, pregunta: str, respuesta: str) -> EvaluacionDTO:
        texto = respuesta.strip()
        if not texto:
            return EvaluacionDTO(
                puntuacion=0.0,
                observaciones="No se registró contenido en la respuesta.",
                profundidad="baja",
            )
        extractor = DocumentoFeatures(None, get_aws_client("bedrock-runtime"))
        # Pertinencia: la pregunta ya incorpora contenido real del documento, así que la
        # similitud respuesta↔pregunta refleja si el estudiante respondió a lo planteado.
        pertinencia = extractor.similitud(texto, pregunta)  # 0..1
        sustancia = min(1.0, len(texto) / 400.0)  # elaboración (extensión)
        punt = round(min(10.0, 10.0 * (0.6 * pertinencia + 0.4 * sustancia)), 2)
        profundidad = "alta" if punt >= 7 else "media" if punt >= 4 else "baja"
        obs = (
            "Aborda la pregunta con buen nivel de detalle."
            if punt >= 7
            else "Pertinente, pero conviene profundizar con más evidencia."
            if punt >= 4
            else "Respuesta breve o poco relacionada con lo preguntado."
        )
        return EvaluacionDTO(puntuacion=punt, observaciones=obs, profundidad=profundidad)
