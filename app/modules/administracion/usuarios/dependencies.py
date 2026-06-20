"""Dependencias de autenticación y autorización (RBAC) basadas en Usuario."""

from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends, HTTPException, status

from app.core.database import DbDep
from app.core.enums import RolUsuario
from app.core.security import TokenDep, decode_token
from app.modules.administracion.usuarios.models import Usuario
from app.modules.administracion.usuarios.repository import UsuarioRepository


async def get_current_user(token: TokenDep, db: DbDep) -> Usuario:
    """Carga el Usuario del token (claim `sub`). 401 si no es válido o está inactivo."""
    payload = decode_token(token)
    sub = payload.get("sub")
    user = await UsuarioRepository(db).get(int(sub)) if sub is not None else None
    if user is None or not user.activo:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario no válido o inactivo",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


CurrentUser = Annotated[Usuario, Depends(get_current_user)]


def require_role(*roles: RolUsuario) -> Callable[[Usuario], Awaitable[Usuario]]:
    """Construye una dependencia que exige que el usuario tenga uno de los roles."""

    async def _dependency(user: CurrentUser) -> Usuario:
        if user.rol not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Permiso insuficiente")
        return user

    return _dependency


RequireAdmin = Annotated[Usuario, Depends(require_role(RolUsuario.ADMINISTRADOR))]
RequireEstudiante = Annotated[Usuario, Depends(require_role(RolUsuario.ESTUDIANTE))]
