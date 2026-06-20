"""Puertos de integración del análisis de documentos (contratos) + DTOs neutrales.

- `AnalysisQueuePort`: encola la solicitud de análisis de una versión (SQS / stub).
- `AnalysisServicePort`: pide el análisis al microservicio de IA de calificación y
  devuelve DTOs neutrales (sin dependencias del ORM).
"""

from dataclasses import dataclass, field
from typing import Protocol


class AnalysisQueuePort(Protocol):
    async def enqueue_analysis(self, *, documento_id: int, version_id: int) -> None: ...


class AnalysisServiceError(Exception):
    """El microservicio de análisis falló o devolvió una respuesta inválida."""


@dataclass
class ObservacionDTO:
    categoria: str  # "COHERENCIA" | "NORMAS" | "SUGERENCIA"
    severidad: str  # "alta" | "media" | "baja"
    descripcion: str
    ubicacion: str | None = None


@dataclass
class AnalisisResultadoDTO:
    nivel_documento: str  # "ALTO" | "MEDIO" | "BAJO"
    resumen: str | None = None
    observaciones: list[ObservacionDTO] = field(default_factory=list)
    # Vector de features que alimentó a la IA: se persiste para trazabilidad y para
    # acumular un corpus REAL con el que reentrenar a futuro (no solo sintéticos).
    features: dict[str, float] = field(default_factory=dict)
    revision_sugerida: bool = False  # caso de frontera: conviene revisión humana


class AnalysisServicePort(Protocol):
    async def analizar(
        self, *, version_id: int, archivo_url: str, formato: str
    ) -> AnalisisResultadoDTO:
        """Pide al microservicio el análisis de una versión y devuelve el resultado neutral."""
        ...
