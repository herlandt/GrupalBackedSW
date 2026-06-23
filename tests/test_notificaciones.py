"""Tests de notificaciones in-app (CU-02)."""

from datetime import datetime

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import EstadoSuscripcion
from app.modules.administracion.suscripciones.models import Suscripcion
from app.modules.administracion.usuarios.models import Usuario
from tests.conftest import FakeEmail


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_cambio_tarifa_genera_notificacion_in_app(
    client: AsyncClient,
    admin_token: str,
    estudiante_token: str,
    db_session: AsyncSession,
    fake_email: FakeEmail,
) -> None:
    # Admin crea un plan.
    r = await client.post(
        "/api/v1/planes",
        json={"nombre": "Plan", "precio": "9.99", "moneda": "USD", "periodo_dias": 30},
        headers=auth(admin_token),
    )
    plan_id = int(r.json()["id"])

    # El estudiante tiene una suscripción ACTIVA a ese plan.
    user = (
        await db_session.execute(select(Usuario).where(Usuario.email == "estu@example.com"))
    ).scalar_one()
    db_session.add(
        Suscripcion(
            usuario_id=user.id,
            plan_id=plan_id,
            estado=EstadoSuscripcion.ACTIVA,
            fecha_inicio=datetime(2020, 1, 1),
            fecha_fin=datetime(2999, 1, 1),
        )
    )
    await db_session.flush()

    # Admin cambia la tarifa -> CU-02: correo + notificación in-app.
    r = await client.patch(
        f"/api/v1/planes/{plan_id}", json={"precio": "19.99"}, headers=auth(admin_token)
    )
    assert r.status_code == 200, r.text
    assert any(m["to"] == "estu@example.com" for m in fake_email.messages)  # correo

    # El estudiante ve la notificación en el sistema.
    r = await client.get("/api/v1/notificaciones", headers=auth(estudiante_token))
    assert r.status_code == 200
    notifs = r.json()
    assert len(notifs) == 1
    assert notifs[0]["leida"] is False
    assert "tarifa" in notifs[0]["titulo"].lower()

    # Puede marcarla como leída.
    r = await client.post(
        f"/api/v1/notificaciones/{notifs[0]['id']}/leida", headers=auth(estudiante_token)
    )
    assert r.status_code == 200
    assert r.json()["leida"] is True


async def test_notificaciones_requiere_token(client: AsyncClient) -> None:
    r = await client.get("/api/v1/notificaciones")
    assert r.status_code == 401


async def test_marcar_leida_ajena_404(
    client: AsyncClient, estudiante_token: str, estudiante2_token: str, db_session: AsyncSession
) -> None:
    # Una notificación de estu2 no puede marcarla estu (se trata como inexistente).
    from app.modules.administracion.notificaciones.models import NotificacionUsuario

    user2 = (
        await db_session.execute(select(Usuario).where(Usuario.email == "estu2@example.com"))
    ).scalar_one()
    notif = NotificacionUsuario(usuario_id=user2.id, titulo="x", cuerpo="y")
    db_session.add(notif)
    await db_session.flush()
    r = await client.post(
        f"/api/v1/notificaciones/{notif.id}/leida", headers=auth(estudiante_token)
    )
    assert r.status_code == 404
