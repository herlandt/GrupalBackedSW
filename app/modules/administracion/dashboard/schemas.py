"""Esquemas Pydantic del submódulo Dashboard (CU-06, RF-08/09)."""

from typing import Any

from pydantic import BaseModel


class DashboardResponse(BaseModel):
    """Respuesta compuesta del dashboard.

    `metricas` es un diccionario nombre-de-fuente -> payload de esa fuente, para que
    añadir fuentes (Sprints 2-3) no rompa el contrato existente.
    """

    rol: str
    metricas: dict[str, Any]
