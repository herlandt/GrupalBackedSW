"""Esquemas Pydantic — notificaciones in-app (CU-02)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class NotificacionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    titulo: str
    cuerpo: str
    leida: bool
    created_at: datetime
