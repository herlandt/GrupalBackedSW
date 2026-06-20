"""Acceso a datos — submódulo monitoreo (CU-07, RF-08)."""

from collections.abc import Sequence

from sqlalchemy import select

from app.core.enums import RolUsuario
from app.core.repository import BaseRepository
from app.modules.administracion.monitoreo.models import AvanceFormal
from app.modules.administracion.usuarios.models import Usuario


class AvanceFormalRepository(BaseRepository[AvanceFormal]):
    model = AvanceFormal

    async def list_por_usuario(self, usuario_id: int) -> Sequence[AvanceFormal]:
        result = await self.db.execute(
            select(AvanceFormal)
            .where(AvanceFormal.usuario_id == usuario_id)
            .order_by(AvanceFormal.created_at.desc())
        )
        return result.scalars().all()


class EstudianteRepository(BaseRepository[Usuario]):
    model = Usuario

    async def list_estudiantes(self) -> Sequence[Usuario]:
        result = await self.db.execute(
            select(Usuario).where(Usuario.rol == RolUsuario.ESTUDIANTE).order_by(Usuario.nombre)
        )
        return result.scalars().all()
