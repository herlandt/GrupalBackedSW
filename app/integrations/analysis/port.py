"""Puerto de integración del análisis de documentos (contrato) + DTOs neutrales.

- `AnalysisServicePort`: pide el análisis al microservicio de IA de calificación y
  devuelve DTOs neutrales (sin dependencias del ORM).

El disparo del análisis NO usa una cola: tras subir/versionar un documento, el router
lanza `procesar_version` como tarea de fondo (post-commit). Ver `auditoria/router.py`.
"""

from dataclasses import dataclass, field
from typing import Protocol


class AnalysisServiceError(Exception):
    """El microservicio de análisis falló o devolvió una respuesta inválida."""


@dataclass
class ObservacionDTO:
    categoria: str  # "COHERENCIA" | "NORMAS" | "SUGERENCIA"
    severidad: str  # "alta" | "media" | "baja"
    descripcion: str
    ubicacion: str | None = None


@dataclass
class AlertaEticaDTO:
    """Posible incumplimiento ético detectado en el documento (CU-12)."""

    tipo: str  # p.ej. "INVESTIGACION_SERES_HUMANOS" | "EXPERIMENTACION_ANIMAL"
    fragmento: str | None = None


@dataclass
class AnalisisResultadoDTO:
    nivel_documento: str  # "ALTO" | "MEDIO" | "BAJO"
    resumen: str | None = None
    observaciones: list[ObservacionDTO] = field(default_factory=list)
    # Vector de features que alimentó a la IA: se persiste para trazabilidad y para
    # acumular un corpus REAL con el que reentrenar a futuro (no solo sintéticos).
    features: dict[str, float] = field(default_factory=dict)
    revision_sugerida: bool = False  # caso de frontera: conviene revisión humana
    # CU-12: alertas de ética detectadas durante el análisis (el motor las abre solo).
    alertas_etica: list[AlertaEticaDTO] = field(default_factory=list)


class AnalysisServicePort(Protocol):
    async def analizar(
        self, *, version_id: int, archivo_url: str, formato: str
    ) -> AnalisisResultadoDTO:
        """Pide al microservicio el análisis de una versión y devuelve el resultado neutral."""
        ...

    async def coherencia_discurso(
        self, *, archivo_url: str, formato: str, discurso: str
    ) -> float:
        """Similitud semántica (0..1) entre un DISCURSO (transcripción de la defensa) y el
        documento. Mide que lo expuesto cubra/no contradiga la tesis (RF-04/05 + RF-01)."""
        ...
