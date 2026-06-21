"""Lógica de negocio — submódulo biometrico (CU-14, RF-03/04/05).

Persiste y agrega las métricas biométricas de una sesión de simulación. No conoce HTTP.
El análisis pesado (Transcribe + Rekognition) vive tras `BiometricServicePort`.
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit.service import AuditService
from app.core.enums import EstadoSesion
from app.core.exceptions import BusinessRuleError, ResourceNotFoundError
from app.integrations.biometric.port import BiometricServicePort
from app.modules.administracion.usuarios.models import Usuario
from app.modules.simulador.biometrico.models import MetricaBiometrica
from app.modules.simulador.biometrico.repository import MetricaBiometricaRepository
from app.modules.simulador.biometrico.schemas import SegmentoIn
from app.modules.simulador.simulaciones.models import SesionSimulacion
from app.modules.simulador.simulaciones.repository import SesionSimulacionRepository


def _now() -> datetime:
    """Instante actual en UTC, sin zona (las columnas son TIMESTAMP naive)."""
    return datetime.now(UTC).replace(tzinfo=None)


def _dec(valor: float | None) -> Decimal | None:
    """Convierte un float del DTO a Decimal (Numeric(5,2)) sin imprecisión de float."""
    return Decimal(str(valor)) if valor is not None else None


class BiometricoService:
    def __init__(self, db: AsyncSession, biometric: BiometricServicePort) -> None:
        self.db = db
        self.metricas = MetricaBiometricaRepository(db)
        self.sesiones = SesionSimulacionRepository(db)
        self.audit = AuditService(db)
        self.biometric = biometric

    # --- Helpers (IDOR) -------------------------------------------------
    async def _sesion_del_usuario(self, sesion_id: int, usuario: Usuario) -> SesionSimulacion:
        """Resuelve la sesión y verifica que pertenece al estudiante (anti-IDOR).

        Una sesión ajena se trata como inexistente (404), para no revelar su existencia.
        """
        sesion = await self.sesiones.get(sesion_id)
        if sesion is None or sesion.usuario_id != usuario.id:
            raise ResourceNotFoundError(f"Sesión {sesion_id} no existe")
        return sesion

    # --- CU-14 (escritura): analiza un segmento y persiste una métrica --
    async def analizar_segmento(
        self, sesion_id: int, usuario: Usuario, data: SegmentoIn
    ) -> MetricaBiometrica:
        sesion = await self._sesion_del_usuario(sesion_id, usuario)
        if sesion.estado != EstadoSesion.EN_CURSO:
            raise BusinessRuleError("La sesión no está en curso; no admite más análisis.")

        # Si el análisis falla, BiometricServiceError se propaga al router (→ 502) y no se
        # persiste ninguna métrica (get_db revierte la transacción).
        dto = await self.biometric.analizar_segmento(
            sesion_id=sesion.id, audio_url=data.audio_url, video_url=data.video_url
        )

        metrica = MetricaBiometrica(
            sesion_id=sesion.id,
            postura_score=_dec(dto.postura_score),
            muletillas_conteo=dto.muletillas_conteo,
            ritmo_wpm=dto.ritmo_wpm,
            contacto_visual_pct=_dec(dto.contacto_visual_pct),
            momento=data.momento.replace(tzinfo=None) if data.momento else _now(),
        )
        await self.metricas.add(metrica)  # flush -> metrica.id disponible
        await self.audit.log(
            actor_id=usuario.id,
            accion="BIOMETRIA_SEGMENTO_ANALIZADO",
            entidad="metrica_biometrica",
            entidad_id=metrica.id,
            metadata={"sesion_id": sesion.id},
        )
        return metrica

    # --- CU-14 (escritura): analiza un frame de la cámara (RF-04) -------
    async def analizar_frame(
        self, sesion_id: int, usuario: Usuario, imagen: bytes
    ) -> MetricaBiometrica:
        sesion = await self._sesion_del_usuario(sesion_id, usuario)
        if sesion.estado != EstadoSesion.EN_CURSO:
            raise BusinessRuleError("La sesión no está en curso; no admite más análisis.")
        dto = await self.biometric.analizar_imagen(imagen=imagen)
        metrica = MetricaBiometrica(
            sesion_id=sesion.id,
            postura_score=_dec(dto.postura_score),
            muletillas_conteo=dto.muletillas_conteo,
            ritmo_wpm=dto.ritmo_wpm,
            contacto_visual_pct=_dec(dto.contacto_visual_pct),
            momento=_now(),
        )
        await self.metricas.add(metrica)
        await self.audit.log(
            actor_id=usuario.id,
            accion="BIOMETRIA_FRAME_ANALIZADO",
            entidad="metrica_biometrica",
            entidad_id=metrica.id,
            metadata={"sesion_id": sesion.id},
        )
        return metrica

    # --- CU-14 (escritura): segmento de AUDIO en vivo (RF-05) ----------
    async def asegurar_en_curso(self, sesion_id: int, usuario: Usuario) -> SesionSimulacion:
        """Valida (anti-IDOR) que la sesión es del usuario y está EN_CURSO.

        La usa el WebSocket de audio para rechazar la conexión antes de abrir Transcribe.
        """
        sesion = await self._sesion_del_usuario(sesion_id, usuario)
        if sesion.estado != EstadoSesion.EN_CURSO:
            raise BusinessRuleError("La sesión no está en curso; no admite más análisis.")
        return sesion

    async def registrar_audio(
        self,
        sesion_id: int,
        usuario: Usuario,
        *,
        muletillas: int,
        wpm: int | None,
        pausas: int = 0,
        transcripcion: str,
    ) -> MetricaBiometrica:
        """Persiste un segmento de expresión oral (muletillas + ritmo + pausas) de Transcribe.

        Postura/contacto van vacíos: esta métrica proviene del audio, no del video.
        """
        sesion = await self.asegurar_en_curso(sesion_id, usuario)
        metrica = MetricaBiometrica(
            sesion_id=sesion.id,
            postura_score=None,
            muletillas_conteo=muletillas,
            ritmo_wpm=wpm,
            pausas_largas_conteo=pausas,
            contacto_visual_pct=None,
            transcripcion_texto=transcripcion or "",
            momento=_now(),
        )
        await self.metricas.add(metrica)
        await self.audit.log(
            actor_id=usuario.id,
            accion="BIOMETRIA_AUDIO_ANALIZADO",
            entidad="metrica_biometrica",
            entidad_id=metrica.id,
            metadata={"sesion_id": sesion.id, "muletillas": muletillas},
        )
        return metrica

    # --- CU-14 (lectura): histórico por intervalo ----------------------
    async def listar_metricas(
        self, sesion_id: int, usuario: Usuario
    ) -> Sequence[MetricaBiometrica]:
        await self._sesion_del_usuario(sesion_id, usuario)
        return await self.metricas.por_sesion(sesion_id)

    # --- CU-14 (lectura): resumen acumulado ----------------------------
    async def resumen(self, sesion_id: int, usuario: Usuario) -> dict[str, Any]:
        await self._sesion_del_usuario(sesion_id, usuario)
        datos = await self.metricas.resumen(sesion_id)
        return {"sesion_id": sesion_id, **datos}
