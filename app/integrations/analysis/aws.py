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
            observaciones=_observaciones(features, texto, temas),
            features=features,
            revision_sugerida=revision,
        )


def _observaciones(
    features: dict[str, float], texto: str, temas: list[str] | None = None
) -> list[ObservacionDTO]:
    """Traduce las features débiles en observaciones del informe (RF-01/RF-02)."""
    obs: list[ObservacionDTO] = []
    if features["coherencia_objetivos_resultados"] < 0.5:
        obs.append(
            ObservacionDTO(
                "COHERENCIA", "alta",
                "Baja coherencia entre los objetivos y los resultados/conclusiones.",
            )
        )
    if features["cohesion_secciones"] < 0.5:
        obs.append(
            ObservacionDTO(
                "COHERENCIA", "media",
                "Las secciones del documento presentan poca cohesión entre sí.",
            )
        )
    faltan = [s for s in SECCIONES_ESPERADAS if s not in particionar(texto)]
    if faltan:
        obs.append(
            ObservacionDTO(
                "NORMAS", "media",
                f"No se detectaron estas secciones esperadas: {', '.join(faltan)}.",
            )
        )
    if features["densidad_referencias"] < 0.3:
        obs.append(
            ObservacionDTO(
                "NORMAS", "baja", "Se detectaron pocas referencias o citas en el documento."
            )
        )
    if temas:
        obs.append(
            ObservacionDTO(
                "SUGERENCIA", "baja",
                f"Temas detectados en el documento: {', '.join(temas[:6])}.",
            )
        )
    if not obs:
        obs.append(
            ObservacionDTO(
                "SUGERENCIA", "baja",
                "El documento cumple los indicadores básicos; revisa la redacción final.",
            )
        )
    return obs
