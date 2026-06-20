"""Bitácora / log de auditoría (transversal a todos los módulos).

Registra eventos sensibles del sistema (altas, cambios de tarifa, pagos, etc.).
Vive en `core` porque lo reutilizan módulos de los 3 sprints.
"""

from typing import Any

from sqlalchemy import BigInteger, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CreatedAtMixin, IdMixin


class Bitacora(Base, IdMixin, CreatedAtMixin):
    __tablename__ = "bitacora"

    actor_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"), index=True)
    accion: Mapped[str] = mapped_column(String(120))
    entidad: Mapped[str] = mapped_column(String(120))
    entidad_id: Mapped[int | None] = mapped_column(BigInteger)
    metadata_: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB)
