"""Puerto de la IA evaluadora propia (microservicio) + DTOs neutrales.

El core agrega las señales de la sesión en `DefensaFeatures` y pide el juicio de la
dimensión `defensa` (Alto/Medio/Bajo). El microservicio real vive en
`microservicios/ia-evaluadora/` (`POST /evaluar/defensa`); en dev se usa un stub.
"""

from dataclasses import dataclass, field
from typing import Protocol


class EvaluadorServiceError(Exception):
    """La IA evaluadora falló o devolvió una respuesta inválida."""


@dataclass(frozen=True)
class DefensaFeatures:
    """Vector de features de la dimensión `defensa` (contrato del microservicio)."""

    fluidez: float  # 0..1  (↑ mejor)
    contacto_visual: float  # 0..1  (↑ mejor)
    estabilidad_postura: float  # 0..1  (↑ mejor)
    muletillas_por_min: float  # >=0   (↓ mejor)
    ritmo_ppm: float  # >0
    pausas_largas_por_min: float  # >=0   (↓ mejor)
    coherencia_discurso_documento: float  # 0..1  (↑ mejor) — discurso vs documento


@dataclass
class EvaluacionDefensaDTO:
    nivel: str  # "ALTO" | "MEDIO" | "BAJO"
    confianza: float
    factores_a_reforzar: list[str] = field(default_factory=list)
    revision_sugerida: bool = False  # caso de frontera: conviene revisión humana


class EvaluadorServicePort(Protocol):
    async def evaluar_defensa(self, features: DefensaFeatures) -> EvaluacionDefensaDTO:
        """Pide el nivel de la dimensión `defensa` a la IA evaluadora propia."""
        ...
