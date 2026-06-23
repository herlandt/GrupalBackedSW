"""Acceso a datos del submódulo Reportes (CU-05). Solo lectura/agregaciones.

Devuelve dataclasses 'planas' (capa DATOS) que luego renderizan los renderers.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select

from app.core.audit.models import Bitacora
from app.core.enums import EstadoPago, NivelPreparacion, RolUsuario
from app.core.repository import BaseRepository
from app.modules.administracion.pagos.models import Pago
from app.modules.administracion.usuarios.models import Usuario
from app.modules.auditoria_documental.auditoria.models import ResultadoAuditoria
from app.modules.auditoria_documental.documentos.models import Documento, VersionDocumento
from app.modules.simulador.simulaciones.models import SesionSimulacion
from app.modules.simulador.tribunal.models import ResultadoSimulacion

_ORDEN = {NivelPreparacion.BAJO: 0, NivelPreparacion.MEDIO: 1, NivelPreparacion.ALTO: 2}
_NIVELES = (NivelPreparacion.BAJO, NivelPreparacion.MEDIO, NivelPreparacion.ALTO)


def _combinar_nivel(
    doc: NivelPreparacion | None, defe: NivelPreparacion | None
) -> NivelPreparacion | None:
    """Nivel general = promedio ordinal documento+defensa (empate hacia arriba); None si no hay."""
    presentes = [n for n in (doc, defe) if n is not None]
    if not presentes:
        return None
    if len(presentes) == 1:
        return presentes[0]
    return _NIVELES[(_ORDEN[presentes[0]] + _ORDEN[presentes[1]] + 1) // 2]


@dataclass(frozen=True)
class GananciasData:
    total: Decimal
    moneda: str
    cantidad_pagos: int


@dataclass(frozen=True)
class PagoPorEstudianteData:
    usuario_id: int
    nombre: str
    email: str
    total_pagado: Decimal
    cantidad_pagos: int


@dataclass(frozen=True)
class PagoFilaData:
    """Una fila del historial de un usuario (para el export del estudiante, CU-04)."""

    fecha: datetime
    monto: Decimal
    moneda: str
    estado: str


@dataclass(frozen=True)
class ProgresoEstudianteData:
    """Fila del reporte de progreso de estudiantes (CU-05)."""

    nombre: str
    email: str
    total_documentos: int
    total_simulaciones: int
    nivel_documento: str | None
    nivel_defensa: str | None
    nivel_general: str


@dataclass(frozen=True)
class BitacoraFilaData:
    """Una fila de la bitácora/auditoría (para el reporte del admin)."""

    fecha: datetime
    actor: str  # nombre/email del actor, o "sistema" si fue un evento sin usuario
    accion: str
    entidad: str
    entidad_id: int | None
    detalle: str  # metadata serializada de forma compacta (clave=valor)


def _fmt_detalle(meta: dict[str, Any] | None) -> str:
    """Aplana la metadata JSONB a una cadena 'clave=valor, …' legible en el reporte."""
    if not meta:
        return ""
    return ", ".join(f"{clave}={valor}" for clave, valor in meta.items())


class ReporteRepository(BaseRepository[Pago]):
    model = Pago

    async def ganancias_totales(self) -> GananciasData:
        """Suma de montos de pagos PAGADO. La moneda se toma del primer pago pagado."""
        stmt = (
            select(
                func.coalesce(func.sum(Pago.monto), 0),
                func.count(Pago.id),
                func.min(Pago.moneda),
            )
            .where(Pago.estado == EstadoPago.PAGADO)
        )
        total, cantidad, moneda = (await self.db.execute(stmt)).one()
        return GananciasData(
            total=Decimal(total),
            cantidad_pagos=int(cantidad),
            moneda=str(moneda) if moneda else "USD",
        )

    async def pagos_por_estudiante(self) -> Sequence[PagoPorEstudianteData]:
        """Total pagado y cantidad de pagos por usuario (solo pagos PAGADO)."""
        stmt = (
            select(
                Usuario.id,
                Usuario.nombre,
                Usuario.email,
                func.coalesce(func.sum(Pago.monto), 0),
                func.count(Pago.id),
            )
            .join(Pago, Pago.usuario_id == Usuario.id)
            .where(Pago.estado == EstadoPago.PAGADO)
            .group_by(Usuario.id, Usuario.nombre, Usuario.email)
            .order_by(func.sum(Pago.monto).desc())
        )
        filas = (await self.db.execute(stmt)).all()
        return [
            PagoPorEstudianteData(
                usuario_id=int(uid),
                nombre=str(nombre),
                email=str(email),
                total_pagado=Decimal(total),
                cantidad_pagos=int(cantidad),
            )
            for uid, nombre, email, total, cantidad in filas
        ]

    async def bitacora(
        self,
        *,
        desde: datetime | None = None,
        hasta: datetime | None = None,
        limite: int = 2000,
    ) -> Sequence[BitacoraFilaData]:
        """Eventos de la bitácora (más reciente primero) con el actor resuelto.

        `outerjoin` con Usuario para que los eventos de sistema (actor_id NULL) también
        salgan. `limite` acota el tamaño del reporte; `desde`/`hasta` filtran por fecha.
        """
        stmt = (
            select(
                Bitacora.created_at,
                Usuario.nombre,
                Usuario.email,
                Bitacora.accion,
                Bitacora.entidad,
                Bitacora.entidad_id,
                Bitacora.metadata_,
            )
            .select_from(Bitacora)
            .outerjoin(Usuario, Usuario.id == Bitacora.actor_id)
        )
        if desde is not None:
            stmt = stmt.where(Bitacora.created_at >= desde)
        if hasta is not None:
            stmt = stmt.where(Bitacora.created_at <= hasta)
        stmt = stmt.order_by(Bitacora.created_at.desc()).limit(limite)
        filas = (await self.db.execute(stmt)).all()
        return [
            BitacoraFilaData(
                fecha=fecha,
                actor=nombre or email or "sistema",
                accion=str(accion),
                entidad=str(entidad),
                entidad_id=int(eid) if eid is not None else None,
                detalle=_fmt_detalle(meta),
            )
            for fecha, nombre, email, accion, entidad, eid, meta in filas
        ]

    async def progreso_estudiantes(self) -> Sequence[ProgresoEstudianteData]:
        """Progreso por estudiante: # documentos, # simulaciones y nivel (doc/defensa/general)."""
        estudiantes = (
            await self.db.execute(
                select(Usuario.id, Usuario.nombre, Usuario.email)
                .where(Usuario.rol == RolUsuario.ESTUDIANTE)
                .order_by(Usuario.nombre)
            )
        ).all()
        docs = {
            uid: int(n)
            for uid, n in (
                await self.db.execute(
                    select(Documento.usuario_id, func.count()).group_by(Documento.usuario_id)
                )
            ).all()
        }
        sims = {
            uid: int(n)
            for uid, n in (
                await self.db.execute(
                    select(SesionSimulacion.usuario_id, func.count()).group_by(
                        SesionSimulacion.usuario_id
                    )
                )
            ).all()
        }
        # Último nivel por estudiante con DISTINCT ON (Postgres): el más reciente por usuario.
        niv_doc = {
            uid: nivel
            for uid, nivel in (
                await self.db.execute(
                    select(Documento.usuario_id, ResultadoAuditoria.nivel_documento)
                    .select_from(ResultadoAuditoria)
                    .join(VersionDocumento, VersionDocumento.id == ResultadoAuditoria.version_id)
                    .join(Documento, Documento.id == VersionDocumento.documento_id)
                    .order_by(Documento.usuario_id, ResultadoAuditoria.created_at.desc())
                    .distinct(Documento.usuario_id)
                )
            ).all()
        }
        niv_def = {
            uid: nivel
            for uid, nivel in (
                await self.db.execute(
                    select(SesionSimulacion.usuario_id, ResultadoSimulacion.nivel_defensa)
                    .select_from(ResultadoSimulacion)
                    .join(SesionSimulacion, SesionSimulacion.id == ResultadoSimulacion.sesion_id)
                    .order_by(SesionSimulacion.usuario_id, ResultadoSimulacion.created_at.desc())
                    .distinct(SesionSimulacion.usuario_id)
                )
            ).all()
        }
        filas: list[ProgresoEstudianteData] = []
        for uid, nombre, email in estudiantes:
            doc = niv_doc.get(uid)
            defe = niv_def.get(uid)
            general = _combinar_nivel(doc, defe)
            filas.append(
                ProgresoEstudianteData(
                    nombre=str(nombre),
                    email=str(email),
                    total_documentos=docs.get(uid, 0),
                    total_simulaciones=sims.get(uid, 0),
                    nivel_documento=doc.value if doc is not None else None,
                    nivel_defensa=defe.value if defe is not None else None,
                    nivel_general=general.value if general is not None else "SIN_DATOS",
                )
            )
        return filas

    async def historial_de_usuario(self, usuario_id: int) -> Sequence[PagoFilaData]:
        """Todas las filas de pago de un usuario (para el export del propio estudiante)."""
        stmt = (
            select(Pago.created_at, Pago.monto, Pago.moneda, Pago.estado)
            .where(Pago.usuario_id == usuario_id)
            .order_by(Pago.created_at.desc())
        )
        filas = (await self.db.execute(stmt)).all()
        return [
            PagoFilaData(fecha=fecha, monto=Decimal(monto), moneda=str(moneda), estado=str(estado))
            for fecha, monto, moneda, estado in filas
        ]
