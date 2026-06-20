"""Acceso a datos — submódulo biometrico (CU-14, RF-03/04/05)."""

from collections.abc import Sequence
from typing import Any

from sqlalchemy import func, select

from app.core.repository import BaseRepository
from app.modules.simulador.biometrico.models import MetricaBiometrica


class MetricaBiometricaRepository(BaseRepository[MetricaBiometrica]):
    model = MetricaBiometrica

    async def por_sesion(self, sesion_id: int) -> Sequence[MetricaBiometrica]:
        """Histórico (CU-14): métricas de la sesión, en orden cronológico."""
        result = await self.db.execute(
            select(MetricaBiometrica)
            .where(MetricaBiometrica.sesion_id == sesion_id)
            .order_by(MetricaBiometrica.momento)
        )
        return result.scalars().all()

    async def resumen(self, sesion_id: int) -> dict[str, Any]:
        """Agrega las métricas de una sesión (promedios + total de muletillas)."""
        stmt = select(
            func.count(MetricaBiometrica.id),
            func.avg(MetricaBiometrica.postura_score),
            func.avg(MetricaBiometrica.contacto_visual_pct),
            func.coalesce(func.sum(MetricaBiometrica.muletillas_conteo), 0),
            func.avg(MetricaBiometrica.ritmo_wpm),
            func.coalesce(func.sum(MetricaBiometrica.pausas_largas_conteo), 0),
        ).where(MetricaBiometrica.sesion_id == sesion_id)
        intervalos, postura_avg, contacto_avg, muletillas_total, ritmo_avg, pausas_total = (
            await self.db.execute(stmt)
        ).one()
        return {
            "intervalos": int(intervalos),
            "postura_score_promedio": postura_avg,
            "contacto_visual_pct_promedio": contacto_avg,
            "muletillas_total": int(muletillas_total),
            "ritmo_wpm_promedio": int(ritmo_avg) if ritmo_avg is not None else None,
            "pausas_total": int(pausas_total),
        }
