"""Tests del submódulo Suscripciones (CU-02): gestión de tarifas por el admin."""

from datetime import datetime

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import EstadoSuscripcion
from app.modules.administracion.suscripciones.models import Suscripcion
from app.modules.administracion.usuarios.models import Usuario
from tests.conftest import FakeEmail

PLAN = {"nombre": "Plan Test", "precio": "5.00", "moneda": "USD", "periodo_dias": 30}


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_admin_crea_plan(client: AsyncClient, admin_token: str) -> None:
    r = await client.post("/api/v1/planes", json=PLAN, headers=auth(admin_token))
    assert r.status_code == 201
    assert r.json()["nombre"] == "Plan Test"
    assert r.json()["precio"] == "5.00"


async def test_estudiante_no_puede_crear_plan(client: AsyncClient, estudiante_token: str) -> None:
    r = await client.post("/api/v1/planes", json=PLAN, headers=auth(estudiante_token))
    assert r.status_code == 403


async def test_listar_planes(client: AsyncClient, admin_token: str) -> None:
    await client.post("/api/v1/planes", json=PLAN, headers=auth(admin_token))
    r = await client.get("/api/v1/planes", headers=auth(admin_token))
    assert r.status_code == 200
    assert any(p["nombre"] == "Plan Test" for p in r.json())


async def test_actualizar_tarifa(client: AsyncClient, admin_token: str) -> None:
    creado = await client.post("/api/v1/planes", json=PLAN, headers=auth(admin_token))
    plan_id = creado.json()["id"]
    r = await client.patch(
        f"/api/v1/planes/{plan_id}", json={"precio": "7.50"}, headers=auth(admin_token)
    )
    assert r.status_code == 200
    assert r.json()["precio"] == "7.50"


async def test_listar_requiere_autenticacion(client: AsyncClient) -> None:
    r = await client.get("/api/v1/planes")
    assert r.status_code == 401


async def test_cambio_tarifa_notifica_suscriptores_activos(
    client: AsyncClient,
    admin_token: str,
    estudiante_token: str,
    db_session: AsyncSession,
    fake_email: FakeEmail,
) -> None:
    # Plan + suscripción ACTIVA de un estudiante a ese plan.
    creado = await client.post("/api/v1/planes", json=PLAN, headers=auth(admin_token))
    plan_id = creado.json()["id"]
    estu = (
        await db_session.execute(select(Usuario).where(Usuario.email == "estu@example.com"))
    ).scalar_one()
    db_session.add(
        Suscripcion(
            usuario_id=estu.id,
            plan_id=plan_id,
            estado=EstadoSuscripcion.ACTIVA,
            fecha_inicio=datetime(2020, 1, 1),
            fecha_fin=datetime(2999, 1, 1),
        )
    )
    await db_session.flush()

    # El admin cambia el precio -> CU-02 (postcondición): notificar a los suscriptores activos.
    r = await client.patch(
        f"/api/v1/planes/{plan_id}", json={"precio": "9.99"}, headers=auth(admin_token)
    )
    assert r.status_code == 200
    destinatarios = [m["to"] for m in fake_email.messages]
    assert "estu@example.com" in destinatarios
    assert any("tarifa" in m["subject"].lower() for m in fake_email.messages)
