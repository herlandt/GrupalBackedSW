"""Esquemas Pydantic — submódulo documentos (CU-08, CU-09, CU-11)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import EstadoAnalisis, EstadoEticaTesis, FormatoDocumento, NivelPreparacion


class VersionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    documento_id: int
    numero_version: int
    archivo_url: str
    formato: FormatoDocumento
    estado_analisis: EstadoAnalisis
    # CU-11: resumen/nivel del resultado de auditoría de la versión (None si no hay aún).
    nivel_documento: NivelPreparacion | None = None
    resumen: str | None = None
    created_at: datetime


class DocumentoRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    titulo: str
    estado_etico: EstadoEticaTesis
    created_at: datetime
    updated_at: datetime


class DocumentoConVersiones(DocumentoRead):
    versiones: list[VersionRead] = Field(default_factory=list)
