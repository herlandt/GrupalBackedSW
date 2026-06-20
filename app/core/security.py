"""Primitivas de autenticación reutilizables: hashing de contraseñas y JWT.

No conoce el modelo de usuario. La carga real del usuario a partir del token se
cablea en el Ciclo 1 (módulo de usuarios), donde `get_current_user` devolverá un
`User` cargado desde la base de datos en lugar de los claims crudos.
"""

from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pwdlib import PasswordHash

from app.core.config import settings

_hasher = PasswordHash.recommended()  # Argon2id
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def hash_password(plain: str) -> str:
    """Devuelve el hash Argon2id de una contraseña en texto plano."""
    return _hasher.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Comprueba si una contraseña en texto plano corresponde al hash dado."""
    return _hasher.verify(plain, hashed)


def create_access_token(subject: str, expires_minutes: int | None = None) -> str:
    """Genera un JWT firmado cuyo `sub` identifica al usuario."""
    expire = datetime.now(UTC) + timedelta(minutes=expires_minutes or settings.jwt_expire_minutes)
    payload = {"sub": subject, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict[str, Any]:
    """Valida y decodifica un JWT; lanza 401 si es inválido o ha expirado."""
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o expirado",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


# Token crudo extraído del header Authorization. La carga del Usuario real desde
# la DB vive en `app/modules/administracion/usuarios/dependencies.py`.
TokenDep = Annotated[str, Depends(oauth2_scheme)]
