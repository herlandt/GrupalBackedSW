"""Adaptadores stub de análisis para desarrollo/test.

- `StubAnalysisQueue`: registra (log) el encolado sin SQS real.
- `StubAnalysisService`: devuelve un ResultadoAuditoria de ejemplo (coherencia + normas +
  sugerencia) sin llamar al microservicio real. El adaptador HTTP real se conecta por entorno.
"""

import logging

from app.integrations.analysis.port import (
    AnalisisResultadoDTO,
    AnalysisServicePort,
    ObservacionDTO,
)

logger = logging.getLogger(__name__)


class StubAnalysisQueue:
    async def enqueue_analysis(self, *, documento_id: int, version_id: int) -> None:
        logger.info(
            "Análisis encolado (stub): documento=%s version=%s", documento_id, version_id
        )


class StubAnalysisService(AnalysisServicePort):
    async def analizar(
        self, *, version_id: int, archivo_url: str, formato: str
    ) -> AnalisisResultadoDTO:
        return AnalisisResultadoDTO(
            nivel_documento="MEDIO",
            resumen="Análisis de ejemplo: revisar coherencia metodológica y formato de citas.",
            observaciones=[
                ObservacionDTO(
                    categoria="COHERENCIA",
                    severidad="alta",
                    descripcion="El objetivo general no se alinea con la pregunta planteada.",
                    ubicacion="Capítulo 1, sección 1.2",
                ),
                ObservacionDTO(
                    categoria="NORMAS",
                    severidad="media",
                    descripcion="Citas con formato inconsistente respecto a la norma declarada.",
                    ubicacion="Referencias",
                ),
                ObservacionDTO(
                    categoria="SUGERENCIA",
                    severidad="baja",
                    descripcion="Considera reforzar la justificación con datos recientes.",
                    ubicacion="Capítulo 1, sección 1.3",
                ),
            ],
        )
