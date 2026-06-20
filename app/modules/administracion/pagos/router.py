"""Capa API del submódulo Pagos (CU-03 pago, CU-04 historial)."""

from collections.abc import Sequence
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.core.database import DbDep
from app.integrations.email.port import EmailPort
from app.integrations.factory import get_email_port, get_payment_gateway
from app.integrations.payments.port import PaymentGatewayPort, WebhookVerificationError
from app.modules.administracion.pagos.models import Pago
from app.modules.administracion.pagos.schemas import (
    CheckoutRequest,
    CheckoutResponse,
    ConfirmarRequest,
    PagoRead,
    SuscripcionEstado,
)
from app.modules.administracion.pagos.service import PagoService
from app.modules.administracion.suscripciones.models import Suscripcion
from app.modules.administracion.usuarios.dependencies import RequireEstudiante

router = APIRouter(prefix="/pagos", tags=["pagos"])


def get_pago_service(
    db: DbDep,
    gateway: Annotated[PaymentGatewayPort, Depends(get_payment_gateway)],
    email: Annotated[EmailPort, Depends(get_email_port)],
) -> PagoService:
    return PagoService(db, gateway, email)


ServiceDep = Annotated[PagoService, Depends(get_pago_service)]


@router.post("/checkout", response_model=CheckoutResponse)
async def checkout(
    data: CheckoutRequest, service: ServiceDep, user: RequireEstudiante
) -> CheckoutResponse:
    url = await service.iniciar_checkout(user, data.plan_id)
    return CheckoutResponse(checkout_url=url)


@router.post("/webhook", include_in_schema=False)
async def webhook(request: Request, service: ServiceDep) -> dict[str, str]:
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    try:
        await service.procesar_webhook(payload, sig)
    except WebhookVerificationError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Firma de webhook inválida") from exc
    return {"status": "ok"}


@router.post("/confirmar", response_model=SuscripcionEstado | None)
async def confirmar(
    data: ConfirmarRequest, service: ServiceDep, user: RequireEstudiante
) -> Suscripcion | None:
    return await service.confirmar_pago(user, data.session_id)


@router.get("/mi-suscripcion", response_model=SuscripcionEstado | None)
async def mi_suscripcion(service: ServiceDep, user: RequireEstudiante) -> Suscripcion | None:
    return await service.mi_suscripcion(user)


@router.get("/historial", response_model=list[PagoRead])
async def historial(service: ServiceDep, user: RequireEstudiante) -> Sequence[Pago]:
    return await service.historial(user)
