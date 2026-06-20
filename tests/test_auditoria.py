"""Tests del submódulo Auditoria (CU-10, RF-01, RF-02 + worker)."""

from collections.abc import Iterator
from datetime import datetime
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.enums import EstadoAnalisis, EstadoSuscripcion, FormatoDocumento
from app.integrations.analysis.port import (
    AnalisisResultadoDTO,
    AnalysisServiceError,
    ObservacionDTO,
)
from app.integrations.factory import get_analysis_service
from app.main import app
from app.modules.administracion.suscripciones.models import PlanSuscripcion, Suscripcion
from app.modules.administracion.usuarios.models import Usuario
from app.modules.auditoria_documental.documentos.models import Documento, VersionDocumento

# El endpoint interno del worker exige el secreto compartido por cabecera.
INTERNAL = {"X-Internal-Token": settings.internal_api_token}


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


class FakeAnalysis:
    async def analizar(
        self, *, version_id: int, archivo_url: str, formato: str
    ) -> AnalisisResultadoDTO:
        return AnalisisResultadoDTO(
            nivel_documento="ALTO",
            resumen="ok",
            observaciones=[
                ObservacionDTO(categoria="COHERENCIA", severidad="alta", descripcion="c"),
                ObservacionDTO(categoria="NORMAS", severidad="baja", descripcion="n"),
            ],
        )


@pytest.fixture
def fake_analysis() -> Iterator[None]:
    app.dependency_overrides[get_analysis_service] = lambda: FakeAnalysis()
    yield
    app.dependency_overrides.pop(get_analysis_service, None)


async def _estudiante(db_session: AsyncSession) -> Usuario:
    result = await db_session.execute(select(Usuario).where(Usuario.email == "estu@example.com"))
    return result.scalar_one()


async def _crear_version(db_session: AsyncSession, usuario: Usuario) -> int:
    documento = Documento(usuario_id=usuario.id, titulo="Tesis")
    db_session.add(documento)
    await db_session.flush()
    version = VersionDocumento(
        documento_id=documento.id,
        numero_version=1,
        archivo_url="/media/x.pdf",
        formato=FormatoDocumento.PDF,
        estado_analisis=EstadoAnalisis.PENDIENTE,
    )
    db_session.add(version)
    await db_session.flush()
    return version.id


async def _dar_suscripcion(db_session: AsyncSession, usuario: Usuario) -> None:
    plan = PlanSuscripcion(nombre="Plan", precio=Decimal("9.99"), moneda="USD", periodo_dias=30)
    db_session.add(plan)
    await db_session.flush()
    db_session.add(
        Suscripcion(
            usuario_id=usuario.id,
            plan_id=plan.id,
            estado=EstadoSuscripcion.ACTIVA,
            fecha_inicio=datetime(2020, 1, 1),
            fecha_fin=datetime(2999, 1, 1),
        )
    )
    await db_session.flush()


async def _version_con_suscripcion(db_session: AsyncSession) -> int:
    usuario = await _estudiante(db_session)
    await _dar_suscripcion(db_session, usuario)
    return await _crear_version(db_session, usuario)


