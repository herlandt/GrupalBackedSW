"""Fuentes de métricas del dashboard (patrón Strategy / puerto MetricSource).

El DashboardService itera una LISTA de fuentes. Para añadir métricas en Sprints 2-3
(documentos, simulaciones) basta con crear una clase nueva que cumpla MetricSource y
registrarla en la lista de `dependencies.py`, SIN tocar el agregador.
"""

from datetime import datetime
from typing import Any, Protocol

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.core.enums import EstadoAnalisis, EstadoAvance, EstadoSesion, RolUsuario
from app.modules.administracion.dashboard.repository import DashboardRepository
from app.modules.administracion.monitoreo.models import AvanceFormal
from app.modules.administracion.pagos.repository import PagoRepository
from app.modules.administracion.suscripciones.repository import SuscripcionRepository
from app.modules.administracion.usuarios.repository import UsuarioRepository
from app.modules.auditoria_documental.auditoria.models import ResultadoAuditoria
from app.modules.auditoria_documental.documentos.models import Documento, VersionDocumento
from app.modules.simulador.biometrico.models import MetricaBiometrica
from app.modules.simulador.simulaciones.models import SesionSimulacion
from app.modules.simulador.tribunal.models import ResultadoSimulacion


def _entre(
    columna: InstrumentedAttribute[datetime],
    desde: datetime | None,
    hasta: datetime | None,
) -> list[ColumnElement[bool]]:
    """Condiciones de rango de fechas (CU-06, filtro por periodo); vacío = sin filtro."""
    condiciones: list[ColumnElement[bool]] = []
    if desde is not None:
        condiciones.append(columna >= desde)
    if hasta is not None:
        condiciones.append(columna <= hasta)
    return condiciones


class MetricSource(Protocol):
    """Contrato de una fuente de métricas del dashboard."""

    name: str

    async def collect(
        self,
        usuario_id: int,
        rol: RolUsuario,
        *,
        desde: datetime | None = None,
        hasta: datetime | None = None,
    ) -> dict[str, Any]: ...


class CuentaMetricSource:
    """Datos básicos de la cuenta (RF-09). Admin -> totales globales."""

    name = "cuenta"

    def __init__(self, db: AsyncSession) -> None:
        self.usuarios = UsuarioRepository(db)
        self.agg = DashboardRepository(db)

    async def collect(
        self,
        usuario_id: int,
        rol: RolUsuario,
        *,
        desde: datetime | None = None,
        hasta: datetime | None = None,
    ) -> dict[str, Any]:
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

    async def collect(
        self,
        usuario_id: int,
        rol: RolUsuario,
        *,
        desde: datetime | None = None,
        hasta: datetime | None = None,
    ) -> dict[str, Any]:
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

    async def collect(
        self,
        usuario_id: int,
        rol: RolUsuario,
        *,
        desde: datetime | None = None,
        hasta: datetime | None = None,
    ) -> dict[str, Any]:
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

    async def collect(
        self,
        usuario_id: int,
        rol: RolUsuario,
        *,
        desde: datetime | None = None,
        hasta: datetime | None = None,
    ) -> dict[str, Any]:
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


class DocumentoMetricSource:
    """CU-06 — Documentos y resultados de auditoría del estudiante (CU-08/10/11)."""

    name = "documentos"

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def collect(
        self,
        usuario_id: int,
        rol: RolUsuario,
        *,
        desde: datetime | None = None,
        hasta: datetime | None = None,
    ) -> dict[str, Any]:
        if rol == RolUsuario.ADMINISTRADOR:
            total = await self.db.scalar(
                select(func.count())
                .select_from(Documento)
                .where(*_entre(Documento.created_at, desde, hasta))
            )
            analizadas = await self.db.scalar(
                select(func.count())
                .select_from(VersionDocumento)
                .where(VersionDocumento.estado_analisis == EstadoAnalisis.COMPLETADO)
                .where(*_entre(VersionDocumento.created_at, desde, hasta))
            )
            return {
                "total_documentos": int(total or 0),
                "versiones_analizadas": int(analizadas or 0),
            }
        total_docs = await self.db.scalar(
            select(func.count())
            .select_from(Documento)
            .where(Documento.usuario_id == usuario_id)
            .where(*_entre(Documento.created_at, desde, hasta))
        )
        total_versiones = await self.db.scalar(
            select(func.count())
            .select_from(VersionDocumento)
            .join(Documento, Documento.id == VersionDocumento.documento_id)
            .where(Documento.usuario_id == usuario_id)
            .where(*_entre(VersionDocumento.created_at, desde, hasta))
        )
        ultimo = (
            await self.db.execute(
                select(ResultadoAuditoria.nivel_documento)
                .join(VersionDocumento, VersionDocumento.id == ResultadoAuditoria.version_id)
                .join(Documento, Documento.id == VersionDocumento.documento_id)
                .where(Documento.usuario_id == usuario_id)
                .order_by(ResultadoAuditoria.created_at.desc())
                .limit(1)
            )
        ).scalars().first()
        return {
            "total_documentos": int(total_docs or 0),
            "total_versiones": int(total_versiones or 0),
            "ultimo_nivel": ultimo.value if ultimo is not None else None,
        }


