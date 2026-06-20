"""Ejecuta todas las semillas de datos de desarrollo.

Uso (desde la raíz del backend):  python -m seed

Para añadir una semilla nueva: crea `seed/<algo>.py` con una corutina
`async def seed(db)` y agrégala a la lista SEMILLAS de abajo.
"""

import asyncio
from collections.abc import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import SessionLocal
from app.core.event_loop import new_event_loop
from seed import planes, usuarios

SEMILLAS: list[Callable[[AsyncSession], Awaitable[None]]] = [
    usuarios.seed,
    planes.seed,
]


async def main() -> None:
    async with SessionLocal() as db:
        for ejecutar_semilla in SEMILLAS:
            await ejecutar_semilla(db)
        await db.commit()
    print("Semillas aplicadas.")


if __name__ == "__main__":
    asyncio.run(main(), loop_factory=new_event_loop)
