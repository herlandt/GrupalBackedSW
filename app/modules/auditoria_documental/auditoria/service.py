"""Lógica de negocio — submódulo auditoria (CU-10, RF-01, RF-02)."""

from collections.abc import Sequence

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit.service import AuditService
from app.core.database import SessionLocal
from app.core.enums import CategoriaObservacion, EstadoAnalisis, NivelPreparacion
from app.core.exceptions import BusinessRuleError, ResourceNotFoundError
from app.integrations.analysis.port import AnalysisServiceError, AnalysisServicePort
from app.modules.administracion.usuarios.models import Usuario
from app.modules.auditoria_documental.auditoria.models import Observacion, ResultadoAuditoria
from app.modules.auditoria_documental.auditoria.repository import (
    ObservacionRepository,
    ResultadoRepository,
)
from app.modules.auditoria_documental.documentos.models import Documento, VersionDocumento
from app.modules.auditoria_documental.documentos.repository import VersionRepository


async def reiniciar_analisis_huerfanos() -> int:
    """Al arrancar, devuelve a PENDIENTE los análisis que quedaron EN_PROCESO.

    Un EN_PROCESO tras un reinicio es un trabajo ABANDONADO (el proceso que lo ejecutaba
    murió: las tareas de fondo no sobreviven al reinicio). Así el usuario puede reintentar
    en vez de quedarse con un "Analizando…" eterno. Devuelve cuántos se reiniciaron.
    """
    async with SessionLocal() as db:
        resultado = await db.execute(
            update(VersionDocumento)
            .where(VersionDocumento.estado_analisis == EstadoAnalisis.EN_PROCESO)
            .values(estado_analisis=EstadoAnalisis.PENDIENTE)
        )
        await db.commit()
        return resultado.rowcount or 0  # type: ignore[attr-defined]  # CursorResult en UPDATE


class AuditoriaService:
    def __init__(self, db: AsyncSession, analysis: AnalysisServicePort) -> None:
        self.db = db
        self.resultados = ResultadoRepository(db)
        self.observaciones = ObservacionRepository(db)
        self.versiones = VersionRepository(db)
        self.audit = AuditService(db)
        self.analysis = analysis

    # --- Helpers ---------------------------------------------------------
    async def _version_del_usuario(self, version_id: int, usuario: Usuario) -> VersionDocumento:
        version = await self.versiones.get(version_id)
        if version is None:
            raise ResourceNotFoundError(f"Versión {version_id} no existe")
        documento = await self.db.get(Documento, version.documento_id)
        if documento is None or documento.usuario_id != usuario.id:
            # No revelar existencia de versiones ajenas: tratar como no encontrada.
            raise ResourceNotFoundError(f"Versión {version_id} no existe")
        return version

    # --- CU-10: lectura --------------------------------------------------
    async def obtener_resultado(
        self, version_id: int, usuario: Usuario, categoria: CategoriaObservacion | None = None
    ) -> tuple[ResultadoAuditoria, Sequence[Observacion]]:
        await self._version_del_usuario(version_id, usuario)
        resultado = await self.resultados.por_version(version_id)
        if resultado is None:
            raise ResourceNotFoundError("Aún no hay resultados de auditoría para esta versión")
        obs = await self.observaciones.por_resultado(resultado.id, categoria)
        return resultado, obs

    async def estado(self, version_id: int, usuario: Usuario) -> EstadoAnalisis:
        version = await self._version_del_usuario(version_id, usuario)
        return version.estado_analisis

    # --- CU-08: el estudiante dispara el análisis de su propia versión ---
    async def analizar(self, version_id: int, usuario: Usuario) -> ResultadoAuditoria:
        """Analiza la versión del propio estudiante. Idempotente: si ya tiene
        resultado lo devuelve; si no, ejecuta el análisis (vía el worker)."""
        await self._version_del_usuario(version_id, usuario)
        existente = await self.resultados.por_version(version_id)
        if existente is not None:
            return existente
        return await self.procesar_version(version_id)

    async def solicitar_analisis(
        self, version_id: int, usuario: Usuario
    ) -> tuple[EstadoAnalisis, bool]:
        """Marca la versión EN_PROCESO para analizarla EN SEGUNDO PLANO (no bloquea).

        Devuelve `(estado, encolar)` donde `encolar` indica si hay que lanzar el trabajo:
        - COMPLETADO -> ya hay resultado, no recalcula (False).
        - EN_PROCESO ya existente -> hay un análisis en curso, no duplicar (False).
        - PENDIENTE/ERROR -> pasa a EN_PROCESO y se debe encolar (True). ERROR permite reintento.
        """
        version = await self._version_del_usuario(version_id, usuario)
        if await self.resultados.por_version(version_id) is not None:
            return EstadoAnalisis.COMPLETADO, False
        if version.estado_analisis == EstadoAnalisis.EN_PROCESO:
            return EstadoAnalisis.EN_PROCESO, False
        version.estado_analisis = EstadoAnalisis.EN_PROCESO
        await self.db.flush()
        return EstadoAnalisis.EN_PROCESO, True

    # --- Worker interno: procesa una versión encolada --------------------
    async def procesar_version(self, version_id: int) -> ResultadoAuditoria:
        """Procesa una versión encolada. Idempotente: si ya hay resultado, no recalcula.

        Hace el ANÁLISIS (lento, 1-2 min) ANTES de escribir nada, para no mantener un lock
        de fila sobre la versión durante todo el proceso (bloquearía las consultas de estado
        y los reintentos). El estado EN_PROCESO lo marca quien encola (la petición).
        """
        version = await self.versiones.get(version_id)
        if version is None:
            raise ResourceNotFoundError(f"Versión {version_id} no existe")
        if await self.resultados.por_version(version_id) is not None:
            raise BusinessRuleError("La versión ya tiene resultados de auditoría")

        try:
            dto = await self.analysis.analizar(
                version_id=version.id,
                archivo_url=version.archivo_url,
                formato=version.formato.value,
            )
        except AnalysisServiceError:
            version.estado_analisis = EstadoAnalisis.ERROR
            await self.db.flush()
            raise

        resultado = ResultadoAuditoria(
            version_id=version.id,
            nivel_documento=NivelPreparacion(dto.nivel_documento),
            resumen=dto.resumen,
            features=dto.features or None,
        )
        await self.resultados.add(resultado)  # flush -> resultado.id disponible

        for o in dto.observaciones:
            self.db.add(
                Observacion(
                    resultado_id=resultado.id,
                    categoria=CategoriaObservacion(o.categoria),
                    severidad=o.severidad,
                    descripcion=o.descripcion,
                    ubicacion=o.ubicacion,
                )
            )
        version.estado_analisis = EstadoAnalisis.COMPLETADO
        await self.db.flush()

        await self.audit.log(
            actor_id=None,
            accion="AUDITORIA_COMPLETADA",
            entidad="resultado_auditoria",
            entidad_id=resultado.id,
            metadata={"version_id": version.id, "nivel": resultado.nivel_documento.value},
        )
        return resultado
