"""Modelos ORM del submódulo Auditoría — resultados (CU-10, RF-01, RF-02)."""

from typing import Any

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import CategoriaObservacion, NivelPreparacion
from app.models.base import Base, CreatedAtMixin, IdMixin


class ResultadoAuditoria(Base, IdMixin, CreatedAtMixin):
    __tablename__ = "resultado_auditoria"

    version_id: Mapped[int] = mapped_column(ForeignKey("version_documento.id"), unique=True)
    nivel_documento: Mapped[NivelPreparacion] = mapped_column(
        SAEnum(NivelPreparacion, name="nivel_preparacion")
    )
    resumen: Mapped[str | None] = mapped_column(Text)
    # Features que alimentaron a la IA evaluadora (trazabilidad + futuro reentrenamiento).
    features: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


class Observacion(Base, IdMixin):
    __tablename__ = "observacion"

    resultado_id: Mapped[int] = mapped_column(ForeignKey("resultado_auditoria.id"), index=True)
    categoria: Mapped[CategoriaObservacion] = mapped_column(
        SAEnum(CategoriaObservacion, name="categoria_observacion")
    )
    severidad: Mapped[str] = mapped_column(String(20))
    descripcion: Mapped[str] = mapped_column(Text)
    ubicacion: Mapped[str | None] = mapped_column(String(255))
