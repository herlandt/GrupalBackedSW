"""Esquemas Pydantic — submódulo auditoria (CU-10, RF-01, RF-02)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.core.enums import CategoriaObservacion, EstadoAnalisis, NivelPreparacion


class ObservacionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    categoria: CategoriaObservacion
    severidad: str
    descripcion: str
    ubicacion: str | None


class ResultadoRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    version_id: int
    nivel_documento: NivelPreparacion
    resumen: str | None
    created_at: datetime
    observaciones: list[ObservacionRead]


class EstadoAnalisisRead(BaseModel):
    """Para consultar el estado del análisis de una versión sin el informe completo."""

    version_id: int
    estado_analisis: EstadoAnalisis
    tiene_resultado: bool
