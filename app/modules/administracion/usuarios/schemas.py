"""Esquemas Pydantic del submódulo Usuarios (contrato de la API)."""

from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.core.enums import RolUsuario


class UsuarioRegister(BaseModel):
    nombre: str = Field(min_length=1, max_length=150)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class UsuarioRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre: str
    email: EmailStr
    rol: RolUsuario
    foto_perfil_url: str | None = None
    preferencias: dict[str, Any] | None = None
    activo: bool


class UsuarioUpdate(BaseModel):
    nombre: str | None = Field(default=None, min_length=1, max_length=150)
    preferencias: dict[str, Any] | None = None


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str = Field(min_length=8, max_length=128)
