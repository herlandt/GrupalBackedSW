"""Modelos ORM del submódulo Pagos (CU-03, CU-04)."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import EstadoPago
from app.models.base import Base, IdMixin, TimestampMixin


class Pago(Base, IdMixin, TimestampMixin):
    __tablename__ = "pago"

    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuario.id"), index=True)
    suscripcion_id: Mapped[int | None] = mapped_column(ForeignKey("suscripcion.id"), index=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("plan_suscripcion.id"), index=True)
    monto: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    moneda: Mapped[str] = mapped_column(String(3))
    estado: Mapped[EstadoPago] = mapped_column(SAEnum(EstadoPago, name="estado_pago"))
    stripe_checkout_session_id: Mapped[str | None] = mapped_column(String(255), unique=True)
    stripe_payment_intent_id: Mapped[str | None] = mapped_column(String(255))


class EventoWebhook(Base, IdMixin):
    """Idempotencia de webhooks de Stripe: un evento se procesa una sola vez."""

    __tablename__ = "evento_webhook"

    stripe_event_id: Mapped[str] = mapped_column(String(255), unique=True)
    pago_id: Mapped[int | None] = mapped_column(ForeignKey("pago.id"), index=True)
    tipo: Mapped[str] = mapped_column(String(120))
    processed_at: Mapped[datetime] = mapped_column(server_default=func.now())
