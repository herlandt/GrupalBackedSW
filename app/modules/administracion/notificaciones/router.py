"""Capa API — notificaciones in-app del usuario (CU-02)."""

from collections.abc import Sequence
from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.database import DbDep
from app.modules.administracion.notificaciones.models import NotificacionUsuario
from app.modules.administracion.notificaciones.schemas import NotificacionRead
from app.modules.administracion.notificaciones.service import NotificacionService
from app.modules.administracion.usuarios.dependencies import CurrentUser

router = APIRouter(prefix="/notificaciones", tags=["notificaciones"])


def get_notificacion_service(db: DbDep) -> NotificacionService:
    return NotificacionService(db)


ServiceDep = Annotated[NotificacionService, Depends(get_notificacion_service)]


@router.get("", response_model=list[NotificacionRead])
async def listar_notificaciones(
    service: ServiceDep, user: CurrentUser
) -> Sequence[NotificacionUsuario]:
    return await service.listar(user)


@router.post("/{notificacion_id}/leida", response_model=NotificacionRead)
async def marcar_leida(
    notificacion_id: int, service: ServiceDep, user: CurrentUser
) -> NotificacionUsuario:
    return await service.marcar_leida(notificacion_id, user)
