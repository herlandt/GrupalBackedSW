"""Puerto del LLM del tribunal virtual (servicio externo) + DTOs neutrales.

- `generar_preguntas`: genera preguntas desde el contenido real de la tesis (RF-06).
- `evaluar_respuesta`: califica calidad, precisión y profundidad de una respuesta (RF-07).

Los DTOs NO dependen del ORM. El LLM real (OpenAI/Anthropic/Bedrock/microservicio) se
conectará por entorno; aquí solo definimos el contrato y, en stub.py, el adaptador de dev.
"""

from dataclasses import dataclass
from typing import Protocol


class TribunalLLMError(Exception):
    """El LLM del tribunal falló o devolvió una respuesta inválida."""


@dataclass
class PreguntaGeneradaDTO:
    orden: int
    texto: str


@dataclass
class EvaluacionDTO:
    puntuacion: float  # 0–10 (se convierte a Decimal al persistir)
    observaciones: str | None = None
    profundidad: str | None = None  # "alta" | "media" | "baja"


class TribunalLLMPort(Protocol):
    async def generar_preguntas(
        self, *, archivo_url: str, formato: str, nivel_dificultad: str
    ) -> list[PreguntaGeneradaDTO]:
        """Genera preguntas a partir del documento de la tesis (en S3) y su nivel (RF-06)."""
        ...

    async def evaluar_respuesta(self, *, pregunta: str, respuesta: str) -> EvaluacionDTO:
        """Evalúa la respuesta del estudiante a una pregunta (RF-07)."""
        ...
