"""Tests del submódulo Pagos (CU-03 pago, CU-04 historial) con pasarela falsa."""

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.administracion.suscripciones.models import PlanSuscripcion
from tests.conftest import FakePaymentGateway


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _crear_plan(client: AsyncClient, admin_token: str) -> int:
    r = await client.post(
        "/api/v1/planes",
        json={"nombre": "Plan", "precio": "9.99", "moneda": "USD", "periodo_dias": 30},
        headers=auth(admin_token),
    )
    return int(r.json()["id"])


async def test_checkout_crea_sesion(
    client: AsyncClient, admin_token: str, estudiante_token: str, fake_gateway: FakePaymentGateway
) -> None:
    plan_id = await _crear_plan(client, admin_token)
    r = await client.post(
        "/api/v1/pagos/checkout", json={"plan_id": plan_id}, headers=auth(estudiante_token)
    )
    assert r.status_code == 200
    assert r.json()["checkout_url"].startswith("https://")


async def test_admin_no_puede_pagar(
    client: AsyncClient, admin_token: str, fake_gateway: FakePaymentGateway
) -> None:
    plan_id = await _crear_plan(client, admin_token)
    r = await client.post(
        "/api/v1/pagos/checkout", json={"plan_id": plan_id}, headers=auth(admin_token)
    )
    assert r.status_code == 403


async def test_historial_filtra_por_estado_cu04(
    client: AsyncClient, admin_token: str, estudiante_token: str, db_session: AsyncSession
) -> None:
    # CU-04: el historial se filtra por estado (y por periodo con desde/hasta).
    from decimal import Decimal

    from sqlalchemy import select

    from app.core.enums import EstadoPago
    from app.modules.administracion.pagos.models import Pago
    from app.modules.administracion.usuarios.models import Usuario

    plan_id = await _crear_plan(client, admin_token)
    user = (
        await db_session.execute(select(Usuario).where(Usuario.email == "estu@example.com"))
    ).scalar_one()
    db_session.add_all(
        [
            Pago(
                usuario_id=user.id, plan_id=plan_id, monto=Decimal("9.99"),
                moneda="USD", estado=EstadoPago.PAGADO,
            ),
            Pago(
                usuario_id=user.id, plan_id=plan_id, monto=Decimal("9.99"),
                moneda="USD", estado=EstadoPago.FALLIDO,
            ),
        ]
    )
    await db_session.flush()

    r = await client.get(
        "/api/v1/pagos/historial?estado=PAGADO", headers=auth(estudiante_token)
    )
    assert r.status_code == 200
    assert [p["estado"] for p in r.json()] == ["PAGADO"]

    r = await client.get("/api/v1/pagos/historial", headers=auth(estudiante_token))
    assert len(r.json()) == 2  # sin filtro: ambos pagos


async def test_webhook_activa_suscripcion(
    client: AsyncClient, admin_token: str, estudiante_token: str, fake_gateway: FakePaymentGateway
) -> None:
    plan_id = await _crear_plan(client, admin_token)
    await client.post(
        "/api/v1/pagos/checkout", json={"plan_id": plan_id}, headers=auth(estudiante_token)
    )
    # Simula el webhook de Stripe (la pasarela falsa devuelve un evento 'completado').
    r = await client.post(
        "/api/v1/pagos/webhook", content=b"{}", headers={"stripe-signature": "test"}
    )
    assert r.status_code == 200

    r = await client.get("/api/v1/pagos/mi-suscripcion", headers=auth(estudiante_token))
    assert r.status_code == 200
    assert r.json()["estado"] == "ACTIVA"


async def test_historial_de_pagos(
    client: AsyncClient, admin_token: str, estudiante_token: str, fake_gateway: FakePaymentGateway
) -> None:
    plan_id = await _crear_plan(client, admin_token)
    await client.post(
        "/api/v1/pagos/checkout", json={"plan_id": plan_id}, headers=auth(estudiante_token)
    )
    r = await client.get("/api/v1/pagos/historial", headers=auth(estudiante_token))
    assert r.status_code == 200
    assert len(r.json()) >= 1


