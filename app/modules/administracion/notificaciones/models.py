"""Modelo ORM de notificaciones in-app al usuario (CU-02 y avisos del sistema)."""

from sqlalchemy import Boolean, ForeignKey, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CreatedAtMixin, IdMixin


class NotificacionUsuario(Base, IdMixin, CreatedAtMixin):
    __tablename__ = "notificacion_usuario"

    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuario.id"), index=True)
    titulo: Mapped[str] = mapped_column(String(160))
    cuerpo: Mapped[str] = mapped_column(Text)
    leida: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
