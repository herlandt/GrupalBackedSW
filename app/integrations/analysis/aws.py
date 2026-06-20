"""Adaptador REAL del análisis documental sobre AWS (reemplaza `StubAnalysisService`).

Lee el documento, lo parte por secciones (map-reduce para cientos de páginas), calcula
las 6 features con AWS **Comprehend** + **Titan Embeddings**, y deja que la **IA
evaluadora propia** (`predictor`) DECIDA el nivel. Devuelve también observaciones
(RF-01/02) para el informe. Se activa con `settings.analysis_backend == "aws"`.
"""

from __future__ import annotations

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
from app.integrations.aws.session import get_boto_session
from app.ml import predictor, rubrica


class AwsAnalysisService:
    async def analizar(
        self, *, version_id: int, archivo_url: str, formato: str
    ) -> AnalisisResultadoDTO:
        try:
            texto = extraer_texto(resolver_path(archivo_url), formato)
        except Exception as exc:  # archivo ilegible / formato roto
            raise AnalysisServiceError(f"No se pudo leer el documento: {exc}") from exc
        if not texto.strip():
            raise AnalysisServiceError("El documento no contiene texto legible")

        # EXTRAE con AWS (mide); la evaluadora DECIDE.
        session = get_boto_session()
        features = DocumentoFeatures(
            session.client("comprehend"), session.client("bedrock-runtime")
        ).calcular(texto)

        juicio = predictor.predecir("documento", features)
        nivel = str(juicio["nivel"])
        mejoras = rubrica.consejos("documento", list(juicio["factores_a_reforzar"]), features)
        guia = "; ".join(mejoras) or "—"
        revision = bool(juicio["revision_sugerida"])
        nota = " ⚠️ Caso límite (confianza baja): conviene una revisión humana." if revision else ""
        return AnalisisResultadoDTO(
            nivel_documento=nivel,
            resumen=f"Nivel del documento: {nivel}. Para mejorar: {guia}.{nota}",
            observaciones=_observaciones(features, texto),
            features=features,
            revision_sugerida=revision,
        )


def _observaciones(features: dict[str, float], texto: str) -> list[ObservacionDTO]:
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
    if not obs:
        obs.append(
            ObservacionDTO(
                "SUGERENCIA", "baja",
                "El documento cumple los indicadores básicos; revisa la redacción final.",
            )
        )
    return obs
