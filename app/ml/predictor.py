"""Inferencia de la IA evaluadora propia (modelo entrenado por el equipo).

Carga los modelos RandomForest (`.pkl` en `app/ml/models/`) y predice el nivel
(Alto/Medio/Bajo) a partir de las features que entregan los extractores. Corre **en
proceso** dentro del backend: se despliega junto con él, sin servicio HTTP aparte.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import joblib
import pandas as pd

from app.ml import rubrica

MODELS_DIR = Path(__file__).resolve().parent / "models"

# Abstención: por debajo de estos umbrales el juicio es de FRONTERA y se sugiere revisión
# humana en vez de sentenciar (la confianza ya está calibrada). AJUSTABLES por el equipo.
UMBRAL_CONFIANZA = 0.55  # confianza (prob. de la clase top) mínima para comprometerse
UMBRAL_MARGEN = 0.15  # diferencia mínima entre las dos clases más probables


@lru_cache
def _bundle(dim: str) -> dict[str, Any]:
    """Carga (una sola vez) el modelo entrenado de la dimensión."""
    bundle: dict[str, Any] = joblib.load(MODELS_DIR / f"modelo_{dim}.pkl")
    return bundle


def predecir(dim: str, valores: dict[str, float]) -> dict[str, Any]:
    """Predice nivel + confianza + factores a reforzar para la dimensión dada."""
    bundle = _bundle(dim)
    columnas: list[str] = bundle["features"]
    x = pd.DataFrame([[valores[c] for c in columnas]], columns=columnas)
    modelo = bundle["modelo"]
    proba = modelo.predict_proba(x)[0]
    clases = list(modelo.classes_)
    # Confianza = prob. de la clase top; margen = distancia a la segunda. Si cualquiera es
    # bajo, el caso está en la frontera → se sugiere revisión humana (abstención honesta).
    ordenadas = sorted((float(p) for p in proba), reverse=True)
    confianza = ordenadas[0]
    margen = ordenadas[0] - ordenadas[1] if len(ordenadas) > 1 else ordenadas[0]
    return {
        "nivel": str(modelo.predict(x)[0]),
        "confianza": round(confianza, 3),
        "margen": round(margen, 3),
        "revision_sugerida": confianza < UMBRAL_CONFIANZA or margen < UMBRAL_MARGEN,
        "probabilidades": {c: round(float(p), 3) for c, p in zip(clases, proba, strict=True)},
        "factores_a_reforzar": rubrica.factores_debiles(dim, valores, bundle.get("importancias")),
        "algoritmo": bundle["algoritmo"],
    }
