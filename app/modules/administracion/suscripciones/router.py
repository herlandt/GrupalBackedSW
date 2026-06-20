"""Capa API del submódulo Suscripciones (CU-02). Gestión de tarifas (admin)."""

from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.core.database import DbDep
from app.core.enums import RolUsuario
from app.integrations.email.port import EmailPort
from app.integrations.factory import get_email_port
from app.modules.administracion.suscripciones.models import PlanSuscripcion
from app.modules.administracion.suscripciones.schemas import PlanCreate, PlanRead, PlanUpdate
from app.modules.administracion.suscripciones.service import SuscripcionService
from app.modules.administracion.usuarios.dependencies import CurrentUser, RequireAdmin

router = APIRouter(prefix="/planes", tags=["suscripciones"])


def get_suscripcion_service(
    db: DbDep, email: Annotated[EmailPort, Depends(get_email_port)]
) -> SuscripcionService:
    return SuscripcionService(db, email)


ServiceDep = Annotated[SuscripcionService, Depends(get_suscripcion_service)]


@router.get("", response_model=list[PlanRead])
async def listar_planes(
    service: ServiceDep, user: CurrentUser, incluir_inactivos: bool = False
) -> list[PlanSuscripcion]:
    """Planes activos; un administrador puede pedir todos con ?incluir_inactivos=true."""
    solo_activos = not (incluir_inactivos and user.rol is RolUsuario.ADMINISTRADOR)
    return list(await service.listar_planes(solo_activos=solo_activos))


@router.post("", response_model=PlanRead, status_code=status.HTTP_201_CREATED)
async def crear_plan(data: PlanCreate, service: ServiceDep, admin: RequireAdmin) -> PlanSuscripcion:
    return await service.crear_plan(data, admin.id)


@router.patch("/{plan_id}", response_model=PlanRead)
async def actualizar_plan(
    plan_id: int, data: PlanUpdate, service: ServiceDep, admin: RequireAdmin
) -> PlanSuscripcion:
    return await service.actualizar_plan(plan_id, data, admin.id)
