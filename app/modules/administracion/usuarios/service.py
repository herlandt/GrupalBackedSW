"""Lógica de negocio del submódulo Usuarios (CU-01)."""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit.service import AuditService
from app.core.config import settings
from app.core.enums import RolUsuario
from app.core.exceptions import BusinessRuleError
from app.core.security import create_access_token, hash_password, verify_password
from app.integrations.email.port import EmailPort
from app.integrations.storage.port import StoragePort
from app.modules.administracion.usuarios.models import TokenResetPassword, Usuario
from app.modules.administracion.usuarios.repository import (
    TokenResetRepository,
    UsuarioRepository,
)
from app.modules.administracion.usuarios.schemas import (
    PasswordResetConfirm,
    UsuarioRegister,
    UsuarioUpdate,
)


def _now() -> datetime:
    """Instante actual en UTC, sin zona (las columnas son TIMESTAMP naive)."""
    return datetime.now(UTC).replace(tzinfo=None)


class UsuarioService:
    def __init__(self, db: AsyncSession, email: EmailPort, storage: StoragePort) -> None:
        self.db = db
        self.users = UsuarioRepository(db)
        self.tokens = TokenResetRepository(db)
        self.audit = AuditService(db)
        self.email = email
        self.storage = storage

    async def register(self, data: UsuarioRegister) -> Usuario:
        if await self.users.get_by_email(data.email):
            raise BusinessRuleError("Ya existe una cuenta con ese correo")
        user = Usuario(
            nombre=data.nombre,
            email=data.email,
            password_hash=hash_password(data.password),
            rol=RolUsuario.ESTUDIANTE,
        )
        await self.users.add(user)
        await self.audit.log(
            actor_id=user.id, accion="USER_REGISTERED", entidad="usuario", entidad_id=user.id
        )
        return user

    async def authenticate(self, email: str, password: str) -> str:
        user = await self.users.get_by_email(email)
        if user is None or not user.activo or not verify_password(password, user.password_hash):
            raise BusinessRuleError("Credenciales inválidas")
        await self.audit.log(
            actor_id=user.id, accion="USER_LOGIN", entidad="usuario", entidad_id=user.id
        )
        return create_access_token(str(user.id))

    async def update_profile(self, user: Usuario, data: UsuarioUpdate) -> Usuario:
        if data.nombre is not None:
            user.nombre = data.nombre
        await self.db.flush()
        await self.audit.log(
            actor_id=user.id, accion="PROFILE_UPDATED", entidad="usuario", entidad_id=user.id
        )
        return user

    async def set_foto(
        self, user: Usuario, filename: str, content: bytes, content_type: str
    ) -> Usuario:
        key = f"usuarios/{user.id}/{filename}"
        user.foto_perfil_url = await self.storage.save(
            key=key, data=content, content_type=content_type
        )
        await self.db.flush()
        return user

    async def request_reset(self, email: str) -> None:
        user = await self.users.get_by_email(email)
        if user is None:
            return  # no se revela si el correo existe
        raw = secrets.token_urlsafe(32)
        token = TokenResetPassword(
            usuario_id=user.id,
            token_hash=hashlib.sha256(raw.encode()).hexdigest(),
            expires_at=_now() + timedelta(minutes=settings.password_reset_expire_minutes),
        )
        await self.tokens.add(token)
        link = f"{settings.frontend_base_url}/reset?token={raw}"
        await self.email.send(
            to=email,
            subject="Restablecer contraseña — TesisGuard",
            body=f"Para restablecer tu contraseña abre este enlace:\n{link}",
        )
        await self.audit.log(
            actor_id=user.id,
            accion="PASSWORD_RESET_REQUESTED",
            entidad="usuario",
            entidad_id=user.id,
        )

    async def confirm_reset(self, data: PasswordResetConfirm) -> None:
        token_hash = hashlib.sha256(data.token.encode()).hexdigest()
        token = await self.tokens.get_by_hash(token_hash)
        if token is None or token.used_at is not None or token.expires_at < _now():
            raise BusinessRuleError("Token inválido o expirado")
        user = await self.users.get_or_404(token.usuario_id)
        user.password_hash = hash_password(data.new_password)
        token.used_at = _now()
        await self.db.flush()
        await self.audit.log(
            actor_id=user.id,
            accion="PASSWORD_RESET_COMPLETED",
            entidad="usuario",
            entidad_id=user.id,
        )
