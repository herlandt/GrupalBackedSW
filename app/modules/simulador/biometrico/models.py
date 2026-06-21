"""Modelos ORM del submódulo Biométrico — ExpoLens (RF-03, RF-04, RF-05)."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import ForeignKey, Index, Integer, Numeric, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CreatedAtMixin, IdMixin


class MetricaBiometrica(Base, IdMixin, CreatedAtMixin):
    __tablename__ = "metrica_biometrica"
    # Índice compuesto: las lecturas filtran por sesión y ordenan por momento; con el
    # análisis continuo cada sesión acumula muchas filas, así que cubre filtro + orden.
    __table_args__ = (Index("ix_metrica_biometrica_sesion_momento", "sesion_id", "momento"),)

    sesion_id: Mapped[int] = mapped_column(ForeignKey("sesion_simulacion.id"))
    postura_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    muletillas_conteo: Mapped[int] = mapped_column(Integer)
    ritmo_wpm: Mapped[int | None] = mapped_column(Integer)
    # Pausas largas medidas desde el timing de Transcribe (RF-05). 0 en filas de video.
    pausas_largas_conteo: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    contacto_visual_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    # Texto reconocido por Transcribe en este segmento (RF-05). Vacío en filas de solo video.
    # Se concatena al cerrar la sesión para medir la coherencia discurso↔documento.
    transcripcion_texto: Mapped[str] = mapped_column(Text, default="", server_default="")
    momento: Mapped[datetime]
