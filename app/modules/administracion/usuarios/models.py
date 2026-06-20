"""Modelos ORM del submódulo Usuarios (CU-01)."""

from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, String, text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import RolUsuario
from app.models.base import Base, CreatedAtMixin, IdMixin, TimestampMixin


class Usuario(Base, IdMixin, TimestampMixin):
    __tablename__ = "usuario"

    nombre: Mapped[str] = mapped_column(String(150))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    rol: Mapped[RolUsuario] = mapped_column(SAEnum(RolUsuario, name="rol_usuario"))
    foto_perfil_url: Mapped[str | None] = mapped_column(String(500))
    activo: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))


class TokenResetPassword(Base, IdMixin, CreatedAtMixin):
    __tablename__ = "token_reset_password"

    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuario.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime]
    used_at: Mapped[datetime | None]
