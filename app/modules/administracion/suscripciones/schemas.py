"""Esquemas Pydantic del submódulo Suscripciones (CU-02)."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import EstadoSuscripcion


class PlanRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre: str
    precio: Decimal
    moneda: str
    periodo_dias: int
    activo: bool


class PlanCreate(BaseModel):
    nombre: str = Field(min_length=1, max_length=120)
    precio: Decimal = Field(gt=0)
    moneda: str = Field(default="USD", min_length=3, max_length=3)
    periodo_dias: int = Field(gt=0)


class PlanUpdate(BaseModel):
    nombre: str | None = Field(default=None, min_length=1, max_length=120)
    precio: Decimal | None = Field(default=None, gt=0)
    periodo_dias: int | None = Field(default=None, gt=0)
    activo: bool | None = None


class SuscripcionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    plan_id: int
    estado: EstadoSuscripcion
    fecha_inicio: datetime | None
    fecha_fin: datetime | None
