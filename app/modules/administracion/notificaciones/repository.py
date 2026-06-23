"""Acceso a datos — notificaciones in-app (CU-02)."""

from collections.abc import Sequence

from sqlalchemy import select

from app.core.repository import BaseRepository
from app.modules.administracion.notificaciones.models import NotificacionUsuario


class NotificacionRepository(BaseRepository[NotificacionUsuario]):
    model = NotificacionUsuario

    async def por_usuario(self, usuario_id: int) -> Sequence[NotificacionUsuario]:
        result = await self.db.execute(
            select(NotificacionUsuario)
            .where(NotificacionUsuario.usuario_id == usuario_id)
            .order_by(NotificacionUsuario.created_at.desc())
        )
        return result.scalars().all()
