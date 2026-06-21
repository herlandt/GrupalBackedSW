"""Esquemas Pydantic — submódulo integracion (CU-14, dimensión defensa)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.core.enums import NivelPreparacion


class ResultadoSimulacionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sesion_id: int
    nivel_defensa: NivelPreparacion
    oratoria_score: float | None
    comunicacion_no_verbal_score: float | None
    dominio_score: float | None
    coherencia_documento_score: float | None  # 0..100: discurso vs documento
    confianza: float | None  # confianza calibrada de la IA (0..1)
    resumen: str | None
    created_at: datetime
