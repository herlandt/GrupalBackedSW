"""Lógica de negocio — submódulo monitoreo (CU-07, RF-08)."""

from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit.service import AuditService
from app.core.enums import EstadoAvance, NivelPreparacion, RolUsuario
from app.core.exceptions import BusinessRuleError, ResourceNotFoundError
from app.modules.administracion.monitoreo.models import AvanceFormal
from app.modules.administracion.monitoreo.repository import (
    AvanceFormalRepository,
    EstudianteRepository,
)
from app.modules.administracion.monitoreo.schemas import (
    AvanceFormalCreate,
    AvanceFormalRead,
    EstudianteDetalle,
    EstudianteResumen,
    SesionResumen,
    VersionResumen,
)
from app.modules.administracion.reportes.renderers import pdf
from app.modules.administracion.usuarios.models import Usuario
from app.modules.auditoria_documental.auditoria.models import ResultadoAuditoria
from app.modules.auditoria_documental.documentos.models import Documento, VersionDocumento
from app.modules.simulador.simulaciones.models import SesionSimulacion
from app.modules.simulador.tribunal.models import ResultadoSimulacion

_ORDEN = {NivelPreparacion.BAJO: 0, NivelPreparacion.MEDIO: 1, NivelPreparacion.ALTO: 2}
_NIVELES = (NivelPreparacion.BAJO, NivelPreparacion.MEDIO, NivelPreparacion.ALTO)


def _now() -> datetime:
    """Instante actual en UTC, sin zona (las columnas son TIMESTAMP naive)."""
    return datetime.now(UTC).replace(tzinfo=None)


