"""Lógica de negocio — submódulo tribunal (CU-16, CU-17, RF-06, RF-07)."""

from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit.service import AuditService
from app.core.exceptions import BusinessRuleError, ResourceNotFoundError
from app.integrations.llm.port import TribunalLLMPort
from app.integrations.transcription.port import TranscriptionPort
from app.modules.administracion.reportes.renderers import pdf
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


def _ajustar_por_atencion(
    puntuacion: float, observaciones: str | None, atencion: float | None
) -> tuple[float, str | None]:
    """Penaliza la nota de la respuesta si el estudiante no miró al tribunal (RF-07).

    `atencion` es el contacto visual promedio (0-1) medido por cámara durante la respuesta.
    factor = 0.6 + 0.4*atencion (piso 60%): un falso negativo de Rekognition no arruina una
    buena respuesta. `atencion=None` (cámara apagada) NO penaliza.
    """
    if atencion is None:
        return puntuacion, observaciones
    atencion = max(0.0, min(1.0, atencion))
    nueva = round(puntuacion * (0.6 + 0.4 * atencion), 2)
    if atencion < 0.5:
        nota = "Mantén contacto visual con el tribunal al responder."
        observaciones = f"{observaciones} {nota}".strip() if observaciones else nota
    return nueva, observaciones


