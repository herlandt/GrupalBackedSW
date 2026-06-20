"""Base declarativa y mixins comunes de los modelos ORM (SQLAlchemy 2.0).

`Base.metadata` reúne todas las tablas del sistema; es lo que Alembic compara
para autogenerar migraciones. Todos los modelos de dominio (que viven en sus
módulos) heredan de `Base` y de estos mixins.
"""

from datetime import datetime

from sqlalchemy import BigInteger, Identity, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base declarativa única de todos los modelos."""


class IdMixin:
    """Clave primaria entera autoincremental (BigInteger + IDENTITY)."""

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)


class TimestampMixin:
    """Marcas de tiempo de creación y última actualización, gestionadas por la DB."""

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class CreatedAtMixin:
    """Solo marca de creación (para entidades inmutables o de registro)."""

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
