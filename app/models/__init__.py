"""Paquete de modelos. Mantener mínimo para evitar imports circulares.

Para registrar TODAS las tablas en `Base.metadata` (Alembic, tests) se importa
`app.models.registry`, no este `__init__`.
"""

from app.models.base import Base

__all__ = ["Base"]