class TribunalService:
    def __init__(
        self,
        db: AsyncSession,
        llm: TribunalLLMPort,
        transcripcion: TranscriptionPort | None = None,
    ) -> None:
        self.db = db
        self.sesiones = SesionSimulacionRepository(db)
        self.versiones = VersionRepository(db)
        self.preguntas = PreguntaRepository(db)
        self.respuestas = RespuestaRepository(db)
        self.evaluaciones = EvaluacionRepository(db)
        self.audit = AuditService(db)
        self.llm = llm
        # CU-16: respaldo para respuestas que llegan solo como audio (sin texto en vivo).
        self.transcripcion = transcripcion

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

    async def obtener_pregunta(self, pregunta_id: int, usuario: Usuario) -> PreguntaTribunal:
        """Devuelve la pregunta verificando que su sesión es del usuario (anti-IDOR)."""
        pregunta, _ = await self._pregunta_del_usuario(pregunta_id, usuario)
        return pregunta

    # --- CU-16 + RF-07: responder y evaluar ------------------------------
    async def responder(
        self,
        pregunta_id: int,
        usuario: Usuario,
        texto: str | None,
        audio_url: str | None,
        atencion: float | None = None,
    ) -> tuple[RespuestaEstudiante, EvaluacionRespuesta]:
        """Registra la respuesta (texto o audio) y la evalúa con el LLM (RF-07).

        `atencion` (0-1) es el contacto visual a cámara medido durante la respuesta: ajusta
        la puntuación (mirar a otro lado penaliza). None = sin cámara, no penaliza.
        """
        pregunta, _ = await self._pregunta_del_usuario(pregunta_id, usuario)
        if await self.respuestas.por_pregunta(pregunta_id) is not None:
            raise BusinessRuleError("Esta pregunta ya fue respondida")

        # CU-16/RF-07: se evalúa el TEXTO de la respuesta. Si llega solo audio (sin texto en
        # vivo), se transcribe primero para no calificar contra una cadena vacía.
        contenido = (texto or "").strip()
        if not contenido and audio_url and self.transcripcion is not None:
            contenido = (await self.transcripcion.transcribir(audio_url)).strip()

        respuesta = RespuestaEstudiante(
            pregunta_id=pregunta_id, texto=contenido or texto, audio_url=audio_url
        )
        await self.respuestas.add(respuesta)  # flush -> respuesta.id disponible

        dto = await self.llm.evaluar_respuesta(pregunta=pregunta.texto, respuesta=contenido)
        puntuacion, observaciones = _ajustar_por_atencion(
            dto.puntuacion, dto.observaciones, atencion
        )
        evaluacion = EvaluacionRespuesta(
            respuesta_id=respuesta.id,
            puntuacion=Decimal(str(puntuacion)),
            observaciones=observaciones,
            profundidad=dto.profundidad,
        )
        await self.evaluaciones.add(evaluacion)

        await self.audit.log(
            actor_id=usuario.id,
            accion="TRIBUNAL_RESPUESTA_EVALUADA",
            entidad="respuesta_estudiante",
            entidad_id=respuesta.id,
            metadata={
                "pregunta_id": pregunta_id,
                "puntuacion": str(evaluacion.puntuacion),
                "atencion": atencion,
            },
        )
        return respuesta, evaluacion

    async def registrar_sin_respuesta(
        self, pregunta_id: int, usuario: Usuario
    ) -> tuple[RespuestaEstudiante, EvaluacionRespuesta]:
        """CU-16 (excepción): se agotó el tiempo. Registra la pregunta SIN respuesta y avanza.

        Deja una respuesta vacía con evaluación de puntuación 0 para que CU-17 tenga el dato.
        """
        pregunta, _ = await self._pregunta_del_usuario(pregunta_id, usuario)
        if await self.respuestas.por_pregunta(pregunta_id) is not None:
            raise BusinessRuleError("Esta pregunta ya fue respondida")

        respuesta = RespuestaEstudiante(pregunta_id=pregunta_id, texto=None, audio_url=None)
        await self.respuestas.add(respuesta)
        evaluacion = EvaluacionRespuesta(
            respuesta_id=respuesta.id,
            puntuacion=Decimal("0.00"),
            observaciones="No respondida: se agotó el tiempo de respuesta.",
            profundidad="NINGUNA",
        )
        await self.evaluaciones.add(evaluacion)

        await self.audit.log(
            actor_id=usuario.id,
            accion="TRIBUNAL_PREGUNTA_VENCIDA",
            entidad="respuesta_estudiante",
            entidad_id=respuesta.id,
            metadata={"pregunta_id": pregunta_id},
        )
        return respuesta, evaluacion

    # --- CU-17: informe descargable en PDF -------------------------------
    async def informe_pdf(self, sesion_id: int, usuario: Usuario) -> tuple[bytes, str]:
        """Genera el informe PDF de evaluación del tribunal de la sesión (CU-17).

        Por pregunta: puntuación, profundidad y observaciones (calidad/áreas de mejora).
        """
        await self._sesion_del_usuario(sesion_id, usuario)
        stmt = (
            select(PreguntaTribunal, EvaluacionRespuesta)
            .outerjoin(
                RespuestaEstudiante, RespuestaEstudiante.pregunta_id == PreguntaTribunal.id
            )
            .outerjoin(
                EvaluacionRespuesta,
                EvaluacionRespuesta.respuesta_id == RespuestaEstudiante.id,
            )
            .where(PreguntaTribunal.sesion_id == sesion_id)
            .order_by(PreguntaTribunal.orden)
        )
        filas = (await self.db.execute(stmt)).all()
        if not filas:
            raise ResourceNotFoundError("La sesión no tiene preguntas para el informe")

        cuerpo: list[list[str]] = [
            [
                str(pregunta.orden),
                pregunta.texto[:60],
                str(ev.puntuacion) if ev else "—",
                (ev.profundidad or "—") if ev else "—",
                (ev.observaciones or "—") if ev else "Sin responder",
            ]
            for pregunta, ev in filas
        ]
        secciones = [
            (
                "Evaluación de respuestas del tribunal",
                ["#", "Pregunta", "Puntuación", "Profundidad", "Observaciones"],
                cuerpo,
            )
        ]
        contenido = pdf.reporte_tablas_pdf(
            f"Informe de evaluación del tribunal — sesión {sesion_id}", secciones
        )
        await self.audit.log(
            actor_id=usuario.id,
            accion="TRIBUNAL_INFORME_EXPORTADO",
            entidad="sesion_simulacion",
            entidad_id=sesion_id,
        )
        return contenido, f"informe_tribunal_sesion_{sesion_id}.pdf"

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
