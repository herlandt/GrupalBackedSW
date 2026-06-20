"""Puerto del servicio biométrico (AWS Transcribe + Rekognition) + DTO neutral.

`BiometricServicePort` recibe un segmento de audio/video de la defensa y devuelve
métricas de lenguaje corporal (RF-04) y expresión oral (RF-05) como un DTO neutral,
sin dependencias del ORM. El adaptador real (boto3) se conectará por entorno; aquí solo
definimos el contrato y, en stub.py, el adaptador de desarrollo.
"""

from dataclasses import dataclass
from typing import Protocol


class BiometricServiceError(Exception):
    """El servicio biométrico (Transcribe/Rekognition) falló o devolvió algo inválido."""


@dataclass
class SegmentoMetricasDTO:
    # RF-04 (Rekognition): lenguaje corporal
    postura_score: float | None  # 0.0–100.0
    contacto_visual_pct: float | None  # 0.0–100.0
    # RF-05 (Transcribe + postproceso): expresión oral
    muletillas_conteo: int  # nº de muletillas en el segmento
    ritmo_wpm: int | None  # palabras por minuto
    transcripcion: str | None = None  # texto reconocido (RF-05; no se persiste hoy)


class BiometricServicePort(Protocol):
    async def analizar_segmento(
        self, *, sesion_id: int, audio_url: str | None, video_url: str | None
    ) -> SegmentoMetricasDTO:
        """Analiza un segmento (audio/video) y devuelve sus métricas neutrales."""
        ...

    async def analizar_imagen(self, *, imagen: bytes) -> SegmentoMetricasDTO:
        """Analiza un frame (imagen) de la cámara: postura y contacto visual (RF-04)."""
        ...
