"""Modelos ORM del submódulo Simulaciones (CU-13, CU-14, CU-15)."""

from datetime import datetime

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import EstadoSesion, NivelDificultad
from app.models.base import Base, CreatedAtMixin, IdMixin


class SesionSimulacion(Base, IdMixin, CreatedAtMixin):
    __tablename__ = "sesion_simulacion"

    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuario.id"), index=True)
    version_documento_id: Mapped[int] = mapped_column(
        ForeignKey("version_documento.id"), index=True
    )
    nivel_dificultad: Mapped[NivelDificultad] = mapped_column(
        SAEnum(NivelDificultad, name="nivel_dificultad")
    )
    estado: Mapped[EstadoSesion] = mapped_column(SAEnum(EstadoSesion, name="estado_sesion"))
    fecha_inicio: Mapped[datetime]
    fecha_fin: Mapped[datetime | None]
