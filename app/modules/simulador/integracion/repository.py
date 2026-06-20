"""Acceso a datos — submódulo integracion (CU-14, dimensión defensa)."""

from collections.abc import Sequence

from sqlalchemy import select

from app.core.repository import BaseRepository
from app.modules.simulador.tribunal.models import (
    EvaluacionRespuesta,
    PreguntaTribunal,
    RespuestaEstudiante,
    ResultadoSimulacion,
)


class ResultadoSimulacionRepository(BaseRepository[ResultadoSimulacion]):
    model = ResultadoSimulacion

    async def por_sesion(self, sesion_id: int) -> ResultadoSimulacion | None:
        result = await self.db.execute(
            select(ResultadoSimulacion).where(ResultadoSimulacion.sesion_id == sesion_id)
        )
        return result.scalar_one_or_none()


class EvaluacionRespuestaRepository(BaseRepository[EvaluacionRespuesta]):
    model = EvaluacionRespuesta

    async def por_sesion(self, sesion_id: int) -> Sequence[EvaluacionRespuesta]:
        """Evaluaciones de toda la sesión: sesion → pregunta → respuesta → evaluacion."""
        stmt = (
            select(EvaluacionRespuesta)
            .join(
                RespuestaEstudiante,
                RespuestaEstudiante.id == EvaluacionRespuesta.respuesta_id,
            )
            .join(PreguntaTribunal, PreguntaTribunal.id == RespuestaEstudiante.pregunta_id)
            .where(PreguntaTribunal.sesion_id == sesion_id)
        )
        result = await self.db.execute(stmt)
        return result.scalars().all()
