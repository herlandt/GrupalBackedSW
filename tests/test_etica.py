"""Tests del submódulo Ética (CU-12)."""

from datetime import datetime
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import (
    EstadoAlertaEtica,
    EstadoAnalisis,
    EstadoEticaTesis,
    EstadoSuscripcion,
    FormatoDocumento,
)
from app.integrations.analysis.etica import detectar_alertas_etica
from app.integrations.analysis.port import AlertaEticaDTO, AnalisisResultadoDTO
from app.modules.administracion.suscripciones.models import PlanSuscripcion, Suscripcion
from app.modules.administracion.usuarios.models import Usuario
from app.modules.auditoria_documental.auditoria.service import AuditoriaService
from app.modules.auditoria_documental.documentos.models import Documento, VersionDocumento
from app.modules.auditoria_documental.etica.models import AlertaEtica
from app.modules.auditoria_documental.etica.service import EticaService
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


# --- CU-12: detección automática durante el análisis -----------------------


def test_heuristica_detecta_riesgo_sin_salvaguarda() -> None:
    texto = (
        "La investigación se aplicó a una muestra de personas (participantes) mediante "
        "una encuesta presencial sobre sus hábitos de estudio."
    )
    alertas = detectar_alertas_etica(texto)
    tipos = {a.tipo for a in alertas}
    assert "INVESTIGACION_SERES_HUMANOS" in tipos
    assert alertas[0].fragmento  # se extrae un fragmento del documento


def test_heuristica_respeta_salvaguarda() -> None:
    texto = (
        "La investigación se aplicó a participantes voluntarios que firmaron un "
        "consentimiento informado, con aprobación del comité de ética institucional."
    )
    assert detectar_alertas_etica(texto) == []


class _FakeAnalysisConEtica:
    """Servicio de análisis de test que devuelve una alerta de ética (CU-12)."""

    async def analizar(
        self, *, version_id: int, archivo_url: str, formato: str
    ) -> AnalisisResultadoDTO:
        return AnalisisResultadoDTO(
            nivel_documento="MEDIO",
            resumen="análisis de prueba",
            observaciones=[],
            alertas_etica=[
                AlertaEticaDTO(tipo="INVESTIGACION_SERES_HUMANOS", fragmento="…participantes…")
            ],
        )

    async def coherencia_discurso(
        self, *, archivo_url: str, formato: str, discurso: str
    ) -> float:
        return 0.0


async def _documento_de_version(db: AsyncSession, version_id: int) -> Documento:
    return (
        await db.execute(
            select(Documento)
            .join(VersionDocumento, VersionDocumento.documento_id == Documento.id)
            .where(VersionDocumento.id == version_id)
        )
    ).scalar_one()


async def test_analisis_abre_alerta_etica_automaticamente(
    client: AsyncClient,
    admin_token: str,
    estudiante_token: str,
    db_session: AsyncSession,
    fake_email: FakeEmail,
) -> None:
    # El sistema (motor de análisis) abre la alerta SOLO, sin POST manual del admin.
    assert admin_token  # crea admin@example.com para que reciba el aviso
    version_id = await _crear_version_de(db_session, "estu@example.com")
    service = AuditoriaService(
        db_session, _FakeAnalysisConEtica(), EticaService(db_session, fake_email)
    )
    await service.procesar_version(version_id)
    await db_session.flush()

    alertas = (
        await db_session.execute(
            select(AlertaEtica).where(AlertaEtica.version_id == version_id)
        )
    ).scalars().all()
    assert len(alertas) == 1
    assert alertas[0].tipo == "INVESTIGACION_SERES_HUMANOS"
    assert alertas[0].estado == EstadoAlertaEtica.PENDIENTE

    # Postcondición: el estado de la tesis pasa a EN_REVISION.
    doc = await _documento_de_version(db_session, version_id)
    assert doc.estado_etico == EstadoEticaTesis.EN_REVISION

    # Notificó al estudiante dueño y al administrador.
    destinatarios = [m["to"] for m in fake_email.messages]
    assert "estu@example.com" in destinatarios
    assert "admin@example.com" in destinatarios


