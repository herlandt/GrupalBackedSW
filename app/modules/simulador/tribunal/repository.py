"""Acceso a datos — submódulo tribunal (CU-16, CU-17, RF-06, RF-07)."""

from collections.abc import Sequence

from sqlalchemy import select

from app.core.repository import BaseRepository
from app.modules.simulador.tribunal.models import (
    EvaluacionRespuesta,
    PreguntaTribunal,
    RespuestaEstudiante,
)


class PreguntaRepository(BaseRepository[PreguntaTribunal]):
    model = PreguntaTribunal

    async def por_sesion(self, sesion_id: int) -> Sequence[PreguntaTribunal]:
        result = await self.db.execute(
            select(PreguntaTribunal)
            .where(PreguntaTribunal.sesion_id == sesion_id)
            .order_by(PreguntaTribunal.orden)
        )
        return result.scalars().all()

    async def existe_para_sesion(self, sesion_id: int) -> bool:
        result = await self.db.execute(
            select(PreguntaTribunal.id).where(PreguntaTribunal.sesion_id == sesion_id).limit(1)
        )
        return result.scalar_one_or_none() is not None


class RespuestaRepository(BaseRepository[RespuestaEstudiante]):
    model = RespuestaEstudiante

    async def por_pregunta(self, pregunta_id: int) -> RespuestaEstudiante | None:
        result = await self.db.execute(
            select(RespuestaEstudiante).where(RespuestaEstudiante.pregunta_id == pregunta_id)
        )
        return result.scalar_one_or_none()


class EvaluacionRepository(BaseRepository[EvaluacionRespuesta]):
    model = EvaluacionRespuesta

    async def por_respuesta(self, respuesta_id: int) -> EvaluacionRespuesta | None:
        result = await self.db.execute(
            select(EvaluacionRespuesta).where(EvaluacionRespuesta.respuesta_id == respuesta_id)
        )
        return result.scalar_one_or_none()
