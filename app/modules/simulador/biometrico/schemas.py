"""Esquemas Pydantic — submódulo biometrico (CU-14, RF-03/04/05).

Contrato de datos de entrada y salida de la API.
"""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class SegmentoIn(BaseModel):
    """Entrada del cliente: referencias a un segmento ya subido (audio/video) y su instante.

    En modo por-segmentos el clip se sube primero a storage/S3 y aquí se envían sus URLs;
    el backend llama al servicio biométrico con ellas.
    """

    audio_url: str | None = Field(default=None, max_length=500)
    video_url: str | None = Field(default=None, max_length=500)
    momento: datetime | None = None  # si no se envía, el service usa "ahora"


class MetricaRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sesion_id: int
    postura_score: Decimal | None
    muletillas_conteo: int
    ritmo_wpm: int | None
    pausas_largas_conteo: int
    contacto_visual_pct: Decimal | None
    transcripcion_texto: str = ""  # texto reconocido (segmentos de audio); vacío en frames de video
    momento: datetime
    created_at: datetime


class ResumenBiometrico(BaseModel):
    """CU-14: métricas acumuladas de la sesión (agregadas sobre todas las métricas)."""

    sesion_id: int
    intervalos: int  # nº de mediciones registradas
    postura_score_promedio: Decimal | None
    contacto_visual_pct_promedio: Decimal | None
    muletillas_total: int
    pausas_total: int
    ritmo_wpm_promedio: int | None