class MonitoreoService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.estudiantes = EstudianteRepository(db)
        self.avances = AvanceFormalRepository(db)
        self.audit = AuditService(db)

    # --- nivel general: documento (Sprint 2) + defensa (Sprint 3) -------------
    async def _nivel_documento(self, usuario_id: int) -> NivelPreparacion | None:
        """Último nivel de auditoría documental del estudiante (RF-01/02)."""
        stmt = (
            select(ResultadoAuditoria.nivel_documento)
            .join(VersionDocumento, VersionDocumento.id == ResultadoAuditoria.version_id)
            .join(Documento, Documento.id == VersionDocumento.documento_id)
            .where(Documento.usuario_id == usuario_id)
            .order_by(ResultadoAuditoria.created_at.desc())
            .limit(1)
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def _nivel_defensa(self, usuario_id: int) -> NivelPreparacion | None:
        """Último nivel de defensa del estudiante (Sprint 3, simulación)."""
        stmt = (
            select(ResultadoSimulacion.nivel_defensa)
            .join(SesionSimulacion, SesionSimulacion.id == ResultadoSimulacion.sesion_id)
            .where(SesionSimulacion.usuario_id == usuario_id)
            .order_by(ResultadoSimulacion.created_at.desc())
            .limit(1)
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def _nivel_general(self, usuario: Usuario) -> NivelPreparacion:
        """Combinación ordinal de documento (Sprint 2) y defensa (Sprint 3).

        Misma regla que ``rubrica.combinar_niveles``: promedio ordinal con EMPATE hacia arriba
        (``(a+b+1)//2``, evita el banker's rounding asimétrico de ``round``).
        Si falta una dimensión, devuelve la otra; si faltan ambas, MEDIO (neutro).
        """
        doc = await self._nivel_documento(usuario.id)
        defe = await self._nivel_defensa(usuario.id)
        presentes = [n for n in (doc, defe) if n is not None]
        if not presentes:
            return NivelPreparacion.MEDIO
        if len(presentes) == 1:
            return presentes[0]
        indice = (_ORDEN[presentes[0]] + _ORDEN[presentes[1]] + 1) // 2
        return _NIVELES[indice]

    async def _sesiones_de(self, usuario_id: int) -> list[SesionResumen]:
        """Historial de simulaciones del estudiante con su nivel de defensa (CU-07)."""
        stmt = (
            select(SesionSimulacion, ResultadoSimulacion.nivel_defensa)
            .outerjoin(ResultadoSimulacion, ResultadoSimulacion.sesion_id == SesionSimulacion.id)
            .where(SesionSimulacion.usuario_id == usuario_id)
            .order_by(SesionSimulacion.fecha_inicio.desc())
        )
        return [
            SesionResumen(
                id=s.id,
                fecha_inicio=s.fecha_inicio,
                nivel_dificultad=s.nivel_dificultad,
                estado=s.estado,
                nivel_defensa=nivel,
            )
            for s, nivel in (await self.db.execute(stmt)).all()
        ]

    async def _versiones_de(self, usuario_id: int) -> list[VersionResumen]:
        """Versiones del documento del estudiante con su retroalimentación de auditoría (CU-07)."""
        stmt = (
            select(
                VersionDocumento,
                ResultadoAuditoria.nivel_documento,
                ResultadoAuditoria.resumen,
            )
            .select_from(VersionDocumento)
            .join(Documento, Documento.id == VersionDocumento.documento_id)
            .outerjoin(ResultadoAuditoria, ResultadoAuditoria.version_id == VersionDocumento.id)
            .where(Documento.usuario_id == usuario_id)
            .order_by(VersionDocumento.created_at.desc())
        )
        return [
            VersionResumen(
                id=v.id,
                numero_version=v.numero_version,
                estado_analisis=v.estado_analisis,
                nivel_documento=nivel,
                resumen=resumen,
                created_at=v.created_at,
            )
            for v, nivel, resumen in (await self.db.execute(stmt)).all()
        ]

    async def _get_estudiante(self, usuario_id: int) -> Usuario:
        usuario = await self.estudiantes.get(usuario_id)
        if usuario is None or usuario.rol is not RolUsuario.ESTUDIANTE:
            raise ResourceNotFoundError(f"Estudiante {usuario_id} no existe")
        return usuario

    # --- CU-07: monitoreo -----------------------------------------------------
    async def listar_estudiantes(self) -> list[EstudianteResumen]:
        estudiantes = await self.estudiantes.list_estudiantes()
        return [
            EstudianteResumen(
                id=e.id,
                nombre=e.nombre,
                email=e.email,
                activo=e.activo,
                nivel_general=await self._nivel_general(e),
            )
            for e in estudiantes
        ]

    async def detalle_estudiante(self, usuario_id: int, admin_id: int) -> EstudianteDetalle:
        estudiante = await self._get_estudiante(usuario_id)
        avances = await self.avances.list_por_usuario(usuario_id)
        # CU-07 (postcondición): registrar la consulta en la bitácora.
        await self.audit.log(
            actor_id=admin_id,
            accion="ESTUDIANTE_CONSULTADO",
            entidad="usuario",
            entidad_id=usuario_id,
        )
        return EstudianteDetalle(
            estudiante=EstudianteResumen.model_validate(estudiante),
            nivel_general=await self._nivel_general(estudiante),
            simulaciones=await self._sesiones_de(usuario_id),
            versiones=await self._versiones_de(usuario_id),
            avances=[AvanceFormalRead.model_validate(a) for a in avances],
        )

    async def exportar_estudiante(self, usuario_id: int, admin_id: int) -> tuple[bytes, str]:
        """CU-07: reporte PDF del estudiante (nivel + simulaciones + versiones + avances)."""
        estudiante = await self._get_estudiante(usuario_id)
        nivel = await self._nivel_general(estudiante)
        sesiones = await self._sesiones_de(usuario_id)
        versiones = await self._versiones_de(usuario_id)
        avances = await self.avances.list_por_usuario(usuario_id)
        secciones: list[tuple[str, list[str], list[list[str]]]] = [
            (
                "Resumen",
                ["Estudiante", "Email", "Nivel general"],
                [[estudiante.nombre, estudiante.email, nivel.value]],
            ),
            (
                "Simulaciones",
                ["Fecha", "Dificultad", "Estado", "Nivel defensa"],
                [
                    [
                        s.fecha_inicio.strftime("%Y-%m-%d %H:%M"),
                        s.nivel_dificultad.value,
                        s.estado.value,
                        s.nivel_defensa.value if s.nivel_defensa else "—",
                    ]
                    for s in sesiones
                ],
            ),
            (
                "Versiones del documento",
                ["#", "Estado análisis", "Nivel doc.", "Retroalimentación"],
                [
                    [
                        str(v.numero_version),
                        v.estado_analisis.value,
                        v.nivel_documento.value if v.nivel_documento else "—",
                        (v.resumen or "—")[:80],
                    ]
                    for v in versiones
                ],
            ),
            (
                "Avances formales",
                ["Etapa", "Estado"],
                [[a.etapa, a.estado.value] for a in avances],
            ),
        ]
        contenido = pdf.reporte_tablas_pdf(
            f"Reporte del estudiante — {estudiante.nombre}", secciones
        )
        await self.audit.log(
            actor_id=admin_id,
            accion="ESTUDIANTE_EXPORTADO",
            entidad="usuario",
            entidad_id=usuario_id,
        )
        return contenido, f"estudiante_{usuario_id}.pdf"

    # --- RF-08: avance formal -------------------------------------------------
    async def listar_avances(self, usuario_id: int) -> Sequence[AvanceFormal]:
        await self._get_estudiante(usuario_id)
        return await self.avances.list_por_usuario(usuario_id)

    async def registrar_avance(
        self, usuario_id: int, data: AvanceFormalCreate, admin_id: int
    ) -> AvanceFormal:
        await self._get_estudiante(usuario_id)
        avance = AvanceFormal(
            usuario_id=usuario_id,
            etapa=data.etapa,
            estado=EstadoAvance.PENDIENTE,
        )
        await self.avances.add(avance)
        await self.audit.log(
            actor_id=admin_id,
            accion="AVANCE_REGISTRADO",
            entidad="avance_formal",
            entidad_id=avance.id,
        )
        return avance

    async def _resolver(
        self, avance_id: int, estado: EstadoAvance, admin_id: int
    ) -> AvanceFormal:
        avance = await self.avances.get_or_404(avance_id)
        if avance.estado is not EstadoAvance.PENDIENTE:
            raise BusinessRuleError("El avance ya fue resuelto")
        avance.estado = estado
        avance.aprobado_por_id = admin_id
        avance.fecha_aprobacion = _now()
        await self.db.flush()
        await self.audit.log(
            actor_id=admin_id,
            accion=f"AVANCE_{estado.value}",
            entidad="avance_formal",
            entidad_id=avance.id,
        )
        return avance

    async def aprobar_avance(self, avance_id: int, admin_id: int) -> AvanceFormal:
        return await self._resolver(avance_id, EstadoAvance.APROBADO, admin_id)

    async def rechazar_avance(self, avance_id: int, admin_id: int) -> AvanceFormal:
        return await self._resolver(avance_id, EstadoAvance.RECHAZADO, admin_id)
