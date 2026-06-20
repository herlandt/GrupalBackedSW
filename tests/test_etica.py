"""Tests del submódulo Ética (CU-12)."""

from datetime import datetime
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import EstadoAnalisis, EstadoSuscripcion, FormatoDocumento
from app.modules.administracion.suscripciones.models import PlanSuscripcion, Suscripcion
from app.modules.administracion.usuarios.models import Usuario
from app.modules.auditoria_documental.documentos.models import Documento, VersionDocumento
from tests.conftest import FakeEmail


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _dar_suscripcion(db: AsyncSession, email: str) -> None:
    """Da una suscripción ACTIVA al usuario (precondición de CU-12 para el estudiante)."""
    user = (await db.execute(select(Usuario).where(Usuario.email == email))).scalar_one()
    plan = PlanSuscripcion(nombre="Plan", precio=Decimal("9.99"), moneda="USD", periodo_dias=30)
    db.add(plan)
    await db.flush()
    db.add(
        Suscripcion(
            usuario_id=user.id,
            plan_id=plan.id,
            estado=EstadoSuscripcion.ACTIVA,
            fecha_inicio=datetime(2020, 1, 1),
            fecha_fin=datetime(2999, 1, 1),
        )
    )
    await db.flush()


async def _crear_version_de(db: AsyncSession, email: str) -> int:
    """Crea Documento + VersionDocumento para el usuario con ese email; devuelve version_id."""
    user = (await db.execute(select(Usuario).where(Usuario.email == email))).scalar_one()
    doc = Documento(usuario_id=user.id, titulo="Tesis")
    db.add(doc)
    await db.flush()
    ver = VersionDocumento(
        documento_id=doc.id,
        numero_version=1,
        archivo_url="media/x.docx",
        formato=FormatoDocumento.DOCX,
        estado_analisis=EstadoAnalisis.COMPLETADO,
    )
    db.add(ver)
    await db.flush()
    return ver.id


async def test_admin_crea_alerta_y_notifica(
    client: AsyncClient,
    admin_token: str,
    estudiante_token: str,
    db_session: AsyncSession,
    fake_email: FakeEmail,
) -> None:
    assert estudiante_token  # registra al estudiante "estu@example.com"
    version_id = await _crear_version_de(db_session, "estu@example.com")
    r = await client.post(
        "/api/v1/etica/alertas",
        json={"version_id": version_id, "tipo": "PLAGIO", "fragmento": "texto sospechoso"},
        headers=auth(admin_token),
    )
    assert r.status_code == 201
    assert r.json()["estado"] == "PENDIENTE"
    destinatarios = [m["to"] for m in fake_email.messages]
    assert "estu@example.com" in destinatarios  # estudiante dueño
    assert "admin@example.com" in destinatarios  # administrador


async def test_listar_sin_token_401(client: AsyncClient) -> None:
    r = await client.get("/api/v1/etica/alertas")
    assert r.status_code == 401


async def test_estudiante_no_ve_bandeja_admin(
    client: AsyncClient, estudiante_token: str
) -> None:
    r = await client.get("/api/v1/etica/alertas", headers=auth(estudiante_token))
    assert r.status_code == 403


async def test_resolver_confirmada(
    client: AsyncClient,
    admin_token: str,
    estudiante_token: str,
    db_session: AsyncSession,
    fake_email: FakeEmail,
) -> None:
    assert estudiante_token
    version_id = await _crear_version_de(db_session, "estu@example.com")
    r = await client.post(
        "/api/v1/etica/alertas",
        json={"version_id": version_id, "tipo": "PLAGIO"},
        headers=auth(admin_token),
    )
    alerta_id = r.json()["id"]

    r = await client.patch(
        f"/api/v1/etica/alertas/{alerta_id}/resolver",
        json={"estado": "CONFIRMADA"},
        headers=auth(admin_token),
    )
    assert r.status_code == 200
    assert r.json()["estado"] == "CONFIRMADA"
    assert r.json()["decision_admin_id"] is not None
    # Se notificó al estudiante la resolución.
    asuntos = [m["subject"] for m in fake_email.messages if m["to"] == "estu@example.com"]
    assert any("Resolución" in s for s in asuntos)


async def test_resolver_a_pendiente_409(
    client: AsyncClient, admin_token: str, estudiante_token: str, db_session: AsyncSession
) -> None:
    assert estudiante_token
    version_id = await _crear_version_de(db_session, "estu@example.com")
    r = await client.post(
        "/api/v1/etica/alertas",
        json={"version_id": version_id, "tipo": "PLAGIO"},
        headers=auth(admin_token),
    )
    alerta_id = r.json()["id"]
    r2 = await client.patch(
        f"/api/v1/etica/alertas/{alerta_id}/resolver",
        json={"estado": "PENDIENTE"},
        headers=auth(admin_token),
    )
    assert r2.status_code == 409


async def test_mis_alertas_estudiante(
    client: AsyncClient,
    admin_token: str,
    estudiante_token: str,
    db_session: AsyncSession,
    fake_email: FakeEmail,
) -> None:
    version_id = await _crear_version_de(db_session, "estu@example.com")
    await _dar_suscripcion(db_session, "estu@example.com")  # CU-12: requiere suscripción
    await client.post(
        "/api/v1/etica/alertas",
        json={"version_id": version_id, "tipo": "AUTOPLAGIO"},
        headers=auth(admin_token),
    )
    r = await client.get("/api/v1/etica/mis-alertas", headers=auth(estudiante_token))
    assert r.status_code == 200
    alertas = r.json()
    assert len(alertas) == 1
    assert alertas[0]["version_id"] == version_id
    assert alertas[0]["tipo"] == "AUTOPLAGIO"


async def test_mis_alertas_sin_suscripcion_402(
    client: AsyncClient, estudiante_token: str
) -> None:
    # CU-12 exige suscripción activa para el estudiante (igual que documentos/auditoria).
    r = await client.get("/api/v1/etica/mis-alertas", headers=auth(estudiante_token))
    assert r.status_code == 402


async def test_crear_alerta_version_inexistente_404(
    client: AsyncClient, admin_token: str
) -> None:
    r = await client.post(
        "/api/v1/etica/alertas",
        json={"version_id": 999999, "tipo": "PLAGIO"},
        headers=auth(admin_token),
    )
    assert r.status_code == 404
