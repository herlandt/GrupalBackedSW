"""Capa API (router) — submódulo simulaciones (CU-13, CU-15).

Expone los endpoints HTTP y delega al service. Sin lógica de negocio.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.core.database import DbDep
from app.modules.administracion.suscripciones.dependencies import SuscripcionActiva
from app.modules.administracion.usuarios.dependencies import RequireEstudiante
from app.modules.simulador.simulaciones.schemas import SesionCreate, SesionRead
from app.modules.simulador.simulaciones.service import SimulacionService

router = APIRouter(prefix="/simulaciones", tags=["simulaciones"])


def get_simulacion_service(db: DbDep) -> SimulacionService:
    return SimulacionService(db)


ServiceDep = Annotated[SimulacionService, Depends(get_simulacion_service)]


@router.post("", response_model=SesionRead, status_code=status.HTTP_201_CREATED)
async def iniciar_simulacion(
    data: SesionCreate,
    service: ServiceDep,
    user: RequireEstudiante,
    _sub: SuscripcionActiva,
) -> SesionRead:
    """CU-13: inicia una sesión EN_CURSO anclada a una versión propia."""
    sesion = await service.iniciar(user, data.version_documento_id, data.nivel_dificultad)
    return SesionRead.model_validate(sesion)


@router.get("", response_model=list[SesionRead])
async def listar_simulaciones(
    service: ServiceDep, user: RequireEstudiante, _sub: SuscripcionActiva
) -> list[SesionRead]:
    """CU-15: historial de mis sesiones con su resultado general (más recientes primero)."""
    return await service.historial(user)


@router.get("/{sesion_id}", response_model=SesionRead)
async def obtener_simulacion(
    sesion_id: int, service: ServiceDep, user: RequireEstudiante, _sub: SuscripcionActiva
) -> SesionRead:
    """CU-15: detalle de una sesión propia (404 si es ajena)."""
    sesion = await service.obtener(sesion_id, user)
    return SesionRead.model_validate(sesion)


@router.post("/{sesion_id}/finalizar", response_model=SesionRead)
async def finalizar_simulacion(
    sesion_id: int, service: ServiceDep, user: RequireEstudiante, _sub: SuscripcionActiva
) -> SesionRead:
    """CU-13: cierra la sesión -> FINALIZADA (fija fecha_fin)."""
    sesion = await service.finalizar(sesion_id, user)
    return SesionRead.model_validate(sesion)


@router.post("/{sesion_id}/cancelar", response_model=SesionRead)
async def cancelar_simulacion(
    sesion_id: int, service: ServiceDep, user: RequireEstudiante, _sub: SuscripcionActiva
) -> SesionRead:
    """CU-13: aborta la sesión -> CANCELADA (fija fecha_fin)."""
    sesion = await service.cancelar(sesion_id, user)
    return SesionRead.model_validate(sesion)
