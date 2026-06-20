"""Esquemas Pydantic — submódulo etica (CU-12)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.core.enums import EstadoAlertaEtica


class AlertaCrear(BaseModel):
    """Entrada del motor de análisis para abrir una alerta."""

    version_id: int
    tipo: str
    fragmento: str | None = None


class AlertaResolver(BaseModel):
    """El admin decide el nuevo estado de la alerta."""

    estado: EstadoAlertaEtica


class AlertaRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    version_id: int
    tipo: str
    fragmento: str | None
    estado: EstadoAlertaEtica
    decision_admin_id: int | None
    created_at: datetime
