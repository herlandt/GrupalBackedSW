"""Capa API (router) — submódulo integracion (CU-14, dimensión defensa).

Cierre de la sesión: calcula el nivel de defensa (IA evaluadora) y persiste el
`ResultadoSimulacion`. Sin lógica de negocio (delega al service).
"""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.database import DbDep
from app.integrations.evaluador.port import EvaluadorServicePort
from app.integrations.factory import get_evaluador_service
from app.modules.administracion.suscripciones.dependencies import SuscripcionActiva
from app.modules.administracion.usuarios.dependencies import RequireEstudiante
from app.modules.simulador.integracion.schemas import ResultadoSimulacionRead
from app.modules.simulador.integracion.service import IntegracionService

router = APIRouter(prefix="/simulaciones", tags=["simulador-resultado"])


def get_integracion_service(
    db: DbDep,
    evaluador: Annotated[EvaluadorServicePort, Depends(get_evaluador_service)],
) -> IntegracionService:
    return IntegracionService(db, evaluador)


ServiceDep = Annotated[IntegracionService, Depends(get_integracion_service)]


@router.post("/{sesion_id}/resultado", response_model=ResultadoSimulacionRead)
async def generar_resultado(
    sesion_id: int,
    service: ServiceDep,
    user: RequireEstudiante,
    _sub: SuscripcionActiva,
) -> ResultadoSimulacionRead:
    """CU-14: cierra la sesión, calcula el nivel de defensa (IA) y persiste el resultado."""
    resultado = await service.generar_resultado(sesion_id, user)
    return ResultadoSimulacionRead.model_validate(resultado)


@router.get("/{sesion_id}/resultado", response_model=ResultadoSimulacionRead)
async def obtener_resultado(
    sesion_id: int,
    service: ServiceDep,
    user: RequireEstudiante,
    _sub: SuscripcionActiva,
) -> ResultadoSimulacionRead:
    resultado = await service.obtener_resultado(sesion_id, user)
    return ResultadoSimulacionRead.model_validate(resultado)
