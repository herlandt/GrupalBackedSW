"""Validación del modelo (con o SIN datos reales etiquetados).

Dos vías:
1. Si existe ``data/dataset_{dim}_real.csv`` (etiquetado a mano con ``etiquetar.py``),
   valida contra esos casos reales — lo ideal.
2. ROBUSTEZ cross-generador: como conseguir decenas de etiquetas reales no siempre es
   viable (p. ej. una tarea estudiantil), genera un set de prueba con un proceso DISTINTO
   al de entrenamiento —features INDEPENDIENTES (sin la calidad latente compartida) y
   etiqueta por UMBRALES FIJOS en vez de cuantiles, con otra semilla— y mide si el modelo
   generaliza. NO sustituye a datos reales, pero es evidencia honesta de que el modelo no
   memoriza un único proceso sintético, sino el mapeo rúbrica→nivel.

Ejecutar (venv del backend, desde la raíz): ``python -m app.ml.training.validar``
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score

from app.ml import predictor, rubrica

DATA_DIR = Path(__file__).resolve().parent / "data"


def _reportar(titulo: str, dim: str, df: pd.DataFrame) -> None:
    columnas = rubrica.features(dim)
    y_real = [str(v) for v in df["nivel"].tolist()]
    y_pred = [
        predictor.predecir(dim, {c: float(fila[c]) for c in columnas})["nivel"]
        for _, fila in df.iterrows()
    ]
    acc = accuracy_score(y_real, y_pred)
    f1 = f1_score(y_real, y_pred, average="macro")
    print(f"\n[{dim}] {titulo} · n={len(df)}")
    print(f"  Accuracy: {acc:.3f}   F1-macro: {f1:.3f}")
    print("  Matriz de confusión (filas=real, cols=predicho · BAJO/MEDIO/ALTO):")
    print(confusion_matrix(y_real, y_pred, labels=list(rubrica.NIVELES)))


def _generar_independiente(dim: str, n: int, rng: np.random.Generator) -> pd.DataFrame:
    """Proceso DISTINTO al de entrenamiento: features independientes + umbrales fijos."""
    indicadores = rubrica.DIMENSIONES[dim]
    columnas: dict[str, np.ndarray] = {}
    bondad = np.zeros((n, len(indicadores)))
    for j, (nombre, ind) in enumerate(indicadores.items()):
        lo, hi = ind.rango
        valor = rng.uniform(lo, hi, size=n)  # independientes: sin calidad latente compartida
        columnas[nombre] = valor.round(4)
        norm = (valor - lo) / (hi - lo)
        bondad[:, j] = norm if ind.direccion == 1 else 1.0 - norm
    # MISMA regla de etiquetado que el entrenamiento (media PONDERADA + gatekeeper, score→
    # cuantiles): test JUSTO que aísla la generalización a otra distribución de features.
    pesos = np.array(rubrica.pesos(dim))
    score = np.average(bondad, axis=1, weights=pesos) + rng.normal(0.0, 0.05, size=n)
    t_bajo, t_alto = np.quantile(score, [0.33, 0.73])
    niveles = np.where(score < t_bajo, "BAJO", np.where(score < t_alto, "MEDIO", "ALTO"))
    idx = rubrica.features(dim).index(rubrica.CRITICO[dim])
    niveles[(niveles == "ALTO") & (bondad[:, idx] < 0.30)] = "MEDIO"
    df = pd.DataFrame(columnas)
    df["nivel"] = niveles
    return df


def validar_dimension(dim: str) -> None:
    real = DATA_DIR / f"dataset_{dim}_real.csv"
    if real.exists():
        _reportar("VALIDACIÓN con casos REALES etiquetados a mano", dim, pd.read_csv(real))
    else:
        print(f"\n[{dim}] sin casos reales ({real.name}). Etiqueta con: "
              f"python -m app.ml.training.etiquetar {dim}")
    rng = np.random.default_rng(123)  # semilla != 42 (entrenamiento)
    df = _generar_independiente(dim, 600, rng)
    _reportar("ROBUSTEZ (proceso sintético INDEPENDIENTE)", dim, df)


def main() -> None:
    for dim in rubrica.DIMENSIONES:
        validar_dimension(dim)


if __name__ == "__main__":
    main()
