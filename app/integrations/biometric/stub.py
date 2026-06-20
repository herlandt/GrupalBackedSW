"""Adaptador stub del servicio biométrico para desarrollo/test.

Devuelve un `SegmentoMetricasDTO` de ejemplo (postura, contacto visual, muletillas y
ritmo) SIN llamar a AWS Transcribe/Rekognition. El adaptador real (boto3) leerá el clip
desde S3 y traducirá las respuestas de Transcribe/Rekognition a este mismo DTO.
"""

import logging

from app.integrations.biometric.port import BiometricServicePort, SegmentoMetricasDTO

logger = logging.getLogger(__name__)


class StubBiometricService(BiometricServicePort):
    async def analizar_segmento(
        self, *, sesion_id: int, audio_url: str | None, video_url: str | None
    ) -> SegmentoMetricasDTO:
        logger.info(
            "Análisis biométrico (stub): sesion=%s audio=%s video=%s",
            sesion_id,
            audio_url,
            video_url,
        )
        return SegmentoMetricasDTO(
            postura_score=78.5,
            contacto_visual_pct=64.0,
            muletillas_conteo=3,
            ritmo_wpm=132,
            transcripcion="Buenos días, mi tesis aborda... eh... el problema de...",
        )

    async def analizar_imagen(self, *, imagen: bytes) -> SegmentoMetricasDTO:
        logger.info("Análisis de frame (stub): %d bytes", len(imagen))
        return SegmentoMetricasDTO(
            postura_score=80.0, contacto_visual_pct=72.0, muletillas_conteo=0, ritmo_wpm=None
        )
