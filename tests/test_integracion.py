"""Tests del submódulo Integracion (CU-14): resultado de la simulación + IA evaluadora."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

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
from app.integrations.evaluador.port import (
    DefensaFeatures,
    EvaluacionDefensaDTO,
    EvaluadorServiceError,
)
from app.integrations.factory import get_evaluador_service
from app.main import app
from app.modules.administracion.suscripciones.models import PlanSuscripcion, Suscripcion
from app.modules.administracion.usuarios.models import Usuario
from app.modules.auditoria_documental.documentos.models import Documento, VersionDocumento
from app.modules.simulador.biometrico.models import MetricaBiometrica
from app.modules.simulador.simulaciones.models import SesionSimulacion


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


class FakeEvaluadorCaido:
    async def evaluar_defensa(self, features: DefensaFeatures) -> EvaluacionDefensaDTO:
        raise EvaluadorServiceError("microservicio caído")


async def _sesion_lista(
    db: AsyncSession, email: str, *, con_suscripcion: bool = True, con_metricas: bool = True
) -> int:
    """Sesión EN_CURSO del usuario; opcionalmente con suscripción activa y métricas."""
    user = (await db.execute(select(Usuario).where(Usuario.email == email))).scalar_one()
    ahora = datetime.now(UTC).replace(tzinfo=None)
    if con_suscripcion:
        plan = PlanSuscripcion(
            nombre="Pro", precio=Decimal("10.00"), moneda="USD", periodo_dias=30, activo=True
        )
        db.add(plan)
        await db.flush()
        db.add(
            Suscripcion(
                usuario_id=user.id,
                plan_id=plan.id,
                estado=EstadoSuscripcion.ACTIVA,
                fecha_inicio=ahora,
                fecha_fin=ahora + timedelta(days=30),
            )
        )
    doc = Documento(usuario_id=user.id, titulo="Tesis")
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
        fecha_inicio=ahora - timedelta(minutes=5),
        fecha_fin=None,
    )
    db.add(sesion)
    await db.flush()
    if con_metricas:
        for post, cv, mul, wpm in [(80.0, 65.0, 2, 130), (78.0, 60.0, 1, 128)]:
            db.add(
                MetricaBiometrica(
                    sesion_id=sesion.id,
                    postura_score=Decimal(str(post)),
                    contacto_visual_pct=Decimal(str(cv)),
                    muletillas_conteo=mul,
                    ritmo_wpm=wpm,
                    momento=ahora,
                )
            )
        await db.flush()
    return sesion.id


async def test_generar_y_obtener_resultado_cu14(
    client: AsyncClient, estudiante_token: str, db_session: AsyncSession
) -> None:
    sesion_id = await _sesion_lista(db_session, "estu@example.com")

    r = await client.post(
        f"/api/v1/simulaciones/{sesion_id}/resultado", headers=auth(estudiante_token)
    )
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["nivel_defensa"] in {"ALTO", "MEDIO", "BAJO"}
    assert cuerpo["oratoria_score"] is not None

    r = await client.get(
        f"/api/v1/simulaciones/{sesion_id}/resultado", headers=auth(estudiante_token)
    )
    assert r.status_code == 200
    assert r.json()["sesion_id"] == sesion_id

    # idempotencia: re-evaluar la misma sesión devuelve el MISMO resultado (200, no 409)
    r = await client.post(
        f"/api/v1/simulaciones/{sesion_id}/resultado", headers=auth(estudiante_token)
    )
    assert r.status_code == 200
    assert r.json()["id"] == cuerpo["id"]


async def test_obtener_sin_resultado_404(
    client: AsyncClient, estudiante_token: str, db_session: AsyncSession
) -> None:
    sesion_id = await _sesion_lista(db_session, "estu@example.com", con_metricas=False)
    r = await client.get(
        f"/api/v1/simulaciones/{sesion_id}/resultado", headers=auth(estudiante_token)
    )
    assert r.status_code == 404


async def test_sin_token_401(client: AsyncClient) -> None:
    r = await client.get("/api/v1/simulaciones/1/resultado")
    assert r.status_code == 401


async def test_sin_suscripcion_402(
    client: AsyncClient, estudiante_token: str, db_session: AsyncSession
) -> None:
    sesion_id = await _sesion_lista(db_session, "estu@example.com", con_suscripcion=False)
    r = await client.get(
        f"/api/v1/simulaciones/{sesion_id}/resultado", headers=auth(estudiante_token)
    )
    assert r.status_code == 402


async def test_rol_incorrecto_403(client: AsyncClient, admin_token: str) -> None:
    r = await client.get("/api/v1/simulaciones/1/resultado", headers=auth(admin_token))
    assert r.status_code == 403


async def test_idor_sesion_ajena_404(
    client: AsyncClient,
    estudiante_token: str,
    estudiante2_token: str,
    db_session: AsyncSession,
) -> None:
    sesion_id = await _sesion_lista(db_session, "estu@example.com")
    await _sesion_lista(db_session, "estu2@example.com")  # estu2 con su propia suscripción
    r = await client.get(
        f"/api/v1/simulaciones/{sesion_id}/resultado", headers=auth(estudiante2_token)
    )
    assert r.status_code == 404


async def test_ia_evaluadora_caida_409(
    client: AsyncClient, estudiante_token: str, db_session: AsyncSession
) -> None:
    app.dependency_overrides[get_evaluador_service] = lambda: FakeEvaluadorCaido()
    try:
        sesion_id = await _sesion_lista(db_session, "estu@example.com")
        r = await client.post(
            f"/api/v1/simulaciones/{sesion_id}/resultado", headers=auth(estudiante_token)
        )
        assert r.status_code == 409
    finally:
        app.dependency_overrides.pop(get_evaluador_service, None)
