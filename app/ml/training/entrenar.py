"""Entrena y compara dos modelos PROPIOS (sin pesos preentrenados de terceros).

- RandomForest: clásico, explicable (importancia de indicadores = qué reforzar).
- Red neuronal MLP: entrenada desde cero, por si se valora el componente "deep learning".

Selección por **validación cruzada** (5-fold, F1-macro) para una estimación honesta.
El mejor se **calibra** (CalibratedClassifierCV) para que `predict_proba` —la "confianza"
que ve el estudiante— sea fiable. Guarda el modelo calibrado + las importancias en
``app/ml/models/``. Ejecutar (venv del backend): ``python -m app.ml.training.entrenar``
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score
from sklearn.model_selection import StratifiedKFold, cross_val_score, train_test_split
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from app.ml import rubrica

DATA_DIR = Path(__file__).resolve().parent / "data"
MODELS_DIR = Path(__file__).resolve().parents[1] / "models"  # app/ml/models

CV = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)


def _modelos() -> dict[str, Any]:
    return {
        "RandomForest": RandomForestClassifier(
            n_estimators=300, max_depth=None, random_state=42, n_jobs=-1
        ),
        "GradientBoosting": HistGradientBoostingClassifier(
            max_iter=300, learning_rate=0.08, random_state=42
        ),
        "RedNeuronal_MLP": make_pipeline(
            StandardScaler(),
            MLPClassifier(hidden_layer_sizes=(32, 16), max_iter=800, random_state=42),
        ),
    }


def _bondad(dim: str, x: pd.DataFrame) -> np.ndarray:
    """Matriz de bondad (0=peor … 1=mejor) de cada feature, respetando su dirección."""
    indicadores = rubrica.DIMENSIONES[dim]
    bondad = np.zeros((len(x), len(indicadores)))
    for j, (nombre, ind) in enumerate(indicadores.items()):
        lo, hi = ind.rango
        norm = (x[nombre].to_numpy() - lo) / (hi - lo)
        bondad[:, j] = norm if ind.direccion == 1 else 1.0 - norm
    return bondad


def _regla_oraculo(dim: str, x: pd.DataFrame, t_bajo: float, t_alto: float) -> np.ndarray:
    """Baseline determinista: la MISMA regla que generó las etiquetas (media ponderada +
    gatekeeper), aplicada a las features. Mide cuánto AÑADE el ML sobre la regla."""
    bondad = _bondad(dim, x)
    score = np.average(bondad, axis=1, weights=np.array(rubrica.pesos(dim)))
    niveles = np.where(score < t_bajo, "BAJO", np.where(score < t_alto, "MEDIO", "ALTO"))
    idx = rubrica.features(dim).index(rubrica.CRITICO[dim])
    niveles[(niveles == "ALTO") & (bondad[:, idx] < 0.30)] = "MEDIO"
    return niveles


def entrenar_dimension(dim: str) -> None:
    df = pd.read_csv(DATA_DIR / f"dataset_{dim}.csv")
    x = df[rubrica.features(dim)]
    y = df["nivel"]
    x_tr, x_te, y_tr, y_te = train_test_split(x, y, test_size=0.25, stratify=y, random_state=42)

    print(f"\n{'=' * 66}\nDIMENSIÓN: {dim.upper()}   (n={len(df)})\n{'=' * 66}")
    resultados: dict[str, tuple[float, float, float]] = {}
    for nombre, modelo in _modelos().items():
        cv_f1 = cross_val_score(modelo, x, y, cv=CV, scoring="f1_macro")  # estimación honesta
        modelo.fit(x_tr, y_tr)
        pred = modelo.predict(x_te)
        acc = accuracy_score(y_te, pred)
        f1 = f1_score(y_te, pred, average="macro")
        resultados[nombre] = (acc, f1, float(cv_f1.mean()))
        print(f"\n--- {nombre} ---")
        print(f"Hold-out  -> Accuracy: {acc:.3f}   F1-macro: {f1:.3f}")
        print(f"CV 5-fold -> F1-macro: {cv_f1.mean():.3f} +/- {cv_f1.std():.3f}")
        print("Matriz de confusión (filas=real, cols=predicho · orden BAJO/MEDIO/ALTO):")
        print(confusion_matrix(y_te, pred, labels=list(rubrica.NIVELES)))
        print(classification_report(y_te, pred, labels=list(rubrica.NIVELES), zero_division=0))

    # Baseline REGLA-oráculo (sin ML): la misma regla que generó las etiquetas, con
    # umbrales fijados en TRAIN y evaluada en el MISMO hold-out. Diagnóstico honesto del
    # aporte del ML (la regla es el oráculo; el ML añade calibración, robustez a ruido/
    # faltantes y generalización fuera de los umbrales fijos).
    score_tr = np.average(_bondad(dim, x_tr), axis=1, weights=np.array(rubrica.pesos(dim)))
    t_bajo, t_alto = np.quantile(score_tr, [0.33, 0.73])
    f1_regla = f1_score(y_te, _regla_oraculo(dim, x_te, t_bajo, t_alto), average="macro")
    f1_rf = resultados["RandomForest"][1]
    print("\n--- Baseline REGLA (oráculo determinista, sin ML) ---")
    print(
        f"Hold-out  -> F1-macro: {f1_regla:.3f}   (RF hold-out {f1_rf:.3f}; "
        f"aporte del ML {f1_rf - f1_regla:+.3f})"
    )
    print("   El ML se justifica por calibración, tolerancia a ruido/faltantes y")
    print("   generalización donde los umbrales fijos no aplican (datos reales).")

    mejor = max(resultados, key=lambda k: resultados[k][2])  # elige por CV F1-macro

    # Importancias SIEMPRE desde un RandomForest sobre todo el set (explicabilidad).
    rf = RandomForestClassifier(n_estimators=300, random_state=42, n_jobs=-1).fit(x, y)
    importancias = {
        n: round(float(imp), 4)
        for n, imp in zip(rubrica.features(dim), rf.feature_importances_, strict=True)
    }

    # Modelo desplegado: el mejor, CALIBRADO → probabilidades (la "confianza") fiables.
    calibrado = CalibratedClassifierCV(_modelos()[mejor], method="isotonic", cv=5).fit(x, y)

    MODELS_DIR.mkdir(exist_ok=True)
    joblib.dump(
        {
            "modelo": calibrado,
            "features": rubrica.features(dim),
            "niveles": list(rubrica.NIVELES),
            "algoritmo": f"{mejor} (calibrado)",
            "importancias": importancias,
        },
        MODELS_DIR / f"modelo_{dim}.pkl",
    )
    print(f"\n>> Mejor para '{dim}': {mejor} (CV F1={resultados[mejor][2]:.3f}, calibrado) "
          f"-> models/modelo_{dim}.pkl")
    print("Importancia de indicadores (RandomForest):")
    for nombre, imp in sorted(importancias.items(), key=lambda t: t[1], reverse=True):
        print(f"   {imp:6.3f}  {nombre}")


def main() -> None:
    for dim in rubrica.DIMENSIONES:
        entrenar_dimension(dim)


if __name__ == "__main__":
    main()
