"""Puerto de pasarela de pago (contrato) y DTOs neutrales de la pasarela."""

from dataclasses import dataclass, field
from typing import Protocol


class WebhookVerificationError(Exception):
    """La firma o el contenido del webhook no son válidos."""


@dataclass
class CheckoutSession:
    id: str
    url: str


@dataclass
class WebhookEvent:
    id: str
    type: str
    checkout_session_id: str | None = None
    payment_intent_id: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass
class CheckoutStatus:
    payment_status: str  # "paid" | "unpaid" | "no_payment_required"
    payment_intent_id: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)


class PaymentGatewayPort(Protocol):
    async def create_checkout_session(
        self,
        *,
        amount_cents: int,
        currency: str,
        metadata: dict[str, str],
        success_url: str,
        cancel_url: str,
    ) -> CheckoutSession: ...

    async def retrieve_checkout_session(self, session_id: str) -> CheckoutStatus: ...

    async def parse_webhook_event(self, payload: bytes, sig_header: str) -> WebhookEvent: ...