async def test_analisis_no_duplica_alertas_al_reanalizar(
    client: AsyncClient,
    admin_token: str,
    estudiante_token: str,
    db_session: AsyncSession,
    fake_email: FakeEmail,
) -> None:
    version_id = await _crear_version_de(db_session, "estu@example.com")
    etica = EticaService(db_session, fake_email)
    await etica.crear_alerta_si_nueva(version_id, "INVESTIGACION_SERES_HUMANOS", "…")
    await etica.crear_alerta_si_nueva(version_id, "INVESTIGACION_SERES_HUMANOS", "…")
    await db_session.flush()
    alertas = (
        await db_session.execute(
            select(AlertaEtica).where(AlertaEtica.version_id == version_id)
        )
    ).scalars().all()
    assert len(alertas) == 1  # la segunda no se duplicó


async def test_resolver_confirmada_marca_tesis_observada(
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
    # Tras abrir la alerta, la tesis quedó EN_REVISION.
    doc = await _documento_de_version(db_session, version_id)
    assert doc.estado_etico == EstadoEticaTesis.EN_REVISION

    r2 = await client.patch(
        f"/api/v1/etica/alertas/{alerta_id}/resolver",
        json={"estado": "CONFIRMADA"},
        headers=auth(admin_token),
    )
    assert r2.status_code == 200
    await db_session.refresh(doc)
    assert doc.estado_etico == EstadoEticaTesis.OBSERVADA


async def _crear_alerta(client: AsyncClient, admin_token: str, version_id: int, tipo: str) -> int:
    r = await client.post(
        "/api/v1/etica/alertas",
        json={"version_id": version_id, "tipo": tipo},
        headers=auth(admin_token),
    )
    return int(r.json()["id"])


async def test_estado_tesis_se_deriva_de_todas_las_alertas_cu12(
    client: AsyncClient,
    admin_token: str,
    estudiante_token: str,
    db_session: AsyncSession,
    fake_email: FakeEmail,
) -> None:
    # CU-12: con varias alertas, desestimar una NO debe borrar un incumplimiento confirmado.
    assert estudiante_token
    version_id = await _crear_version_de(db_session, "estu@example.com")
    a1 = await _crear_alerta(client, admin_token, version_id, "PLAGIO")
    a2 = await _crear_alerta(client, admin_token, version_id, "AUTOPLAGIO")

    # Confirmar A -> la tesis queda OBSERVADA.
    await client.patch(
        f"/api/v1/etica/alertas/{a1}/resolver",
        json={"estado": "CONFIRMADA"},
        headers=auth(admin_token),
    )
    doc = await _documento_de_version(db_session, version_id)
    assert doc.estado_etico == EstadoEticaTesis.OBSERVADA

    # Desestimar B -> SIGUE OBSERVADA (A confirmada persiste), no se "limpia".
    await client.patch(
        f"/api/v1/etica/alertas/{a2}/resolver",
        json={"estado": "DESESTIMADA"},
        headers=auth(admin_token),
    )
    await db_session.refresh(doc)
    assert doc.estado_etico == EstadoEticaTesis.OBSERVADA


async def test_estado_tesis_pendientes_y_limpio_cu12(
    client: AsyncClient,
    admin_token: str,
    estudiante_token: str,
    db_session: AsyncSession,
    fake_email: FakeEmail,
) -> None:
    # CU-12: desestimar una de dos PENDIENTE deja EN_REVISION; desestimar ambas -> LIMPIO.
    assert estudiante_token
    version_id = await _crear_version_de(db_session, "estu@example.com")
    a1 = await _crear_alerta(client, admin_token, version_id, "PLAGIO")
    a2 = await _crear_alerta(client, admin_token, version_id, "AUTOPLAGIO")

    await client.patch(
        f"/api/v1/etica/alertas/{a1}/resolver",
        json={"estado": "DESESTIMADA"},
        headers=auth(admin_token),
    )
    doc = await _documento_de_version(db_session, version_id)
    assert doc.estado_etico == EstadoEticaTesis.EN_REVISION  # queda B PENDIENTE

    await client.patch(
        f"/api/v1/etica/alertas/{a2}/resolver",
        json={"estado": "DESESTIMADA"},
        headers=auth(admin_token),
    )
    await db_session.refresh(doc)
    assert doc.estado_etico == EstadoEticaTesis.LIMPIO  # ninguna activa
