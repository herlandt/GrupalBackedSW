"""Modelos ORM del submódulo Tribunal (CU-16, CU-17, RF-06, RF-07)."""

from decimal import Decimal
from typing import Any

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import NivelPreparacion
from app.models.base import Base, CreatedAtMixin, IdMixin


class PreguntaTribunal(Base, IdMixin, CreatedAtMixin):
    __tablename__ = "pregunta_tribunal"

    sesion_id: Mapped[int] = mapped_column(ForeignKey("sesion_simulacion.id"), index=True)
    orden: Mapped[int] = mapped_column(Integer)
    texto: Mapped[str] = mapped_column(Text)


class RespuestaEstudiante(Base, IdMixin, CreatedAtMixin):
    __tablename__ = "respuesta_estudiante"

    pregunta_id: Mapped[int] = mapped_column(ForeignKey("pregunta_tribunal.id"), unique=True)
    texto: Mapped[str | None] = mapped_column(Text)
    audio_url: Mapped[str | None] = mapped_column(String(500))


class EvaluacionRespuesta(Base, IdMixin, CreatedAtMixin):
    __tablename__ = "evaluacion_respuesta"

    respuesta_id: Mapped[int] = mapped_column(ForeignKey("respuesta_estudiante.id"), unique=True)
    puntuacion: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    observaciones: Mapped[str | None] = mapped_column(Text)
    profundidad: Mapped[str | None] = mapped_column(String(20))


class ResultadoSimulacion(Base, IdMixin, CreatedAtMixin):
    __tablename__ = "resultado_simulacion"

    sesion_id: Mapped[int] = mapped_column(ForeignKey("sesion_simulacion.id"), unique=True)
    nivel_defensa: Mapped[NivelPreparacion] = mapped_column(
        SAEnum(NivelPreparacion, name="nivel_defensa")
    )
    oratoria_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    comunicacion_no_verbal_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    dominio_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    resumen: Mapped[str | None] = mapped_column(Text)
    # Confianza calibrada de la IA y vector de features que la produjo (trazabilidad +
    # futuro reentrenamiento con datos reales).
    confianza: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    features: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
