"""Esquemas Pydantic — submódulo tribunal (CU-16, CU-17, RF-06, RF-07)."""

from datetime import datetime
from decimal import Decimal
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PreguntaRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sesion_id: int
    orden: int
    texto: str
    created_at: datetime


class RespuestaCreate(BaseModel):
    """CU-16: el estudiante responde por texto o por audio (al menos uno)."""

    texto: str | None = None
    audio_url: str | None = None
    # Contacto visual promedio (0-1) durante la respuesta, medido por cámara (Rekognition).
    # None = no se midió (cámara desactivada) -> no penaliza la nota.
    atencion: float | None = Field(default=None, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _al_menos_uno(self) -> Self:
        if not (self.texto and self.texto.strip()) and not self.audio_url:
            raise ValueError("Debes responder por texto o por audio.")
        return self


class RespuestaRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    pregunta_id: int
    texto: str | None
    audio_url: str | None
    created_at: datetime


class EvaluacionRead(BaseModel):
    """CU-17: retroalimentación de calidad, precisión y profundidad (RF-07)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    respuesta_id: int
    puntuacion: Decimal
    observaciones: str | None
    profundidad: str | None
    created_at: datetime
