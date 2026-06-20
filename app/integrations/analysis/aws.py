"""Adaptador REAL del análisis documental sobre AWS (reemplaza `StubAnalysisService`).

Lee el documento, lo parte por secciones (map-reduce para cientos de páginas), calcula
las 6 features con AWS **Comprehend** + **Titan Embeddings**, y deja que la **IA
evaluadora propia** (`predictor`) DECIDA el nivel. Devuelve también observaciones
(RF-01/02) para el informe. Se activa con `settings.analysis_backend == "aws"`.
"""

from __future__ import annotations

import anyio

from app.integrations.analysis.extraction import (
    SECCIONES_ESPERADAS,
    extraer_texto,
    particionar,
    resolver_path,
)
from app.integrations.analysis.features import DocumentoFeatures
from app.integrations.analysis.port import (
    AnalisisResultadoDTO,
    AnalysisServiceError,
    ObservacionDTO,
)
from app.integrations.analysis.textract import ocr_pdf
from app.integrations.aws.session import get_aws_client
from app.ml import predictor, rubrica


class AwsAnalysisService:
    async def analizar(
        self, *, version_id: int, archivo_url: str, formato: str
    ) -> AnalisisResultadoDTO:
        # El análisis es BLOQUEANTE (lectura de PDF + boto3 sync + RandomForest, ~1-2 min);
        # lo movemos a un hilo para no congelar el event loop del servidor mientras corre.
        return await anyio.to_thread.run_sync(self._analizar, archivo_url, formato)

    def _analizar(self, archivo_url: str, formato: str) -> AnalisisResultadoDTO:
        path = resolver_path(archivo_url)
        try:
            texto = extraer_texto(path, formato)
        except Exception as exc:  # archivo ilegible / formato roto
            raise AnalysisServiceError(f"No se pudo leer el documento: {exc}") from exc
        # PDF escaneado (sin capa de texto) → OCR con Textract como fallback.
        if formato.upper() == "PDF" and len(texto.strip()) < 100:
            texto = ocr_pdf(path) or texto
        if not texto.strip():
            raise AnalysisServiceError("El documento no contiene texto legible")

        # EXTRAE con AWS (mide); la evaluadora DECIDE. Clientes cacheados con reintentos.
        extractor = DocumentoFeatures(
            get_aws_client("comprehend"), get_aws_client("bedrock-runtime")
        )
        features = extractor.calcular(texto)
        temas = extractor.temas_clave(texto)

        juicio = predictor.predecir("documento", features)
        nivel = str(juicio["nivel"])
        mejoras = rubrica.consejos("documento", list(juicio["factores_a_reforzar"]), features)
        guia = "; ".join(mejoras) or "—"
        revision = bool(juicio["revision_sugerida"])
        nota = " ⚠️ Caso límite (confianza baja): conviene una revisión humana." if revision else ""
        return AnalisisResultadoDTO(
            nivel_documento=nivel,
            resumen=f"Nivel del documento: {nivel}. Para mejorar: {guia}.{nota}",
            observaciones=_observaciones(features, texto, temas, mejoras),
            features=features,
            revision_sugerida=revision,
        )


def _observaciones(
    features: dict[str, float],
    texto: str,
    temas: list[str] | None = None,
    consejos: list[str] | None = None,
) -> list[ObservacionDTO]:
    """Traduce features débiles + consejos del modelo en observaciones ACCIONABLES.

    Cada observación dice QUÉ pasa y QUÉ HACER (RF-01/RF-02); las SUGERENCIAS son los
    consejos priorizados por la IA evaluadora (qué reforzar primero para subir de nivel).
    """
    obs: list[ObservacionDTO] = []
    if features["coherencia_objetivos_resultados"] < 0.5:
        obs.append(
            ObservacionDTO(
                "COHERENCIA", "alta",
                "Baja coherencia entre los objetivos y los resultados/conclusiones. "
                "Qué hacer: asegúrate de que cada objetivo tenga un resultado que lo responda "
                "y que las conclusiones se deriven de esos resultados.",
            )
        )
    if features["cohesion_secciones"] < 0.5:
        obs.append(
            ObservacionDTO(
                "COHERENCIA", "media",
                "Las secciones presentan poca cohesión entre sí. Qué hacer: agrega frases de "
                "enlace entre secciones y un hilo argumental que conecte introducción, "
                "desarrollo y conclusiones.",
            )
        )
    faltan = [s for s in SECCIONES_ESPERADAS if s not in particionar(texto)]
    if faltan:
        obs.append(
            ObservacionDTO(
                "NORMAS", "media",
                f"No se detectaron estas secciones esperadas: {', '.join(faltan)}. "
                "Qué hacer: agrégalas o titúlalas claramente según la estructura exigida.",
            )
        )
    if features["densidad_referencias"] < 0.3:
        obs.append(
            ObservacionDTO(
                "NORMAS", "baja",
                "Se detectaron pocas referencias o citas. Qué hacer: respalda las afirmaciones "
                "clave con citas y verifica que todas aparezcan en la bibliografía.",
            )
        )
    # SUGERENCIAS accionables: lo que la IA evaluadora recomienda reforzar primero.
    for c in consejos or []:
        obs.append(ObservacionDTO("SUGERENCIA", "media", f"Para subir de nivel: {c}."))
    if temas:
        obs.append(
            ObservacionDTO(
                "SUGERENCIA", "baja",
                f"Temas detectados: {', '.join(temas[:6])}. Qué hacer: revisa que el documento "
                "los defina y desarrolle con claridad.",
            )
        )
    if not obs:
        obs.append(
            ObservacionDTO(
                "SUGERENCIA", "baja",
                "El documento cumple los indicadores básicos; revisa la redacción final y la "
                "consistencia de las citas.",
            )
        )
    return obs
