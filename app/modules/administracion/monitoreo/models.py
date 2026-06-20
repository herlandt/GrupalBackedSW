"""Modelos ORM del submódulo Monitoreo / Seguimiento (CU-07, RF-08)."""

from datetime import datetime

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import EstadoAvance
from app.models.base import Base, CreatedAtMixin, IdMixin


class AvanceFormal(Base, IdMixin, CreatedAtMixin):
    """Aprobación formal de etapas de avance del estudiante (RF-08)."""

    __tablename__ = "avance_formal"

    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuario.id"), index=True)
    etapa: Mapped[str] = mapped_column(String(120))
    estado: Mapped[EstadoAvance] = mapped_column(SAEnum(EstadoAvance, name="estado_avance"))
    aprobado_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"), index=True)
    fecha_aprobacion: Mapped[datetime | None]
