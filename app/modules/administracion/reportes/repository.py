"""Acceso a datos del submódulo Reportes (CU-05). Solo lectura/agregaciones.

Devuelve dataclasses 'planas' (capa DATOS) que luego renderizan los renderers.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select

from app.core.enums import EstadoPago
from app.core.repository import BaseRepository
from app.modules.administracion.pagos.models import Pago
from app.modules.administracion.usuarios.models import Usuario


@dataclass(frozen=True)
class GananciasData:
    total: Decimal
    moneda: str
    cantidad_pagos: int


@dataclass(frozen=True)
class PagoPorEstudianteData:
    usuario_id: int
    nombre: str
    email: str
    total_pagado: Decimal
    cantidad_pagos: int


@dataclass(frozen=True)
class PagoFilaData:
    """Una fila del historial de un usuario (para el export del estudiante, CU-04)."""

    fecha: datetime
    monto: Decimal
    moneda: str
    estado: str


class ReporteRepository(BaseRepository[Pago]):
    model = Pago

    async def ganancias_totales(self) -> GananciasData:
        """Suma de montos de pagos PAGADO. La moneda se toma del primer pago pagado."""
        stmt = (
            select(
                func.coalesce(func.sum(Pago.monto), 0),
                func.count(Pago.id),
                func.min(Pago.moneda),
            )
            .where(Pago.estado == EstadoPago.PAGADO)
        )
        total, cantidad, moneda = (await self.db.execute(stmt)).one()
        return GananciasData(
            total=Decimal(total),
            cantidad_pagos=int(cantidad),
            moneda=str(moneda) if moneda else "USD",
        )

    async def pagos_por_estudiante(self) -> Sequence[PagoPorEstudianteData]:
        """Total pagado y cantidad de pagos por usuario (solo pagos PAGADO)."""
        stmt = (
            select(
                Usuario.id,
                Usuario.nombre,
                Usuario.email,
                func.coalesce(func.sum(Pago.monto), 0),
                func.count(Pago.id),
            )
            .join(Pago, Pago.usuario_id == Usuario.id)
            .where(Pago.estado == EstadoPago.PAGADO)
            .group_by(Usuario.id, Usuario.nombre, Usuario.email)
            .order_by(func.sum(Pago.monto).desc())
        )
        filas = (await self.db.execute(stmt)).all()
        return [
            PagoPorEstudianteData(
                usuario_id=int(uid),
                nombre=str(nombre),
                email=str(email),
                total_pagado=Decimal(total),
                cantidad_pagos=int(cantidad),
            )
            for uid, nombre, email, total, cantidad in filas
        ]

    async def historial_de_usuario(self, usuario_id: int) -> Sequence[PagoFilaData]:
        """Todas las filas de pago de un usuario (para el export del propio estudiante)."""
        stmt = (
            select(Pago.created_at, Pago.monto, Pago.moneda, Pago.estado)
            .where(Pago.usuario_id == usuario_id)
            .order_by(Pago.created_at.desc())
        )
        filas = (await self.db.execute(stmt)).all()
        return [
            PagoFilaData(fecha=fecha, monto=Decimal(monto), moneda=str(moneda), estado=str(estado))
            for fecha, monto, moneda, estado in filas
        ]
