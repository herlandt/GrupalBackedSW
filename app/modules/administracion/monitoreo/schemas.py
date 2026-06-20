"""Esquemas Pydantic — submódulo monitoreo (CU-07, RF-08)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import EstadoAvance, NivelPreparacion


class EstudianteResumen(BaseModel):
    """Fila de la lista de estudiantes (CU-07)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre: str
    email: str
    activo: bool
    # Placeholder hasta la Fase 5 (dashboard / MetricSource). Lo calcula el service.
    nivel_general: NivelPreparacion = NivelPreparacion.MEDIO


class AvanceFormalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    usuario_id: int
    etapa: str
    estado: EstadoAvance
    aprobado_por_id: int | None = None
    fecha_aprobacion: datetime | None = None
    created_at: datetime


class AvanceFormalCreate(BaseModel):
    etapa: str = Field(min_length=1, max_length=120)


class EstudianteDetalle(BaseModel):
    """Detalle de un estudiante: resumen + avances formales (CU-07)."""

    estudiante: EstudianteResumen
    nivel_general: NivelPreparacion
    avances: list[AvanceFormalRead]
