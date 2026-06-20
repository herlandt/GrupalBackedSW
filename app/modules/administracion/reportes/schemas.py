"""Esquemas del submódulo Reportes (CU-05) — solo lectura/resumen para el gráfico."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class FilaPagoEstudiante(BaseModel):
    """Una fila del resumen 'pagos por estudiante' (para el gráfico del frontend)."""

    model_config = ConfigDict(from_attributes=True)

    usuario_id: int
    nombre: str
    email: str
    total_pagado: Decimal
    cantidad_pagos: int


class ResumenGanancias(BaseModel):
    """Totales de ganancias (pagos en estado PAGADO)."""

    total: Decimal
    moneda: str
    cantidad_pagos: int
    desde: datetime | None = None
    hasta: datetime | None = None


class ResumenReportes(BaseModel):
    """Payload del endpoint de resumen JSON que consume chart.js en el frontend."""

    ganancias: ResumenGanancias
    por_estudiante: list[FilaPagoEstudiante]
