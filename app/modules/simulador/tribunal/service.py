"""Lógica de negocio — submódulo tribunal (CU-16, CU-17, RF-06, RF-07)."""

from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit.service import AuditService
from app.core.exceptions import BusinessRuleError, ResourceNotFoundError
from app.integrations.llm.port import TribunalLLMPort
from app.modules.administracion.usuarios.models import Usuario
from app.modules.auditoria_documental.documentos.repository import VersionRepository
from app.modules.simulador.simulaciones.models import SesionSimulacion
from app.modules.simulador.simulaciones.repository import SesionSimulacionRepository
from app.modules.simulador.tribunal.models import (
    EvaluacionRespuesta,
    PreguntaTribunal,
    RespuestaEstudiante,
)
from app.modules.simulador.tribunal.repository import (
    EvaluacionRepository,
    PreguntaRepository,
    RespuestaRepository,
)


def _now() -> datetime:
    """Instante actual en UTC, sin zona (las columnas son TIMESTAMP naive)."""
    return datetime.now(UTC).replace(tzinfo=None)


class TribunalService:
    def __init__(self, db: AsyncSession, llm: TribunalLLMPort) -> None:
        self.db = db
        self.sesiones = SesionSimulacionRepository(db)
        self.versiones = VersionRepository(db)
        self.preguntas = PreguntaRepository(db)
        self.respuestas = RespuestaRepository(db)
        self.evaluaciones = EvaluacionRepository(db)
        self.audit = AuditService(db)
        self.llm = llm

    # --- Helpers (IDOR) --------------------------------------------------
    async def _sesion_del_usuario(self, sesion_id: int, usuario: Usuario) -> SesionSimulacion:
        sesion = await self.sesiones.get(sesion_id)
        if sesion is None or sesion.usuario_id != usuario.id:
            # No revelar la existencia de sesiones ajenas: tratar como no encontrada.
            raise ResourceNotFoundError(f"Sesión {sesion_id} no existe")
        return sesion

    async def _pregunta_del_usuario(
        self, pregunta_id: int, usuario: Usuario
    ) -> tuple[PreguntaTribunal, SesionSimulacion]:
        pregunta = await self.preguntas.get(pregunta_id)
        if pregunta is None:
            raise ResourceNotFoundError(f"Pregunta {pregunta_id} no existe")
        sesion = await self._sesion_del_usuario(pregunta.sesion_id, usuario)
        return pregunta, sesion

    # --- RF-06: generar preguntas ----------------------------------------
    async def generar_preguntas(
        self, sesion_id: int, usuario: Usuario
    ) -> Sequence[PreguntaTribunal]:
        """Genera las preguntas del tribunal desde el documento de la tesis (en S3)."""
        sesion = await self._sesion_del_usuario(sesion_id, usuario)
        if await self.preguntas.existe_para_sesion(sesion_id):
            raise BusinessRuleError("Esta sesión ya tiene preguntas generadas")

        version = await self.versiones.get(sesion.version_documento_id)
        if version is None:
            raise ResourceNotFoundError("La versión de documento de la sesión no existe")

        dtos = await self.llm.generar_preguntas(
            archivo_url=version.archivo_url,
            formato=version.formato.value,
            nivel_dificultad=sesion.nivel_dificultad.value,
        )
        for dto in dtos:
            self.db.add(PreguntaTribunal(sesion_id=sesion_id, orden=dto.orden, texto=dto.texto))
        await self.db.flush()

        await self.audit.log(
            actor_id=usuario.id,
            accion="TRIBUNAL_PREGUNTAS_GENERADAS",
            entidad="sesion_simulacion",
            entidad_id=sesion_id,
            metadata={"cantidad": len(dtos)},
        )
        return await self.preguntas.por_sesion(sesion_id)

    async def listar_preguntas(
        self, sesion_id: int, usuario: Usuario
    ) -> Sequence[PreguntaTribunal]:
        await self._sesion_del_usuario(sesion_id, usuario)
        return await self.preguntas.por_sesion(sesion_id)

    # --- CU-16 + RF-07: responder y evaluar ------------------------------
    async def responder(
        self,
        pregunta_id: int,
        usuario: Usuario,
        texto: str | None,
        audio_url: str | None,
    ) -> tuple[RespuestaEstudiante, EvaluacionRespuesta]:
        """Registra la respuesta (texto o audio) y la evalúa con el LLM (RF-07)."""
        pregunta, _ = await self._pregunta_del_usuario(pregunta_id, usuario)
        if await self.respuestas.por_pregunta(pregunta_id) is not None:
            raise BusinessRuleError("Esta pregunta ya fue respondida")

        respuesta = RespuestaEstudiante(pregunta_id=pregunta_id, texto=texto, audio_url=audio_url)
        await self.respuestas.add(respuesta)  # flush -> respuesta.id disponible

        # El LLM evalúa el texto. (Con audio, el adaptador real transcribiría primero.)
        dto = await self.llm.evaluar_respuesta(pregunta=pregunta.texto, respuesta=texto or "")
        evaluacion = EvaluacionRespuesta(
            respuesta_id=respuesta.id,
            puntuacion=Decimal(str(dto.puntuacion)),
            observaciones=dto.observaciones,
            profundidad=dto.profundidad,
        )
        await self.evaluaciones.add(evaluacion)

        await self.audit.log(
            actor_id=usuario.id,
            accion="TRIBUNAL_RESPUESTA_EVALUADA",
            entidad="respuesta_estudiante",
            entidad_id=respuesta.id,
            metadata={"pregunta_id": pregunta_id, "puntuacion": str(evaluacion.puntuacion)},
        )
        return respuesta, evaluacion

    # --- CU-17: consultar la evaluación ----------------------------------
    async def obtener_evaluacion(
        self, pregunta_id: int, usuario: Usuario
    ) -> EvaluacionRespuesta:
        await self._pregunta_del_usuario(pregunta_id, usuario)
        respuesta = await self.respuestas.por_pregunta(pregunta_id)
        if respuesta is None:
            raise ResourceNotFoundError("La pregunta aún no tiene respuesta")
        evaluacion = await self.evaluaciones.por_respuesta(respuesta.id)
        if evaluacion is None:
            raise ResourceNotFoundError("La respuesta aún no tiene evaluación")
        return evaluacion
