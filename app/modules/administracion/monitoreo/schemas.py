"""Esquemas Pydantic — submódulo monitoreo (CU-07, RF-08)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import (
    EstadoAnalisis,
    EstadoAvance,
    EstadoSesion,
    NivelDificultad,
    NivelPreparacion,
)


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


class SesionResumen(BaseModel):
    """Fila del historial de simulaciones del estudiante (CU-07)."""

    id: int
    fecha_inicio: datetime
    nivel_dificultad: NivelDificultad
    estado: EstadoSesion
    nivel_defensa: NivelPreparacion | None = None


class VersionResumen(BaseModel):
    """Fila del historial de versiones del documento, con su retroalimentación (CU-07)."""

    id: int
    numero_version: int
    estado_analisis: EstadoAnalisis
    nivel_documento: NivelPreparacion | None = None
    resumen: str | None = None
    created_at: datetime


class EstudianteDetalle(BaseModel):
    """Detalle del estudiante (CU-07): resumen, nivel, historial de simulaciones,
    versiones del documento (con retroalimentación) y avances formales."""

    estudiante: EstudianteResumen
    nivel_general: NivelPreparacion
    simulaciones: list[SesionResumen] = Field(default_factory=list)
    versiones: list[VersionResumen] = Field(default_factory=list)
    avances: list[AvanceFormalRead]
