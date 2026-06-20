"""Capa API del submódulo Monitoreo (CU-07 monitoreo, RF-08 avance formal). Admin."""

from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.core.database import DbDep
from app.modules.administracion.monitoreo.schemas import (
    AvanceFormalCreate,
    AvanceFormalRead,
    EstudianteDetalle,
    EstudianteResumen,
)
from app.modules.administracion.monitoreo.service import MonitoreoService
from app.modules.administracion.usuarios.dependencies import RequireAdmin

router = APIRouter(prefix="/monitoreo", tags=["monitoreo"])


def get_monitoreo_service(db: DbDep) -> MonitoreoService:
    return MonitoreoService(db)


ServiceDep = Annotated[MonitoreoService, Depends(get_monitoreo_service)]


@router.get("/estudiantes", response_model=list[EstudianteResumen])
async def listar_estudiantes(service: ServiceDep, _: RequireAdmin) -> list[EstudianteResumen]:
    return await service.listar_estudiantes()


@router.get("/estudiantes/{usuario_id}", response_model=EstudianteDetalle)
async def detalle_estudiante(
    usuario_id: int, service: ServiceDep, admin: RequireAdmin
) -> EstudianteDetalle:
    return await service.detalle_estudiante(usuario_id, admin.id)


@router.get("/estudiantes/{usuario_id}/avances", response_model=list[AvanceFormalRead])
async def listar_avances(
    usuario_id: int, service: ServiceDep, _: RequireAdmin
) -> list[AvanceFormalRead]:
    avances = await service.listar_avances(usuario_id)
    return [AvanceFormalRead.model_validate(a) for a in avances]


@router.post(
    "/estudiantes/{usuario_id}/avances",
    response_model=AvanceFormalRead,
    status_code=status.HTTP_201_CREATED,
)
async def registrar_avance(
    usuario_id: int, data: AvanceFormalCreate, service: ServiceDep, admin: RequireAdmin
) -> AvanceFormalRead:
    avance = await service.registrar_avance(usuario_id, data, admin.id)
    return AvanceFormalRead.model_validate(avance)


@router.post("/avances/{avance_id}/aprobar", response_model=AvanceFormalRead)
async def aprobar_avance(
    avance_id: int, service: ServiceDep, admin: RequireAdmin
) -> AvanceFormalRead:
    avance = await service.aprobar_avance(avance_id, admin.id)
    return AvanceFormalRead.model_validate(avance)


@router.post("/avances/{avance_id}/rechazar", response_model=AvanceFormalRead)
async def rechazar_avance(
    avance_id: int, service: ServiceDep, admin: RequireAdmin
) -> AvanceFormalRead:
    avance = await service.rechazar_avance(avance_id, admin.id)
    return AvanceFormalRead.model_validate(avance)
