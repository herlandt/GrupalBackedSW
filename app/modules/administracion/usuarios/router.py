"""Capa API del submódulo Usuarios (CU-01). Recibe y delega al service."""

from typing import Annotated

from fastapi import APIRouter, Depends, File, UploadFile, status
from fastapi.security import OAuth2PasswordRequestForm

from app.core.database import DbDep
from app.integrations.email.port import EmailPort
from app.integrations.factory import get_email_port, get_storage_port
from app.integrations.storage.port import StoragePort
from app.modules.administracion.usuarios.dependencies import CurrentUser
from app.modules.administracion.usuarios.models import Usuario
from app.modules.administracion.usuarios.schemas import (
    PasswordResetConfirm,
    PasswordResetRequest,
    Token,
    UsuarioRead,
    UsuarioRegister,
    UsuarioUpdate,
)
from app.modules.administracion.usuarios.service import UsuarioService

router = APIRouter(tags=["usuarios"])


def get_usuario_service(
    db: DbDep,
    email: Annotated[EmailPort, Depends(get_email_port)],
    storage: Annotated[StoragePort, Depends(get_storage_port)],
) -> UsuarioService:
    return UsuarioService(db, email, storage)


ServiceDep = Annotated[UsuarioService, Depends(get_usuario_service)]


@router.post("/auth/register", response_model=UsuarioRead, status_code=status.HTTP_201_CREATED)
async def register(data: UsuarioRegister, service: ServiceDep) -> Usuario:
    return await service.register(data)


@router.post("/auth/login", response_model=Token)
async def login(
    form: Annotated[OAuth2PasswordRequestForm, Depends()], service: ServiceDep
) -> Token:
    access_token = await service.authenticate(form.username, form.password)
    return Token(access_token=access_token)


@router.post("/auth/logout")
async def logout(user: CurrentUser, service: ServiceDep) -> dict[str, str]:
    """CU-01: cierra la sesión (registra el evento; el cliente descarta el token)."""
    await service.logout(user)
    return {"detail": "Sesión cerrada."}


@router.get("/usuarios/me", response_model=UsuarioRead)
async def get_me(user: CurrentUser) -> Usuario:
    return user


@router.patch("/usuarios/me", response_model=UsuarioRead)
async def update_me(data: UsuarioUpdate, user: CurrentUser, service: ServiceDep) -> Usuario:
    return await service.update_profile(user, data)


@router.post("/usuarios/me/foto", response_model=UsuarioRead)
async def upload_foto(
    user: CurrentUser, service: ServiceDep, file: Annotated[UploadFile, File()]
) -> Usuario:
    content = await file.read()
    return await service.set_foto(
        user,
        file.filename or "foto",
        content,
        file.content_type or "application/octet-stream",
    )


@router.post("/auth/password-reset/request", status_code=status.HTTP_202_ACCEPTED)
async def reset_request(data: PasswordResetRequest, service: ServiceDep) -> dict[str, str]:
    await service.request_reset(data.email)
    return {"detail": "Si el correo está registrado, se envió un enlace de restablecimiento."}


@router.post("/auth/password-reset/confirm")
async def reset_confirm(data: PasswordResetConfirm, service: ServiceDep) -> dict[str, str]:
    await service.confirm_reset(data)
    return {"detail": "Contraseña actualizada."}
