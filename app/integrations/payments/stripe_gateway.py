"""Adaptador de Stripe (Checkout + webhook). El SDK es síncrono → se ejecuta
en un hilo para no bloquear el event loop."""

from typing import Any

import anyio
import stripe

from app.core.config import settings
from app.integrations.payments.port import (
    CheckoutSession,
    CheckoutStatus,
    WebhookEvent,
    WebhookVerificationError,
)


def _field(obj: Any, key: str) -> Any:
    """Lee un campo de un objeto de Stripe de forma robusta (solo subíndice;
    sus objetos no exponen .get()/.items()/dict())."""
    try:
        return obj[key]
    except (KeyError, TypeError):
        return None


class StripeGateway:
    def __init__(self) -> None:
        stripe.api_key = settings.stripe_secret_key

    async def create_checkout_session(
        self,
        *,
        amount_cents: int,
        currency: str,
        metadata: dict[str, str],
        success_url: str,
        cancel_url: str,
    ) -> CheckoutSession:
        def _create() -> Any:
            return stripe.checkout.Session.create(
                mode="payment",
                line_items=[
                    {
                        "price_data": {
                            "currency": currency,
                            "product_data": {
                                "name": metadata.get("plan_nombre", "Suscripción TesisGuard")
                            },
                            "unit_amount": amount_cents,
                        },
                        "quantity": 1,
                    }
                ],
                metadata=metadata,
                success_url=success_url,
                cancel_url=cancel_url,
            )

        session = await anyio.to_thread.run_sync(_create)
        return CheckoutSession(id=session.id, url=session.url or "")

    async def retrieve_checkout_session(self, session_id: str) -> CheckoutStatus:
        def _retrieve() -> Any:
            return stripe.checkout.Session.retrieve(session_id)

        session = await anyio.to_thread.run_sync(_retrieve)
        return CheckoutStatus(
            payment_status=_field(session, "payment_status") or "unpaid",
            payment_intent_id=_field(session, "payment_intent"),
        )

    async def parse_webhook_event(self, payload: bytes, sig_header: str) -> WebhookEvent:
        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, settings.stripe_webhook_secret
            )
        except (stripe.SignatureVerificationError, ValueError) as exc:
            raise WebhookVerificationError(str(exc)) from exc
        obj = event["data"]["object"]
        return WebhookEvent(
            id=event["id"],
            type=event["type"],
            checkout_session_id=_field(obj, "id"),
            payment_intent_id=_field(obj, "payment_intent"),
        )
