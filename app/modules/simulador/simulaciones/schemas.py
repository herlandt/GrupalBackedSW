"""Esquemas Pydantic — submódulo simulaciones (CU-13, CU-15).

Contrato de datos de entrada y salida de la API.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.core.enums import EstadoSesion, NivelDificultad


class SesionCreate(BaseModel):
    """Cuerpo de POST: iniciar una simulación (CU-13)."""

    version_documento_id: int
    nivel_dificultad: NivelDificultad


class SesionRead(BaseModel):
    """Respuesta de lectura de una sesión (detalle e historial, CU-15)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    usuario_id: int
    version_documento_id: int
    nivel_dificultad: NivelDificultad
    estado: EstadoSesion
    fecha_inicio: datetime
    fecha_fin: datetime | None
    created_at: datetime
