"""Modelos ORM del submódulo Suscripciones (CU-02)."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, String, text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import EstadoSuscripcion
from app.models.base import Base, IdMixin, TimestampMixin


class PlanSuscripcion(Base, IdMixin, TimestampMixin):
    __tablename__ = "plan_suscripcion"

    nombre: Mapped[str] = mapped_column(String(120))
    precio: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    moneda: Mapped[str] = mapped_column(String(3))
    periodo_dias: Mapped[int] = mapped_column(Integer)
    activo: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))


class Suscripcion(Base, IdMixin, TimestampMixin):
    __tablename__ = "suscripcion"

    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuario.id"), index=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("plan_suscripcion.id"), index=True)
    estado: Mapped[EstadoSuscripcion] = mapped_column(
        SAEnum(EstadoSuscripcion, name="estado_suscripcion")
    )
    fecha_inicio: Mapped[datetime | None]
    fecha_fin: Mapped[datetime | None]
