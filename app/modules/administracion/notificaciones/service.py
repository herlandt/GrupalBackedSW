"""Lógica de negocio — notificaciones in-app (CU-02)."""

from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ResourceNotFoundError
from app.modules.administracion.notificaciones.models import NotificacionUsuario
from app.modules.administracion.notificaciones.repository import NotificacionRepository
from app.modules.administracion.usuarios.models import Usuario


class NotificacionService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.notificaciones = NotificacionRepository(db)

    async def crear(self, usuario_id: int, titulo: str, cuerpo: str) -> NotificacionUsuario:
        notif = NotificacionUsuario(usuario_id=usuario_id, titulo=titulo, cuerpo=cuerpo)
        await self.notificaciones.add(notif)
        return notif

    async def listar(self, usuario: Usuario) -> Sequence[NotificacionUsuario]:
        return await self.notificaciones.por_usuario(usuario.id)

    async def marcar_leida(self, notificacion_id: int, usuario: Usuario) -> NotificacionUsuario:
        notif = await self.notificaciones.get(notificacion_id)
        if notif is None or notif.usuario_id != usuario.id:
            # No revelar notificaciones ajenas: tratar como inexistente.
            raise ResourceNotFoundError(f"Notificación {notificacion_id} no existe")
        notif.leida = True
        await self.db.flush()
        return notif
