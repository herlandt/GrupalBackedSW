"""Dependencias del submódulo Dashboard: arma la lista de fuentes de métricas."""

from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.administracion.dashboard.sources import (
    AvanceMetricSource,
    BiometricoMetricSource,
    CuentaMetricSource,
    DocumentoMetricSource,
    MetricSource,
    PagosMetricSource,
    SimulacionMetricSource,
    SuscripcionMetricSource,
)


def build_metric_sources(db: AsyncSession) -> Sequence[MetricSource]:
    """Todas las fuentes del dashboard (CU-06). El estudiante ve su progreso real
    (documentos, simulaciones, biométrico, avance); el admin, los agregados globales.
    Añadir una métrica = una línea más aquí, SIN tocar el DashboardService."""
    return [
        CuentaMetricSource(db),
        SuscripcionMetricSource(db),
        PagosMetricSource(db),
        DocumentoMetricSource(db),
        SimulacionMetricSource(db),
        BiometricoMetricSource(db),
        AvanceMetricSource(db),  # RF-08: avance formal del estudiante / progreso global admin
    ]
