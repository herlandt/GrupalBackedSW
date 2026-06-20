"""Repositorio base genérico para los submódulos (SQLAlchemy 2.0 async).

Centraliza las operaciones comunes de acceso a datos. Recibe la sesión en el
constructor y NO confirma la transacción (lo hace `get_db` al final de la
petición); solo hace `flush` para obtener IDs generados.
"""

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ResourceNotFoundError
from app.models.base import Base


class BaseRepository[ModelT: Base]:
    model: type[ModelT]

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get(self, id_: int) -> ModelT | None:
        return await self.db.get(self.model, id_)

    async def get_or_404(self, id_: int) -> ModelT:
        obj = await self.get(id_)
        if obj is None:
            raise ResourceNotFoundError(f"{self.model.__name__} {id_} no existe")
        return obj

    async def list(self) -> Sequence[ModelT]:
        result = await self.db.execute(select(self.model))
        return result.scalars().all()

    async def add(self, obj: ModelT) -> ModelT:
        self.db.add(obj)
        await self.db.flush()
        return obj

    async def delete(self, obj: ModelT) -> None:
        await self.db.delete(obj)
        await self.db.flush()
