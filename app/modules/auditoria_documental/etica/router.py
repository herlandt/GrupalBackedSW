"""Capa API (router) — submódulo etica (CU-12)."""

from collections.abc import Sequence
from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.core.database import DbDep
from app.integrations.email.port import EmailPort
from app.integrations.factory import get_email_port
from app.modules.administracion.suscripciones.dependencies import SuscripcionActiva
from app.modules.administracion.usuarios.dependencies import RequireAdmin, RequireEstudiante
from app.modules.auditoria_documental.etica.models import AlertaEtica
from app.modules.auditoria_documental.etica.schemas import (
    AlertaCrear,
    AlertaRead,
    AlertaResolver,
)
from app.modules.auditoria_documental.etica.service import EticaService

router = APIRouter(prefix="/etica", tags=["etica"])


def get_etica_service(
    db: DbDep,
    email: Annotated[EmailPort, Depends(get_email_port)],
) -> EticaService:
    return EticaService(db, email)


ServiceDep = Annotated[EticaService, Depends(get_etica_service)]


@router.post("/alertas", response_model=AlertaRead, status_code=status.HTTP_201_CREATED)
async def crear_alerta(
    data: AlertaCrear, service: ServiceDep, _admin: RequireAdmin
) -> AlertaEtica:
    return await service.crear_alerta(data.version_id, data.tipo, data.fragmento)


@router.get("/alertas", response_model=list[AlertaRead])
async def listar_alertas(service: ServiceDep, _admin: RequireAdmin) -> Sequence[AlertaEtica]:
    return await service.listar()


@router.get("/alertas/{alerta_id}", response_model=AlertaRead)
async def obtener_alerta(
    alerta_id: int, service: ServiceDep, _admin: RequireAdmin
) -> AlertaEtica:
    return await service.obtener(alerta_id)


@router.patch("/alertas/{alerta_id}/resolver", response_model=AlertaRead)
async def resolver_alerta(
    alerta_id: int, data: AlertaResolver, service: ServiceDep, admin: RequireAdmin
) -> AlertaEtica:
    return await service.resolver(alerta_id, admin, data.estado)


@router.get("/mis-alertas", response_model=list[AlertaRead])
async def mis_alertas(
    service: ServiceDep, user: RequireEstudiante, _sub: SuscripcionActiva
) -> Sequence[AlertaEtica]:
    # CU-12 (precondición): el estudiante debe tener suscripción activa.
    return await service.mis_alertas(user)