async def test_confirmar_al_volver_activa(
    client: AsyncClient, admin_token: str, estudiante_token: str, fake_gateway: FakePaymentGateway
) -> None:
    plan_id = await _crear_plan(client, admin_token)
    await client.post(
        "/api/v1/pagos/checkout", json={"plan_id": plan_id}, headers=auth(estudiante_token)
    )
    # La pasarela falsa usa el id de sesión "cs_test_fake" y la reporta como pagada.
    r = await client.post(
        "/api/v1/pagos/confirmar",
        json={"session_id": "cs_test_fake"},
        headers=auth(estudiante_token),
    )
    assert r.status_code == 200
    assert r.json()["estado"] == "ACTIVA"


async def test_no_checkout_si_ya_tiene_suscripcion(
    client: AsyncClient, admin_token: str, estudiante_token: str, fake_gateway: FakePaymentGateway
) -> None:
    plan_id = await _crear_plan(client, admin_token)
    await client.post(
        "/api/v1/pagos/checkout", json={"plan_id": plan_id}, headers=auth(estudiante_token)
    )
    await client.post(
        "/api/v1/pagos/confirmar",
        json={"session_id": "cs_test_fake"},
        headers=auth(estudiante_token),
    )
    r = await client.post(
        "/api/v1/pagos/checkout", json={"plan_id": plan_id}, headers=auth(estudiante_token)
    )
    assert r.status_code == 409


async def test_pagos_sin_token_401(client: AsyncClient) -> None:
    r = await client.get("/api/v1/pagos/historial")
    assert r.status_code == 401


async def test_confirmar_pago_ajeno_no_activa(
    client: AsyncClient,
    admin_token: str,
    estudiante_token: str,
    estudiante2_token: str,
    fake_gateway: FakePaymentGateway,
) -> None:
    plan_id = await _crear_plan(client, admin_token)
    # estu inicia el checkout (crea el pago con la sesión cs_test_fake).
    await client.post(
        "/api/v1/pagos/checkout", json={"plan_id": plan_id}, headers=auth(estudiante_token)
    )
    # estu2 intenta confirmar la sesión de pago de estu -> null, sin activar nada ajeno.
    r = await client.post(
        "/api/v1/pagos/confirmar",
        json={"session_id": "cs_test_fake"},
        headers=auth(estudiante2_token),
    )
    assert r.status_code == 200
    assert r.json() is None
    # estu nunca confirmó: su suscripción NO se activó por la confirmación ajena.
    r = await client.get("/api/v1/pagos/mi-suscripcion", headers=auth(estudiante_token))
    assert r.json() is None


async def test_webhook_idempotente(
    client: AsyncClient, admin_token: str, estudiante_token: str, fake_gateway: FakePaymentGateway
) -> None:
    plan_id = await _crear_plan(client, admin_token)
    await client.post(
        "/api/v1/pagos/checkout", json={"plan_id": plan_id}, headers=auth(estudiante_token)
    )
    # El mismo evento llega dos veces (Stripe reintenta): la 2ª no debe duplicar nada.
    for _ in range(2):
        r = await client.post(
            "/api/v1/pagos/webhook", content=b"{}", headers={"stripe-signature": "test"}
        )
        assert r.status_code == 200

    r = await client.get("/api/v1/pagos/mi-suscripcion", headers=auth(estudiante_token))
    assert r.json()["estado"] == "ACTIVA"
    r = await client.get("/api/v1/pagos/historial", headers=auth(estudiante_token))
    assert len(r.json()) == 1  # un único pago, no se duplicó


async def test_checkout_plan_inactivo_409(
    client: AsyncClient,
    admin_token: str,
    estudiante_token: str,
    db_session: AsyncSession,
    fake_gateway: FakePaymentGateway,
) -> None:
    plan_id = await _crear_plan(client, admin_token)
    plan = await db_session.get(PlanSuscripcion, plan_id)
    assert plan is not None
    plan.activo = False
    await db_session.flush()
    r = await client.post(
        "/api/v1/pagos/checkout", json={"plan_id": plan_id}, headers=auth(estudiante_token)
    )
    assert r.status_code == 409
