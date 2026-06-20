"""Conexión a la base de datos: engine async, fábrica de sesiones y dependencia.

Única fuente de la sesión de base de datos. Cada petición obtiene su propia
sesión vía `Depends(get_db)`; nunca se comparte una sesión global entre peticiones.
"""

from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    pool_pre_ping=True,  # descarta conexiones muertas tras periodos de inactividad
)

SessionLocal = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,  # evita recargas implícitas (lazy load) tras el commit
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession]:
    """Abre una sesión por petición: confirma si todo va bien, revierte si falla."""
    async with SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# Alias de dependencia para inyectar la sesión en routers/services.
DbDep = Annotated[AsyncSession, Depends(get_db)]
