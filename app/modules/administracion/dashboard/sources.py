"""Fuentes de métricas del dashboard (patrón Strategy / puerto MetricSource).

El DashboardService itera una LISTA de fuentes. Para añadir métricas en Sprints 2-3
(documentos, simulaciones) basta con crear una clase nueva que cumpla MetricSource y
registrarla en la lista de `dependencies.py`, SIN tocar el agregador.
"""

from typing import Any, Protocol

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import EstadoAvance, RolUsuario
from app.modules.administracion.dashboard.repository import DashboardRepository
from app.modules.administracion.monitoreo.models import AvanceFormal
from app.modules.administracion.pagos.repository import PagoRepository
from app.modules.administracion.suscripciones.repository import SuscripcionRepository
from app.modules.administracion.usuarios.repository import UsuarioRepository


class MetricSource(Protocol):
    """Contrato de una fuente de métricas del dashboard."""

    name: str

    async def collect(self, usuario_id: int, rol: RolUsuario) -> dict[str, Any]: ...


class CuentaMetricSource:
    """Datos básicos de la cuenta (RF-09). Admin -> totales globales."""

    name = "cuenta"

    def __init__(self, db: AsyncSession) -> None:
        self.usuarios = UsuarioRepository(db)
        self.agg = DashboardRepository(db)

    async def collect(self, usuario_id: int, rol: RolUsuario) -> dict[str, Any]:
        if rol == RolUsuario.ADMINISTRADOR:
            return {
                "total_usuarios": await self.agg.total_usuarios(),
                "usuarios_activos": await self.agg.total_estudiantes_activos(),
            }
        usuario = await self.usuarios.get(usuario_id)
        return {
            "nombre": usuario.nombre if usuario else None,
            "email": usuario.email if usuario else None,
            "miembro_desde": (
                usuario.created_at.isoformat() if usuario and usuario.created_at else None
            ),
        }


class SuscripcionMetricSource:
    """Estado de la suscripción (RF-09). Admin -> suscripciones activas globales."""

    name = "suscripcion"

    def __init__(self, db: AsyncSession) -> None:
        self.suscripciones = SuscripcionRepository(db)
        self.agg = DashboardRepository(db)

    async def collect(self, usuario_id: int, rol: RolUsuario) -> dict[str, Any]:
        if rol == RolUsuario.ADMINISTRADOR:
            return {"suscripciones_activas": await self.agg.total_suscripciones_activas()}
        suscripcion = await self.suscripciones.activa_de_usuario(usuario_id)
        return {
            "estado": suscripcion.estado.value if suscripcion else "SIN_SUSCRIPCION",
            "plan_id": suscripcion.plan_id if suscripcion else None,
            "fecha_fin": (
                suscripcion.fecha_fin.isoformat()
                if suscripcion and suscripcion.fecha_fin
                else None
            ),
        }


class PagosMetricSource:
    """Resumen de pagos (RF-09). Admin -> ingresos totales."""

    name = "pagos"

    def __init__(self, db: AsyncSession) -> None:
        self.pagos = PagoRepository(db)
        self.agg = DashboardRepository(db)

    async def collect(self, usuario_id: int, rol: RolUsuario) -> dict[str, Any]:
        if rol == RolUsuario.ADMINISTRADOR:
            return {"ingresos_totales": str(await self.agg.ingresos_totales())}
        pagos = await self.pagos.por_usuario(usuario_id)
        return {
            "total_pagos": len(pagos),
            "ultimo_pago": (
                {
                    "monto": str(pagos[0].monto),
                    "moneda": pagos[0].moneda,
                    "estado": pagos[0].estado.value,
                    "fecha": pagos[0].created_at.isoformat(),
                }
                if pagos
                else None
            ),
        }


class AvanceMetricSource:
    """RF-08 — Avance formal del estudiante. Método ESQUELETO extensible.

    En Sprint 1 cuenta etapas por estado. Sprints 2-3 enriquecerán el payload
    (líneas de tiempo, porcentajes) SIN cambiar la firma de collect().
    """

    name = "avance"

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def collect(self, usuario_id: int, rol: RolUsuario) -> dict[str, Any]:
        if rol == RolUsuario.ADMINISTRADOR:
            # Esqueleto: totales globales por estado (Sprint 2-3 lo detallará).
            result = await self.db.execute(
                select(AvanceFormal.estado, func.count()).group_by(AvanceFormal.estado)
            )
            return {"por_estado": {estado.value: n for estado, n in result.all()}}

        result = await self.db.execute(
            select(AvanceFormal.estado, func.count())
            .where(AvanceFormal.usuario_id == usuario_id)
            .group_by(AvanceFormal.estado)
        )
        conteo = {estado.value: n for estado, n in result.all()}
        return {
            "aprobadas": conteo.get(EstadoAvance.APROBADO.value, 0),
            "pendientes": conteo.get(EstadoAvance.PENDIENTE.value, 0),
            "rechazadas": conteo.get(EstadoAvance.RECHAZADO.value, 0),
        }
