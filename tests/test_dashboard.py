"""Tests del submódulo Dashboard (CU-06, RF-08/09)."""

from httpx import AsyncClient

from tests.conftest import FakePaymentGateway


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _plan_y_pago(client: AsyncClient, admin_token: str, estudiante_token: str) -> None:
    """Crea un plan, hace checkout y confirma el pago (deja un pago PAGADO)."""
    r = await client.post(
        "/api/v1/planes",
        json={"nombre": "Plan", "precio": "9.99", "moneda": "USD", "periodo_dias": 30},
        headers=auth(admin_token),
    )
    plan_id = int(r.json()["id"])
    await client.post(
        "/api/v1/pagos/checkout", json={"plan_id": plan_id}, headers=auth(estudiante_token)
    )
    await client.post(
        "/api/v1/pagos/confirmar",
        json={"session_id": "cs_test_fake"},
        headers=auth(estudiante_token),
    )


async def test_dashboard_requiere_token(client: AsyncClient) -> None:
    r = await client.get("/api/v1/dashboard")
    assert r.status_code == 401


async def test_dashboard_estudiante(client: AsyncClient, estudiante_token: str) -> None:
    r = await client.get("/api/v1/dashboard", headers=auth(estudiante_token))
    assert r.status_code == 200
    body = r.json()
    assert body["rol"] == "ESTUDIANTE"
    assert "cuenta" in body["metricas"]
    assert "suscripcion" in body["metricas"]
    assert "pagos" in body["metricas"]
    # El estudiante ve su propio email, no totales globales.
    assert "email" in body["metricas"]["cuenta"]


async def test_dashboard_admin_agregado(client: AsyncClient, admin_token: str) -> None:
    r = await client.get("/api/v1/dashboard", headers=auth(admin_token))
    assert r.status_code == 200
    body = r.json()
    assert body["rol"] == "ADMINISTRADOR"
    assert "total_usuarios" in body["metricas"]["cuenta"]
    assert "ingresos_totales" in body["metricas"]["pagos"]
    assert "suscripciones_activas" in body["metricas"]["suscripcion"]


async def test_dashboard_estudiante_refleja_pago(
    client: AsyncClient,
    admin_token: str,
    estudiante_token: str,
    fake_gateway: FakePaymentGateway,
) -> None:
    await _plan_y_pago(client, admin_token, estudiante_token)
    r = await client.get("/api/v1/dashboard", headers=auth(estudiante_token))
    assert r.status_code == 200
    pagos = r.json()["metricas"]["pagos"]
    assert pagos["total_pagos"] >= 1
    assert pagos["ultimo_pago"]["estado"] == "PAGADO"
