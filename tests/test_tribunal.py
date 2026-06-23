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
from app.integrations.factory import get_transcription, get_tribunal_llm
from app.integrations.llm.port import EvaluacionDTO, PreguntaGeneradaDTO
from app.main import app
from app.modules.administracion.suscripciones.models import PlanSuscripcion, Suscripcion
from app.modules.administracion.usuarios.models import Usuario
from app.modules.auditoria_documental.documentos.models import Documento, VersionDocumento
from app.modules.simulador.simulaciones.models import SesionSimulacion
from app.modules.simulador.tribunal.models import RespuestaEstudiante


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


async def test_voz_pregunta_devuelve_audio(
    client: AsyncClient, estudiante_token: str, db_session: AsyncSession, fake_llm: None
) -> None:
    sesion_id = await _crear_sesion(db_session, "estu@example.com")
    r = await client.post(
        f"/api/v1/tribunal/sesiones/{sesion_id}/preguntas", headers=auth(estudiante_token)
    )
    pregunta_id = r.json()[0]["id"]

    # CU-16 (voz): el endpoint devuelve audio (en tests, el StubTTS da bytes fijos).
    r = await client.get(
        f"/api/v1/tribunal/preguntas/{pregunta_id}/voz", headers=auth(estudiante_token)
    )
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "audio/mpeg"
    assert r.content == b"STUB_TTS_AUDIO"

    # 404: pregunta inexistente (o ajena) no revela existencia.
    r = await client.get(
        "/api/v1/tribunal/preguntas/999999/voz", headers=auth(estudiante_token)
    )
    assert r.status_code == 404


async def test_atencion_penaliza_puntuacion(
    client: AsyncClient, estudiante_token: str, db_session: AsyncSession, fake_llm: None
) -> None:
    sesion_id = await _crear_sesion(db_session, "estu@example.com")
    r = await client.post(
        f"/api/v1/tribunal/sesiones/{sesion_id}/preguntas", headers=auth(estudiante_token)
    )
    pid = r.json()[0]["id"]

    # atencion=0 (miró a otro lado) penaliza: 8.5 * (0.6 + 0.4*0) = 5.10 y añade observación.
    r = await client.post(
        f"/api/v1/tribunal/preguntas/{pid}/respuesta",
        json={"texto": "respuesta razonada", "atencion": 0.0},
        headers=auth(estudiante_token),
    )
    assert r.status_code == 201, r.text
    assert float(r.json()["puntuacion"]) == 5.10
    assert "contacto visual" in (r.json()["observaciones"] or "").lower()


async def test_atencion_alta_no_penaliza(
    client: AsyncClient, estudiante_token: str, db_session: AsyncSession, fake_llm: None
) -> None:
    sesion_id = await _crear_sesion(db_session, "estu@example.com")
    r = await client.post(
        f"/api/v1/tribunal/sesiones/{sesion_id}/preguntas", headers=auth(estudiante_token)
    )
    pid = r.json()[1]["id"]
    r = await client.post(
        f"/api/v1/tribunal/preguntas/{pid}/respuesta",
        json={"texto": "respuesta razonada", "atencion": 1.0},
        headers=auth(estudiante_token),
    )
    assert r.status_code == 201
    assert float(r.json()["puntuacion"]) == 8.5  # sin penalización


class FakeTranscription:
    async def transcribir(self, audio_url: str) -> str:
        return "respuesta transcrita del audio"


@pytest.fixture
def fake_transcription() -> Iterator[None]:
    app.dependency_overrides[get_transcription] = lambda: FakeTranscription()
    yield
    app.dependency_overrides.pop(get_transcription, None)


async def test_respuesta_por_voz_se_transcribe_y_evalua(
    client: AsyncClient,
    estudiante_token: str,
    db_session: AsyncSession,
    fake_llm: None,
    fake_transcription: None,
) -> None:
    # CU-16: respuesta SOLO audio (sin texto) -> el backend transcribe y evalúa ese texto.
    sesion_id = await _crear_sesion(db_session, "estu@example.com")
    r = await client.post(
        f"/api/v1/tribunal/sesiones/{sesion_id}/preguntas", headers=auth(estudiante_token)
    )
    pid = r.json()[0]["id"]
    r = await client.post(
        f"/api/v1/tribunal/preguntas/{pid}/respuesta",
        json={"audio_url": "s3://bucket/respuesta.mp3"},
        headers=auth(estudiante_token),
    )
    assert r.status_code == 201, r.text
    assert float(r.json()["puntuacion"]) == 8.5  # evaluó contenido, no cadena vacía
    # Se persistió el texto transcrito en la respuesta.
    resp = (
        await db_session.execute(
            select(RespuestaEstudiante).where(RespuestaEstudiante.pregunta_id == pid)
        )
    ).scalar_one()
    assert resp.texto == "respuesta transcrita del audio"


async def test_timeout_registra_pregunta_sin_respuesta(
    client: AsyncClient, estudiante_token: str, db_session: AsyncSession, fake_llm: None
) -> None:
    # CU-16 (excepción): se agota el tiempo -> queda registrada sin respuesta y se avanza.
    sesion_id = await _crear_sesion(db_session, "estu@example.com")
    r = await client.post(
        f"/api/v1/tribunal/sesiones/{sesion_id}/preguntas", headers=auth(estudiante_token)
    )
    pid = r.json()[0]["id"]
    r = await client.post(
        f"/api/v1/tribunal/preguntas/{pid}/timeout", headers=auth(estudiante_token)
    )
    assert r.status_code == 201, r.text
    assert float(r.json()["puntuacion"]) == 0.0
    assert r.json()["profundidad"] == "NINGUNA"
    # La evaluación queda consultable (CU-17 tiene el dato).
    r = await client.get(
        f"/api/v1/tribunal/preguntas/{pid}/evaluacion", headers=auth(estudiante_token)
    )
    assert r.status_code == 200
    # Ya registrada: no se puede responder después.
    r = await client.post(
        f"/api/v1/tribunal/preguntas/{pid}/respuesta",
        json={"texto": "tarde"},
        headers=auth(estudiante_token),
    )
    assert r.status_code == 409


async def test_informe_pdf_tribunal_cu17(
    client: AsyncClient, estudiante_token: str, db_session: AsyncSession, fake_llm: None
) -> None:
    # CU-17: descarga del informe de evaluación del tribunal en PDF.
    sesion_id = await _crear_sesion(db_session, "estu@example.com")
    r = await client.post(
        f"/api/v1/tribunal/sesiones/{sesion_id}/preguntas", headers=auth(estudiante_token)
    )
    pid = r.json()[0]["id"]
    await client.post(
        f"/api/v1/tribunal/preguntas/{pid}/respuesta",
        json={"texto": "respuesta razonada"},
        headers=auth(estudiante_token),
    )
    r = await client.get(
        f"/api/v1/tribunal/sesiones/{sesion_id}/informe", headers=auth(estudiante_token)
    )
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:4] == b"%PDF"


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
