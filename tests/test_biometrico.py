"""Tests del submódulo Biometrico — ExpoLens (CU-14, RF-03/04/05) con servicio fake."""

import io
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
from app.integrations.biometric.port import BiometricServiceError, SegmentoMetricasDTO
from app.integrations.factory import get_biometric_service
from app.main import app
from app.modules.administracion.suscripciones.models import PlanSuscripcion, Suscripcion
from app.modules.administracion.usuarios.models import Usuario
from app.modules.auditoria_documental.documentos.models import Documento, VersionDocumento
from app.modules.simulador.simulaciones.models import SesionSimulacion


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


class FakeBiometric:
    async def analizar_segmento(
        self, *, sesion_id: int, audio_url: str | None, video_url: str | None
    ) -> SegmentoMetricasDTO:
        return SegmentoMetricasDTO(
            postura_score=80.0, contacto_visual_pct=60.0, muletillas_conteo=2, ritmo_wpm=130
        )

    async def analizar_imagen(self, *, imagen: bytes) -> SegmentoMetricasDTO:
        return SegmentoMetricasDTO(
            postura_score=85.0, contacto_visual_pct=70.0, muletillas_conteo=0, ritmo_wpm=None
        )


class FakeBiometricCaido:
    async def analizar_segmento(
        self, *, sesion_id: int, audio_url: str | None, video_url: str | None
    ) -> SegmentoMetricasDTO:
        raise BiometricServiceError("servicio biométrico no disponible")


async def _usuario(db: AsyncSession, email: str) -> Usuario:
    user = (await db.execute(select(Usuario).where(Usuario.email == email))).scalar_one()
    return user


async def _sesion_con_suscripcion(db: AsyncSession, email: str, con_suscripcion: bool) -> int:
    """Prepara una sesión EN_CURSO del usuario; opcionalmente le da suscripción activa."""
    user = await _usuario(db, email)
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
                fecha_inicio=datetime.now(UTC).replace(tzinfo=None),
                fecha_fin=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=30),
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
        fecha_inicio=datetime.now(UTC).replace(tzinfo=None),
        fecha_fin=None,
    )
    db.add(sesion)
    await db.flush()
    return sesion.id


async def test_segmento_y_resumen_cu14(
    client: AsyncClient, estudiante_token: str, db_session: AsyncSession
) -> None:
    app.dependency_overrides[get_biometric_service] = lambda: FakeBiometric()
    try:
        sesion_id = await _sesion_con_suscripcion(db_session, "estu@example.com", True)

        r = await client.post(
            f"/api/v1/biometrico/sesiones/{sesion_id}/segmentos",
            json={"audio_url": "s3://b/a.wav", "video_url": "s3://b/v.mp4"},
            headers=auth(estudiante_token),
        )
        assert r.status_code == 201, r.text
        assert r.json()["muletillas_conteo"] == 2

        r = await client.get(
            f"/api/v1/biometrico/sesiones/{sesion_id}/resumen", headers=auth(estudiante_token)
        )
        assert r.status_code == 200
        assert r.json()["intervalos"] == 1
        assert r.json()["muletillas_total"] == 2
        assert r.json()["sugerencia"]  # CU-14: sugerencia en vivo tras acumular datos

        r = await client.get(
            f"/api/v1/biometrico/sesiones/{sesion_id}/metricas", headers=auth(estudiante_token)
        )
        assert r.status_code == 200
        assert len(r.json()) == 1
    finally:
        app.dependency_overrides.pop(get_biometric_service, None)


def test_sugerencia_en_vivo_cu14() -> None:
    from app.modules.simulador.biometrico.service import _sugerencia_en_vivo

    # Sin datos: el sistema espera (no sugiere todavía).
    assert _sugerencia_en_vivo({"intervalos": 0}) is None
    # Prioriza el mayor fallo: poco contacto visual.
    s = _sugerencia_en_vivo(
        {
            "intervalos": 3,
            "contacto_visual_pct_promedio": Decimal("30"),
            "postura_score_promedio": Decimal("80"),
            "muletillas_total": 0,
            "pausas_total": 0,
            "ritmo_wpm_promedio": 120,
        }
    )
    assert s is not None and "contacto visual" in s.lower()


async def test_sin_token_401(client: AsyncClient) -> None:
    r = await client.get("/api/v1/biometrico/sesiones/1/resumen")
    assert r.status_code == 401


async def test_sin_suscripcion_402(
    client: AsyncClient, estudiante_token: str, db_session: AsyncSession
) -> None:
    sesion_id = await _sesion_con_suscripcion(db_session, "estu@example.com", False)
    r = await client.get(
        f"/api/v1/biometrico/sesiones/{sesion_id}/resumen", headers=auth(estudiante_token)
    )
    assert r.status_code == 402


async def test_rol_incorrecto_403(client: AsyncClient, admin_token: str) -> None:
    r = await client.get("/api/v1/biometrico/sesiones/1/resumen", headers=auth(admin_token))
    assert r.status_code == 403


async def test_idor_sesion_ajena_404(
    client: AsyncClient,
    estudiante_token: str,
    estudiante2_token: str,
    db_session: AsyncSession,
) -> None:
    # La sesión es del PRIMER estudiante; el SEGUNDO (con su propia suscripción) no debe verla.
    sesion_id = await _sesion_con_suscripcion(db_session, "estu@example.com", True)
    await _sesion_con_suscripcion(db_session, "estu2@example.com", True)
    r = await client.get(
        f"/api/v1/biometrico/sesiones/{sesion_id}/resumen", headers=auth(estudiante2_token)
    )
    assert r.status_code == 404


async def test_servicio_biometrico_caido_502(
    client: AsyncClient, estudiante_token: str, db_session: AsyncSession
) -> None:
    app.dependency_overrides[get_biometric_service] = lambda: FakeBiometricCaido()
    try:
        sesion_id = await _sesion_con_suscripcion(db_session, "estu@example.com", True)
        r = await client.post(
            f"/api/v1/biometrico/sesiones/{sesion_id}/segmentos",
            json={"audio_url": "s3://b/a.wav"},
            headers=auth(estudiante_token),
        )
        assert r.status_code == 502
        # No se persistió ninguna métrica.
        r = await client.get(
            f"/api/v1/biometrico/sesiones/{sesion_id}/metricas", headers=auth(estudiante_token)
        )
        assert r.json() == []
    finally:
        app.dependency_overrides.pop(get_biometric_service, None)


async def test_frame_camara_cu14(
    client: AsyncClient, estudiante_token: str, db_session: AsyncSession
) -> None:
    app.dependency_overrides[get_biometric_service] = lambda: FakeBiometric()
    try:
        sesion_id = await _sesion_con_suscripcion(db_session, "estu@example.com", True)
        r = await client.post(
            f"/api/v1/biometrico/sesiones/{sesion_id}/frame",
            files={"file": ("frame.jpg", io.BytesIO(b"\xff\xd8\xff jpeg-fake"), "image/jpeg")},
            headers=auth(estudiante_token),
        )
        assert r.status_code == 201, r.text
        assert r.json()["postura_score"] is not None
    finally:
        app.dependency_overrides.pop(get_biometric_service, None)
