"""Dependencias del submódulo Dashboard: arma la lista de fuentes de métricas."""

from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.administracion.dashboard.sources import (
    CuentaMetricSource,
    MetricSource,
    PagosMetricSource,
    SuscripcionMetricSource,
)


def build_metric_sources(db: AsyncSession) -> Sequence[MetricSource]:
    """Fuentes activas en Sprint 1. Sprints 2-3 añaden líneas aquí (documentos,
    simulaciones) SIN tocar el DashboardService."""
    return [
        CuentaMetricSource(db),
        SuscripcionMetricSource(db),
        PagosMetricSource(db),
        # Sprint 1.5+: descomenta para activar RF-08 detallado.
        # AvanceMetricSource(db),
    ]
