"""Esquemas Pydantic — submódulo documentos (CU-08, CU-09, CU-11)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import EstadoAnalisis, FormatoDocumento


class VersionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    documento_id: int
    numero_version: int
    archivo_url: str
    formato: FormatoDocumento
    estado_analisis: EstadoAnalisis
    created_at: datetime


class DocumentoRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    titulo: str
    created_at: datetime
    updated_at: datetime


class DocumentoConVersiones(DocumentoRead):
    versiones: list[VersionRead] = Field(default_factory=list)
