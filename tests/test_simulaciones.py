"""Tests del submódulo Simulaciones (CU-13, CU-15)."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import EstadoAnalisis, EstadoSuscripcion, FormatoDocumento
from app.modules.administracion.suscripciones.models import PlanSuscripcion, Suscripcion
from app.modules.administracion.usuarios.models import Usuario
from app.modules.auditoria_documental.documentos.models import Documento, VersionDocumento


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


async def _usuario_por_email(db: AsyncSession, email: str) -> Usuario:
    return (await db.execute(select(Usuario).where(Usuario.email == email))).scalar_one()


async def _suscribir(db: AsyncSession, usuario_id: int) -> None:
    """Deja al usuario con una suscripción ACTIVA y vigente (pasa el gating 402)."""
    plan = PlanSuscripcion(
        nombre="Plan test", precio=Decimal("9.99"), moneda="USD", periodo_dias=30, activo=True
    )
    db.add(plan)
    await db.flush()
    db.add(
        Suscripcion(
            usuario_id=usuario_id,
            plan_id=plan.id,
            estado=EstadoSuscripcion.ACTIVA,
            fecha_inicio=_now(),
            fecha_fin=_now() + timedelta(days=30),
        )
    )
    await db.flush()


async def _crear_version(db: AsyncSession, usuario_id: int) -> int:
    """Crea un Documento + VersionDocumento del usuario; devuelve version.id."""
    documento = Documento(usuario_id=usuario_id, titulo="Tesis test")
    db.add(documento)
    await db.flush()
    version = VersionDocumento(
        documento_id=documento.id,
        numero_version=1,
        archivo_url="documentos/1/v1/tesis.pdf",
        formato=FormatoDocumento.PDF,
        estado_analisis=EstadoAnalisis.PENDIENTE,
    )
    db.add(version)
    await db.flush()
    return version.id


async def test_iniciar_finalizar_e_historial(
    client: AsyncClient, estudiante_token: str, db_session: AsyncSession
) -> None:
    estu = await _usuario_por_email(db_session, "estu@example.com")
    await _suscribir(db_session, estu.id)
    version_id = await _crear_version(db_session, estu.id)

    # CU-13: iniciar
    r = await client.post(
        "/api/v1/simulaciones",
        json={"version_documento_id": version_id, "nivel_dificultad": "ESTANDAR"},
        headers=auth(estudiante_token),
    )
    assert r.status_code == 201, r.text
    sesion = r.json()
    assert sesion["estado"] == "EN_CURSO"
    assert sesion["fecha_fin"] is None
    sesion_id = sesion["id"]

    # CU-13: finalizar
    r = await client.post(
        f"/api/v1/simulaciones/{sesion_id}/finalizar", headers=auth(estudiante_token)
    )
    assert r.status_code == 200
    assert r.json()["estado"] == "FINALIZADA"
    assert r.json()["fecha_fin"] is not None

    # finalizar dos veces -> 409
    r = await client.post(
        f"/api/v1/simulaciones/{sesion_id}/finalizar", headers=auth(estudiante_token)
    )
    assert r.status_code == 409

    # CU-15: historial
    r = await client.get("/api/v1/simulaciones", headers=auth(estudiante_token))
    assert r.status_code == 200
    assert [s["id"] for s in r.json()] == [sesion_id]

    # CU-15: detalle
    r = await client.get(f"/api/v1/simulaciones/{sesion_id}", headers=auth(estudiante_token))
    assert r.status_code == 200
    assert r.json()["id"] == sesion_id


async def test_no_dos_simulaciones_en_curso_409(
    client: AsyncClient, estudiante_token: str, db_session: AsyncSession
) -> None:
    estu = await _usuario_por_email(db_session, "estu@example.com")
    await _suscribir(db_session, estu.id)
    version_id = await _crear_version(db_session, estu.id)
    cuerpo = {"version_documento_id": version_id, "nivel_dificultad": "ESTANDAR"}
    r = await client.post("/api/v1/simulaciones", json=cuerpo, headers=auth(estudiante_token))
    assert r.status_code == 201
    # Una segunda simulación EN_CURSO no se permite.
    r = await client.post("/api/v1/simulaciones", json=cuerpo, headers=auth(estudiante_token))
    assert r.status_code == 409


async def test_cancelar(
    client: AsyncClient, estudiante_token: str, db_session: AsyncSession
) -> None:
    estu = await _usuario_por_email(db_session, "estu@example.com")
    await _suscribir(db_session, estu.id)
    version_id = await _crear_version(db_session, estu.id)
    r = await client.post(
        "/api/v1/simulaciones",
        json={"version_documento_id": version_id, "nivel_dificultad": "RIGUROSO"},
        headers=auth(estudiante_token),
    )
    sesion_id = r.json()["id"]
    r = await client.post(
        f"/api/v1/simulaciones/{sesion_id}/cancelar", headers=auth(estudiante_token)
    )
    assert r.status_code == 200
    assert r.json()["estado"] == "CANCELADA"


async def test_iniciar_sin_token_401(client: AsyncClient) -> None:
    r = await client.post(
        "/api/v1/simulaciones",
        json={"version_documento_id": 1, "nivel_dificultad": "ESTANDAR"},
    )
    assert r.status_code == 401


async def test_iniciar_sin_suscripcion_402(
    client: AsyncClient, estudiante_token: str, db_session: AsyncSession
) -> None:
    estu = await _usuario_por_email(db_session, "estu@example.com")
    version_id = await _crear_version(db_session, estu.id)  # SIN _suscribir
    r = await client.post(
        "/api/v1/simulaciones",
        json={"version_documento_id": version_id, "nivel_dificultad": "ESTANDAR"},
        headers=auth(estudiante_token),
    )
    assert r.status_code == 402


async def test_iniciar_admin_403(
    client: AsyncClient, admin_token: str, db_session: AsyncSession
) -> None:
    r = await client.post(
        "/api/v1/simulaciones",
        json={"version_documento_id": 1, "nivel_dificultad": "ESTANDAR"},
        headers=auth(admin_token),
    )
    assert r.status_code == 403


async def test_ver_sesion_ajena_404(
    client: AsyncClient,
    estudiante_token: str,
    estudiante2_token: str,
    db_session: AsyncSession,
) -> None:
    estu1 = await _usuario_por_email(db_session, "estu@example.com")
    await _suscribir(db_session, estu1.id)
    version_id = await _crear_version(db_session, estu1.id)
    r = await client.post(
        "/api/v1/simulaciones",
        json={"version_documento_id": version_id, "nivel_dificultad": "ESTANDAR"},
        headers=auth(estudiante_token),
    )
    sesion_id = r.json()["id"]

    # El estudiante 2 NO puede ver ni cerrar la sesión del estudiante 1.
    r = await client.get(f"/api/v1/simulaciones/{sesion_id}", headers=auth(estudiante2_token))
    assert r.status_code == 404
    r = await client.post(
        f"/api/v1/simulaciones/{sesion_id}/finalizar", headers=auth(estudiante2_token)
    )
    assert r.status_code == 404


async def test_iniciar_version_ajena_404(
    client: AsyncClient,
    estudiante_token: str,
    estudiante2_token: str,
    db_session: AsyncSession,
) -> None:
    estu2 = await _usuario_por_email(db_session, "estu2@example.com")
    version_ajena = await _crear_version(db_session, estu2.id)  # versión del estudiante 2
    estu1 = await _usuario_por_email(db_session, "estu@example.com")
    await _suscribir(db_session, estu1.id)
    r = await client.post(
        "/api/v1/simulaciones",
        json={"version_documento_id": version_ajena, "nivel_dificultad": "ESTANDAR"},
        headers=auth(estudiante_token),  # estudiante 1 intenta anclar la versión del 2
    )
    assert r.status_code == 404
