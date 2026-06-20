"""Lógica de negocio — submódulo simulaciones (CU-13, CU-15).

Reglas del dominio; orquesta repositorios. No conoce HTTP.
"""

from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit.service import AuditService
from app.core.enums import EstadoSesion, NivelDificultad
from app.core.exceptions import BusinessRuleError, ResourceNotFoundError
from app.modules.administracion.usuarios.models import Usuario
from app.modules.auditoria_documental.documentos.models import Documento
from app.modules.auditoria_documental.documentos.repository import VersionRepository
from app.modules.simulador.simulaciones.models import SesionSimulacion
from app.modules.simulador.simulaciones.repository import SesionSimulacionRepository


def _now() -> datetime:
    """Instante actual en UTC, sin zona (las columnas son TIMESTAMP naive)."""
    return datetime.now(UTC).replace(tzinfo=None)


class SimulacionService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.sesiones = SesionSimulacionRepository(db)
        self.versiones = VersionRepository(db)
        self.audit = AuditService(db)

    # --- Helpers ---------------------------------------------------------
    async def _sesion_del_usuario(self, sesion_id: int, usuario: Usuario) -> SesionSimulacion:
        """Carga una sesión PROPIA o lanza 404 (no revela sesiones ajenas)."""
        sesion = await self.sesiones.get_de_usuario(sesion_id, usuario.id)
        if sesion is None:
            raise ResourceNotFoundError(f"Sesión {sesion_id} no existe")
        return sesion

    async def _validar_version_propia(self, version_id: int, usuario: Usuario) -> None:
        """La sesión solo se ancla a una versión EXISTENTE y del propio estudiante.

        Cubre la precondición CU-13 ('al menos un documento subido') y evita
        anclar a documentos ajenos (IDOR sobre la versión).
        """
        version = await self.versiones.get(version_id)
        if version is None:
            raise ResourceNotFoundError(f"Versión {version_id} no existe")
        documento = await self.db.get(Documento, version.documento_id)
        if documento is None or documento.usuario_id != usuario.id:
            # No revelar versiones ajenas: tratar como no encontrada.
            raise ResourceNotFoundError(f"Versión {version_id} no existe")

    # --- CU-13: iniciar sesión ------------------------------------------
    async def iniciar(
        self, usuario: Usuario, version_documento_id: int, nivel: NivelDificultad
    ) -> SesionSimulacion:
        if await self.sesiones.tiene_en_curso(usuario.id):
            raise BusinessRuleError("Ya tienes una simulación en curso; ciérrala primero.")
        await self._validar_version_propia(version_documento_id, usuario)
        sesion = SesionSimulacion(
            usuario_id=usuario.id,
            version_documento_id=version_documento_id,
            nivel_dificultad=nivel,
            estado=EstadoSesion.EN_CURSO,
            fecha_inicio=_now(),
            fecha_fin=None,
        )
        await self.sesiones.add(sesion)  # flush -> sesion.id disponible
        await self.audit.log(
            actor_id=usuario.id,
            accion="SIMULACION_INICIADA",
            entidad="sesion_simulacion",
            entidad_id=sesion.id,
            metadata={"version_id": version_documento_id, "nivel": nivel.value},
        )
        return sesion

    # --- CU-13: cerrar el ciclo de vida ---------------------------------
    async def finalizar(self, sesion_id: int, usuario: Usuario) -> SesionSimulacion:
        sesion = await self._sesion_del_usuario(sesion_id, usuario)
        if sesion.estado is not EstadoSesion.EN_CURSO:
            raise BusinessRuleError("La sesión no está en curso")
        sesion.estado = EstadoSesion.FINALIZADA
        sesion.fecha_fin = _now()
        await self.db.flush()
        await self.audit.log(
            actor_id=usuario.id,
            accion="SIMULACION_FINALIZADA",
            entidad="sesion_simulacion",
            entidad_id=sesion.id,
        )
        return sesion

    async def cancelar(self, sesion_id: int, usuario: Usuario) -> SesionSimulacion:
        sesion = await self._sesion_del_usuario(sesion_id, usuario)
        if sesion.estado is not EstadoSesion.EN_CURSO:
            raise BusinessRuleError("La sesión no está en curso")
        sesion.estado = EstadoSesion.CANCELADA
        sesion.fecha_fin = _now()
        await self.db.flush()
        await self.audit.log(
            actor_id=usuario.id,
            accion="SIMULACION_CANCELADA",
            entidad="sesion_simulacion",
            entidad_id=sesion.id,
        )
        return sesion

    # --- CU-15: historial y detalle -------------------------------------
    async def historial(self, usuario: Usuario) -> Sequence[SesionSimulacion]:
        return await self.sesiones.por_usuario(usuario.id)

    async def obtener(self, sesion_id: int, usuario: Usuario) -> SesionSimulacion:
        return await self._sesion_del_usuario(sesion_id, usuario)
