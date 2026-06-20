"""Tests del submódulo Tribunal (CU-16, CU-17, RF-06, RF-07)."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import (
    EstadoAnalisis,
    EstadoSesion,
    EstadoSuscripcion,
    FormatoDocumento,
    NivelDificultad,
)
from app.integrations.factory import get_tribunal_llm
from app.integrations.llm.port import EvaluacionDTO, PreguntaGeneradaDTO
from app.main import app
from app.modules.administracion.suscripciones.models import PlanSuscripcion, Suscripcion
from app.modules.administracion.usuarios.models import Usuario
from app.modules.auditoria_documental.documentos.models import Documento, VersionDocumento
from app.modules.simulador.simulaciones.models import SesionSimulacion


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class FakeTribunalLLM:
    async def generar_preguntas(
        self, *, archivo_url: str, formato: str, nivel_dificultad: str
    ) -> list[PreguntaGeneradaDTO]:
        return [
            PreguntaGeneradaDTO(orden=1, texto="P1"),
            PreguntaGeneradaDTO(orden=2, texto="P2"),
        ]

    async def evaluar_respuesta(self, *, pregunta: str, respuesta: str) -> EvaluacionDTO:
        return EvaluacionDTO(puntuacion=8.5, observaciones="bien", profundidad="alta")


@pytest.fixture
def fake_llm() -> Iterator[None]:
    app.dependency_overrides[get_tribunal_llm] = lambda: FakeTribunalLLM()
    yield
    app.dependency_overrides.pop(get_tribunal_llm, None)


async def _crear_sesion(db: AsyncSession, email: str, *, suscribir: bool = True) -> int:
    """Crea (opcionalmente) suscripción + documento + versión + sesión EN_CURSO."""
    user = (await db.execute(select(Usuario).where(Usuario.email == email))).scalar_one()
    if suscribir:
        plan = PlanSuscripcion(
            nombre="Plan", precio=Decimal("9.99"), moneda="USD", periodo_dias=30
        )
        db.add(plan)
        await db.flush()
        db.add(
            Suscripcion(
                usuario_id=user.id,
                plan_id=plan.id,
                estado=EstadoSuscripcion.ACTIVA,
                fecha_inicio=_now(),
                fecha_fin=_now() + timedelta(days=30),
            )
        )
        await db.flush()
    doc = Documento(usuario_id=user.id, titulo="Tesis demo")
    db.add(doc)
    await db.flush()
    version = VersionDocumento(
        documento_id=doc.id,
        numero_version=1,
        archivo_url="s3://bucket/tesis.pdf",
        formato=FormatoDocumento.PDF,
        estado_analisis=EstadoAnalisis.COMPLETADO,
    )
    db.add(version)
    await db.flush()
    sesion = SesionSimulacion(
        usuario_id=user.id,
        version_documento_id=version.id,
        nivel_dificultad=NivelDificultad.ESTANDAR,
        estado=EstadoSesion.EN_CURSO,
        fecha_inicio=_now(),
        fecha_fin=None,
    )
    db.add(sesion)
    await db.flush()
    return sesion.id


async def test_happy_path_genera_responde_evalua(
    client: AsyncClient, estudiante_token: str, db_session: AsyncSession, fake_llm: None
) -> None:
    sesion_id = await _crear_sesion(db_session, "estu@example.com")

    # RF-06: generar preguntas
    r = await client.post(
        f"/api/v1/tribunal/sesiones/{sesion_id}/preguntas", headers=auth(estudiante_token)
    )
    assert r.status_code == 201, r.text
    preguntas = r.json()
    assert len(preguntas) == 2
    pregunta_id = preguntas[0]["id"]

    # 409: regenerar preguntas en una sesión que ya las tiene
    r = await client.post(
        f"/api/v1/tribunal/sesiones/{sesion_id}/preguntas", headers=auth(estudiante_token)
    )
    assert r.status_code == 409

    # CU-16 + RF-07: responder por texto y recibir la evaluación
    r = await client.post(
        f"/api/v1/tribunal/preguntas/{pregunta_id}/respuesta",
        json={"texto": "Mi respuesta razonada."},
        headers=auth(estudiante_token),
    )
    assert r.status_code == 201
    assert r.json()["profundidad"] == "alta"

    # CU-17: consultar la evaluación
    r = await client.get(
        f"/api/v1/tribunal/preguntas/{pregunta_id}/evaluacion", headers=auth(estudiante_token)
    )
    assert r.status_code == 200
    assert float(r.json()["puntuacion"]) == 8.5

    # 422: respuesta vacía (ni texto ni audio)
    r = await client.post(
        f"/api/v1/tribunal/preguntas/{preguntas[1]['id']}/respuesta",
        json={},
        headers=auth(estudiante_token),
    )
    assert r.status_code == 422

    # 409: responder dos veces la misma pregunta
    r = await client.post(
        f"/api/v1/tribunal/preguntas/{pregunta_id}/respuesta",
        json={"texto": "otra vez"},
        headers=auth(estudiante_token),
    )
    assert r.status_code == 409


async def test_401_sin_token(client: AsyncClient) -> None:
    r = await client.post("/api/v1/tribunal/sesiones/1/preguntas")
    assert r.status_code == 401


async def test_402_sin_suscripcion(
    client: AsyncClient, estudiante_token: str, db_session: AsyncSession, fake_llm: None
) -> None:
    sesion_id = await _crear_sesion(db_session, "estu@example.com", suscribir=False)
    r = await client.post(
        f"/api/v1/tribunal/sesiones/{sesion_id}/preguntas", headers=auth(estudiante_token)
    )
    assert r.status_code == 402


async def test_403_rol_incorrecto(client: AsyncClient, admin_token: str) -> None:
    r = await client.post("/api/v1/tribunal/sesiones/1/preguntas", headers=auth(admin_token))
    assert r.status_code == 403


async def test_404_idor_sesion_de_otro(
    client: AsyncClient,
    estudiante_token: str,
    estudiante2_token: str,
    db_session: AsyncSession,
    fake_llm: None,
) -> None:
    # La sesión pertenece al estudiante 2...
    sesion_id = await _crear_sesion(db_session, "estu2@example.com")
    # ...pero el estudiante 1 (con su propia suscripción) intenta acceder.
    await _crear_sesion(db_session, "estu@example.com")
    r = await client.post(
        f"/api/v1/tribunal/sesiones/{sesion_id}/preguntas", headers=auth(estudiante_token)
    )
    assert r.status_code == 404  # tratado como inexistente, no 403
