"""Adaptador EN-PROCESO de la IA evaluadora propia.

Carga el modelo entrenado por el equipo (`app/ml/models/`) y predice **dentro** del
backend, sin servicio HTTP aparte: se despliega junto con el backend. Es la pieza que
DECIDE el nivel a partir de las features que entregan los extractores.
"""

import anyio

from app.integrations.evaluador.port import (
    DefensaFeatures,
    EvaluacionDefensaDTO,
    EvaluadorServicePort,
)
from app.ml import predictor


class LocalEvaluadorService(EvaluadorServicePort):
    async def evaluar_defensa(self, features: DefensaFeatures) -> EvaluacionDefensaDTO:
        valores: dict[str, float] = {
            "fluidez": features.fluidez,
            "contacto_visual": features.contacto_visual,
            "estabilidad_postura": features.estabilidad_postura,
            "muletillas_por_min": features.muletillas_por_min,
            "ritmo_ppm": features.ritmo_ppm,
            "pausas_largas_por_min": features.pausas_largas_por_min,
        }
        # predict_proba de RandomForest es síncrono y bloqueante: a un hilo para no
        # congelar el event loop (igual que la ruta 'documento' en analysis/aws.py).
        r = await anyio.to_thread.run_sync(predictor.predecir, "defensa", valores)
        return EvaluacionDefensaDTO(
            nivel=str(r["nivel"]),
            confianza=float(r["confianza"]),
            factores_a_reforzar=list(r["factores_a_reforzar"]),
            revision_sugerida=bool(r["revision_sugerida"]),
        )
