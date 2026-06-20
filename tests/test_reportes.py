"""Tests del submódulo Reportes (CU-05 admin + export CU-04)."""

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


async def test_reporte_requiere_admin(client: AsyncClient, estudiante_token: str) -> None:
    # Sin token -> 401
    r = await client.get("/api/v1/reportes/ganancias")
    assert r.status_code == 401
    # Estudiante -> 403
    r = await client.get("/api/v1/reportes/ganancias", headers=auth(estudiante_token))
    assert r.status_code == 403


async def test_export_estudiante_rechaza_admin(client: AsyncClient, admin_token: str) -> None:
    # El export de estudiante exige RequireEstudiante -> un admin recibe 403.
    r = await client.get(
        "/api/v1/reportes/mi-historial/export", headers=auth(admin_token)
    )
    assert r.status_code == 403


async def test_ganancias_pdf(
    client: AsyncClient,
    admin_token: str,
    estudiante_token: str,
    fake_gateway: FakePaymentGateway,
) -> None:
    await _plan_y_pago(client, admin_token, estudiante_token)
    r = await client.get(
        "/api/v1/reportes/ganancias", params={"formato": "pdf"}, headers=auth(admin_token)
    )
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:4] == b"%PDF"


async def test_pagos_por_estudiante_excel(
    client: AsyncClient,
    admin_token: str,
    estudiante_token: str,
    fake_gateway: FakePaymentGateway,
) -> None:
    await _plan_y_pago(client, admin_token, estudiante_token)
    r = await client.get(
        "/api/v1/reportes/pagos-por-estudiante",
        params={"formato": "excel"},
        headers=auth(admin_token),
    )
    assert r.status_code == 200
    assert r.content[:2] == b"PK"  # .xlsx es un zip


async def test_export_historial_propio(
    client: AsyncClient,
    admin_token: str,
    estudiante_token: str,
    fake_gateway: FakePaymentGateway,
) -> None:
    await _plan_y_pago(client, admin_token, estudiante_token)
    r = await client.get(
        "/api/v1/reportes/mi-historial/export",
        params={"formato": "pdf"},
        headers=auth(estudiante_token),
    )
    assert r.status_code == 200
    assert "attachment" in r.headers["content-disposition"]
