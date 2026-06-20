"""Esquemas Pydantic del submódulo Pagos (CU-03, CU-04)."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.core.enums import EstadoPago, EstadoSuscripcion


class CheckoutRequest(BaseModel):
    plan_id: int


class ConfirmarRequest(BaseModel):
    session_id: str


class CheckoutResponse(BaseModel):
    checkout_url: str


class SuscripcionEstado(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    estado: EstadoSuscripcion
    plan_id: int
    fecha_inicio: datetime | None
    fecha_fin: datetime | None


class PagoRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    monto: Decimal
    moneda: str
    estado: EstadoPago
    created_at: datetime
