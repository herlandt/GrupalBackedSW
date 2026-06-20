"""Semilla de planes de suscripción (tarifas)."""

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.administracion.suscripciones.models import PlanSuscripcion

PLANES = [
    ("Plan Mensual", Decimal("9.99"), "USD", 30),
    ("Plan Semestral", Decimal("49.99"), "USD", 180),
]


async def seed(db: AsyncSession) -> None:
    for nombre, precio, moneda, periodo_dias in PLANES:
        existe = (
            await db.execute(select(PlanSuscripcion).where(PlanSuscripcion.nombre == nombre))
        ).scalar_one_or_none()
        if existe is not None:
            print(f"= plan ya existe: {nombre}")
            continue
        db.add(
            PlanSuscripcion(
                nombre=nombre, precio=precio, moneda=moneda, periodo_dias=periodo_dias, activo=True
            )
        )
        print(f"+ plan creado: {nombre} ({precio} {moneda})")
