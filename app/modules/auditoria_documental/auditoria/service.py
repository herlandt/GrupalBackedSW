"""Lógica de negocio — submódulo auditoria (CU-10, RF-01, RF-02)."""

from collections.abc import Sequence
from typing import Any

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
from app.modules.auditoria_documental.etica.service import EticaService

_ORDEN_NIVEL = {NivelPreparacion.BAJO: 0, NivelPreparacion.MEDIO: 1, NivelPreparacion.ALTO: 2}


def _comparar_versiones(
    anterior: VersionDocumento,
    res_anterior: ResultadoAuditoria,
    nivel_actual: NivelPreparacion,
    features_actual: dict[str, float],
) -> dict[str, Any]:
    """Reporte comparativo entre la versión actual y la anterior (CU-09 / RF-09)."""
    ant = _ORDEN_NIVEL[res_anterior.nivel_documento]
    act = _ORDEN_NIVEL[nivel_actual]
    tendencia = "mejoro" if act > ant else "empeoro" if act < ant else "igual"
    prev_feat = res_anterior.features or {}
    deltas = {
        clave: round(float(valor) - float(prev_feat[clave]), 4)
        for clave, valor in (features_actual or {}).items()
        if clave in prev_feat
    }
    return {
        "version_anterior_id": anterior.id,
        "version_anterior_numero": anterior.numero_version,
        "nivel_anterior": res_anterior.nivel_documento.value,
        "nivel_actual": nivel_actual.value,
        "tendencia": tendencia,
        "features_delta": deltas,
    }


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
    def __init__(
        self,
        db: AsyncSession,
        analysis: AnalysisServicePort,
        etica: EticaService | None = None,
    ) -> None:
        self.db = db
        self.resultados = ResultadoRepository(db)
        self.observaciones = ObservacionRepository(db)
        self.versiones = VersionRepository(db)
        self.audit = AuditService(db)
        self.analysis = analysis
        # CU-12: si se inyecta, el motor abre alertas de ética detectadas en el análisis.
        self.etica = etica

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
        # CU-10 (postcondición): registrar la consulta del informe en la bitácora.
        await self.audit.log(
            actor_id=usuario.id,
            accion="AUDITORIA_CONSULTADA",
            entidad="resultado_auditoria",
            entidad_id=resultado.id,
            metadata={
                "version_id": version_id,
                "categoria": categoria.value if categoria else None,
            },
        )
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

        # CU-09 / RF-09: si hay una versión anterior ya analizada, genera la comparación.
        anterior = await self.versiones.version_anterior(
            version.documento_id, version.numero_version
        )
        if anterior is not None:
            res_anterior = await self.resultados.por_version(anterior.id)
            if res_anterior is not None:
                resultado.comparacion = _comparar_versiones(
                    anterior, res_anterior, resultado.nivel_documento, dto.features
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

        # CU-12: el sistema detecta automáticamente posibles incumplimientos éticos durante el
        # análisis y abre las alertas (notificando a estudiante + admins), sin acción manual.
        if self.etica is not None:
            for alerta in dto.alertas_etica:
                await self.etica.crear_alerta_si_nueva(
                    version.id, alerta.tipo, alerta.fragmento
                )
        return resultado
