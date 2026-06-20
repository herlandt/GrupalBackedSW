"""Modelos ORM del submódulo Ética (CU-12)."""

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import EstadoAlertaEtica
from app.models.base import Base, IdMixin, TimestampMixin


class AlertaEtica(Base, IdMixin, TimestampMixin):
    __tablename__ = "alerta_etica"

    version_id: Mapped[int] = mapped_column(ForeignKey("version_documento.id"), index=True)
    tipo: Mapped[str] = mapped_column(String(120))
    fragmento: Mapped[str | None] = mapped_column(Text)
    estado: Mapped[EstadoAlertaEtica] = mapped_column(
        SAEnum(EstadoAlertaEtica, name="estado_alerta_etica")
    )
    decision_admin_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"), index=True)
