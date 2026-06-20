"""Lógica de negocio del submódulo Dashboard (CU-06, RF-08/09)."""

from collections.abc import Sequence
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit.service import AuditService
from app.core.enums import RolUsuario
from app.modules.administracion.dashboard.sources import MetricSource


class DashboardService:
    def __init__(self, db: AsyncSession, sources: Sequence[MetricSource]) -> None:
        self.db = db
        self.sources = sources
        self.audit = AuditService(db)

    async def obtener(self, usuario_id: int, rol: RolUsuario) -> dict[str, Any]:
        """Itera TODAS las fuentes y compone {nombre_fuente: payload}."""
        metricas: dict[str, Any] = {}
        for source in self.sources:
            metricas[source.name] = await source.collect(usuario_id, rol)

        await self.audit.log(actor_id=usuario_id, accion="DASHBOARD_VISTO", entidad="dashboard")
        return metricas
