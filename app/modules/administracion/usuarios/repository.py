"""Acceso a datos del submódulo Usuarios."""

from sqlalchemy import select

from app.core.repository import BaseRepository
from app.modules.administracion.usuarios.models import TokenResetPassword, Usuario


class UsuarioRepository(BaseRepository[Usuario]):
    model = Usuario

    async def get_by_email(self, email: str) -> Usuario | None:
        result = await self.db.execute(select(Usuario).where(Usuario.email == email))
        return result.scalar_one_or_none()


class TokenResetRepository(BaseRepository[TokenResetPassword]):
    model = TokenResetPassword

    async def get_by_hash(self, token_hash: str) -> TokenResetPassword | None:
        result = await self.db.execute(
            select(TokenResetPassword).where(TokenResetPassword.token_hash == token_hash)
        )
        return result.scalar_one_or_none()