class SimulacionMetricSource:
    """CU-06 — Sesiones de simulación y evolución del nivel de defensa (CU-13/14/15)."""

    name = "simulaciones"

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def collect(
        self,
        usuario_id: int,
        rol: RolUsuario,
        *,
        desde: datetime | None = None,
        hasta: datetime | None = None,
    ) -> dict[str, Any]:
        rango = _entre(SesionSimulacion.fecha_inicio, desde, hasta)
        if rol == RolUsuario.ADMINISTRADOR:
            total = await self.db.scalar(
                select(func.count()).select_from(SesionSimulacion).where(*rango)
            )
            finalizadas = await self.db.scalar(
                select(func.count())
                .select_from(SesionSimulacion)
                .where(SesionSimulacion.estado == EstadoSesion.FINALIZADA)
                .where(*rango)
            )
            return {"total_sesiones": int(total or 0), "finalizadas": int(finalizadas or 0)}
        por_estado = {
            estado.value: n
            for estado, n in (
                await self.db.execute(
                    select(SesionSimulacion.estado, func.count())
                    .where(SesionSimulacion.usuario_id == usuario_id)
                    .where(*rango)
                    .group_by(SesionSimulacion.estado)
                )
            ).all()
        }
        niveles = [
            nivel.value
            for nivel in (
                await self.db.execute(
                    select(ResultadoSimulacion.nivel_defensa)
                    .join(SesionSimulacion, SesionSimulacion.id == ResultadoSimulacion.sesion_id)
                    .where(SesionSimulacion.usuario_id == usuario_id)
                    .where(*rango)
                    .order_by(SesionSimulacion.fecha_inicio)
                )
            ).scalars().all()
        ]
        return {
            "total_sesiones": sum(por_estado.values()),
            "por_estado": por_estado,
            "ultimo_nivel_defensa": niveles[-1] if niveles else None,
            "evolucion_defensa": niveles,
        }


class BiometricoMetricSource:
    """CU-06 — Métricas biométricas acumuladas y mayor fallo del estudiante (RF-04/05)."""

    name = "biometrico"

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def collect(
        self,
        usuario_id: int,
        rol: RolUsuario,
        *,
        desde: datetime | None = None,
        hasta: datetime | None = None,
    ) -> dict[str, Any]:
        stmt = (
            select(
                func.coalesce(func.sum(MetricaBiometrica.muletillas_conteo), 0),
                func.coalesce(func.sum(MetricaBiometrica.pausas_largas_conteo), 0),
                func.avg(MetricaBiometrica.ritmo_wpm),
                func.avg(MetricaBiometrica.contacto_visual_pct),
                func.avg(MetricaBiometrica.postura_score),
            )
            .select_from(MetricaBiometrica)
            .join(SesionSimulacion, SesionSimulacion.id == MetricaBiometrica.sesion_id)
            .where(*_entre(MetricaBiometrica.momento, desde, hasta))
        )
        if rol != RolUsuario.ADMINISTRADOR:
            stmt = stmt.where(SesionSimulacion.usuario_id == usuario_id)
        muletillas, pausas, ritmo, contacto, postura = (await self.db.execute(stmt)).one()
        muletillas, pausas = int(muletillas), int(pausas)
        # "Mayor fallo" entre silencios largos y muletillas (CU-06, panel del estudiante).
        if muletillas == 0 and pausas == 0:
            mayor_fallo = None
        elif pausas > muletillas:
            mayor_fallo = "silencios_largos"
        else:
            mayor_fallo = "muletillas"
        return {
            "muletillas_total": muletillas,
            "silencios_largos_total": pausas,
            "ritmo_wpm_promedio": int(ritmo) if ritmo is not None else None,
            "contacto_visual_promedio": round(float(contacto), 2) if contacto is not None else None,
            "postura_promedio": round(float(postura), 2) if postura is not None else None,
            "mayor_fallo": mayor_fallo,
        }