async def test_worker_procesa_y_lectura_cu10(
    client: AsyncClient, estudiante_token: str, db_session: AsyncSession, fake_analysis: None
) -> None:
    version_id = await _version_con_suscripcion(db_session)

    r = await client.post(
        f"/api/v1/auditoria/internal/procesar/{version_id}", headers=INTERNAL
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "ok"

    r = await client.get(
        f"/api/v1/auditoria/versiones/{version_id}/resultado", headers=auth(estudiante_token)
    )
    assert r.status_code == 200
    assert r.json()["nivel_documento"] == "ALTO"
    assert len(r.json()["observaciones"]) == 2

    r = await client.get(
        f"/api/v1/auditoria/versiones/{version_id}/resultado",
        params={"categoria": "NORMAS"},
        headers=auth(estudiante_token),
    )
    assert r.status_code == 200
    obs = r.json()["observaciones"]
    assert obs and all(o["categoria"] == "NORMAS" for o in obs)


async def test_resultado_inexistente_404(
    client: AsyncClient, estudiante_token: str, db_session: AsyncSession
) -> None:
    version_id = await _version_con_suscripcion(db_session)
    r = await client.get(
        f"/api/v1/auditoria/versiones/{version_id}/resultado", headers=auth(estudiante_token)
    )
    assert r.status_code == 404


async def test_resultado_sin_token_401(client: AsyncClient) -> None:
    r = await client.get("/api/v1/auditoria/versiones/1/resultado")
    assert r.status_code == 401


async def test_resultado_sin_suscripcion_402(
    client: AsyncClient, estudiante_token: str, db_session: AsyncSession
) -> None:
    usuario = await _estudiante(db_session)
    version_id = await _crear_version(db_session, usuario)
    r = await client.get(
        f"/api/v1/auditoria/versiones/{version_id}/resultado", headers=auth(estudiante_token)
    )
    assert r.status_code == 402


async def test_worker_doble_procesar_409(
    client: AsyncClient, estudiante_token: str, db_session: AsyncSession, fake_analysis: None
) -> None:
    version_id = await _version_con_suscripcion(db_session)
    r = await client.post(
        f"/api/v1/auditoria/internal/procesar/{version_id}", headers=INTERNAL
    )
    assert r.status_code == 200
    r = await client.post(
        f"/api/v1/auditoria/internal/procesar/{version_id}", headers=INTERNAL
    )
    assert r.status_code == 409


async def test_internal_sin_secreto_401(
    client: AsyncClient, estudiante_token: str, db_session: AsyncSession
) -> None:
    assert estudiante_token  # registra al estudiante dueño de la versión
    version_id = await _version_con_suscripcion(db_session)
    r = await client.post(f"/api/v1/auditoria/internal/procesar/{version_id}")
    assert r.status_code == 401


async def test_idor_resultado_de_version_ajena_404(
    client: AsyncClient,
    estudiante_token: str,
    estudiante2_token: str,
    db_session: AsyncSession,
    fake_analysis: None,
) -> None:
    # Versión + resultado del primer estudiante.
    version_id = await _version_con_suscripcion(db_session)
    r = await client.post(
        f"/api/v1/auditoria/internal/procesar/{version_id}", headers=INTERNAL
    )
    assert r.status_code == 200
    # El segundo estudiante (con su propia suscripción) NO debe ver la versión ajena:
    # se trata como inexistente (404), sin filtrar su existencia.
    estu2 = (
        await db_session.execute(select(Usuario).where(Usuario.email == "estu2@example.com"))
    ).scalar_one()
    await _dar_suscripcion(db_session, estu2)
    r = await client.get(
        f"/api/v1/auditoria/versiones/{version_id}/resultado",
        headers=auth(estudiante2_token),
    )
    assert r.status_code == 404


async def test_estado_con_suscripcion(
    client: AsyncClient, estudiante_token: str, db_session: AsyncSession
) -> None:
    version_id = await _version_con_suscripcion(db_session)
    r = await client.get(
        f"/api/v1/auditoria/versiones/{version_id}/estado", headers=auth(estudiante_token)
    )
    assert r.status_code == 200
    assert r.json()["estado_analisis"] == "PENDIENTE"
    assert r.json()["tiene_resultado"] is False


async def test_estado_sin_suscripcion_402(
    client: AsyncClient, estudiante_token: str, db_session: AsyncSession
) -> None:
    usuario = await _estudiante(db_session)
    version_id = await _crear_version(db_session, usuario)
    r = await client.get(
        f"/api/v1/auditoria/versiones/{version_id}/estado", headers=auth(estudiante_token)
    )
    assert r.status_code == 402


class _FakeAnalysisError:
    async def analizar(self, *, version_id: int, archivo_url: str, formato: str) -> object:
        raise AnalysisServiceError("falló el análisis")


async def test_worker_error_persiste_estado_error(
    client: AsyncClient, estudiante_token: str, db_session: AsyncSession
) -> None:
    assert estudiante_token  # registra al estudiante dueño de la versión
    app.dependency_overrides[get_analysis_service] = lambda: _FakeAnalysisError()
    try:
        version_id = await _version_con_suscripcion(db_session)
        r = await client.post(
            f"/api/v1/auditoria/internal/procesar/{version_id}", headers=INTERNAL
        )
        assert r.status_code == 502
        assert r.json()["status"] == "error"
        version = await db_session.get(VersionDocumento, version_id)
        assert version is not None and version.estado_analisis == EstadoAnalisis.ERROR
    finally:
        app.dependency_overrides.pop(get_analysis_service, None)


async def test_estudiante_analiza_su_version_cu08(
    client: AsyncClient, estudiante_token: str, db_session: AsyncSession, fake_analysis: None
) -> None:
    version_id = await _version_con_suscripcion(db_session)
    # El estudiante dispara el análisis de su propia versión (sin token interno).
    r = await client.post(
        f"/api/v1/auditoria/versiones/{version_id}/analizar", headers=auth(estudiante_token)
    )
    assert r.status_code == 200, r.text
    assert r.json()["estado_analisis"] == "COMPLETADO"
    # ahora el informe ya existe.
    r = await client.get(
        f"/api/v1/auditoria/versiones/{version_id}/resultado", headers=auth(estudiante_token)
    )
    assert r.status_code == 200
    assert r.json()["nivel_documento"] == "ALTO"
    # idempotente: re-analizar devuelve 200, no error.
    r = await client.post(
        f"/api/v1/auditoria/versiones/{version_id}/analizar", headers=auth(estudiante_token)
    )
    assert r.status_code == 200
