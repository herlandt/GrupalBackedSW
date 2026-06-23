"""Lógica de negocio del submódulo Dashboard (CU-06, RF-08/09)."""

from collections.abc import Sequence
from datetime import datetime
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

    async def obtener(
        self,
        usuario_id: int,
        rol: RolUsuario,
        *,
        modulo: str | None = None,
        desde: datetime | None = None,
        hasta: datetime | None = None,
    ) -> dict[str, Any]:
        """Itera las fuentes y compone {nombre_fuente: payload} (CU-06).

        `modulo` filtra a una sola fuente; `desde`/`hasta` acotan el periodo.
        """
        fuentes = [s for s in self.sources if s.name == modulo] if modulo else self.sources
        metricas: dict[str, Any] = {}
        for source in fuentes:
            metricas[source.name] = await source.collect(
                usuario_id, rol, desde=desde, hasta=hasta
            )

        await self.audit.log(actor_id=usuario_id, accion="DASHBOARD_VISTO", entidad="dashboard")
        return metricas
