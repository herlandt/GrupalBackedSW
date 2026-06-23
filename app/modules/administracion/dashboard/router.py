"""Capa API del submódulo Dashboard (CU-06, RF-08/09)."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.database import DbDep
from app.modules.administracion.dashboard.dependencies import build_metric_sources
from app.modules.administracion.dashboard.schemas import DashboardResponse
from app.modules.administracion.dashboard.service import DashboardService
from app.modules.administracion.usuarios.dependencies import CurrentUser

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def get_dashboard_service(db: DbDep) -> DashboardService:
    return DashboardService(db, build_metric_sources(db))


ServiceDep = Annotated[DashboardService, Depends(get_dashboard_service)]


@router.get("", response_model=DashboardResponse)
async def obtener_dashboard(
    service: ServiceDep,
    user: CurrentUser,
    modulo: Annotated[str | None, Query(description="Filtra a un solo módulo")] = None,
    desde: Annotated[datetime | None, Query(description="Inicio del periodo")] = None,
    hasta: Annotated[datetime | None, Query(description="Fin del periodo")] = None,
) -> DashboardResponse:
    # CU-06 (paso 5): el usuario puede filtrar por periodo o módulo.
    metricas = await service.obtener(user.id, user.rol, modulo=modulo, desde=desde, hasta=hasta)
    return DashboardResponse(rol=user.rol.value, metricas=metricas)
