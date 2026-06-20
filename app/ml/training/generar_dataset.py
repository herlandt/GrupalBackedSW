"""Genera datasets sintéticos etiquetados (Alto/Medio/Bajo) desde la rúbrica.

⚠️  DATOS SINTÉTICOS, pero REALISTAS: las features se generan a partir de una "calidad
latente" compartida por muestra (→ quedan CORRELACIONADAS, como en una tesis real: buena
coherencia suele venir con buena estructura) y el nivel se DERIVA de un puntaje de esas
features + ruido de frontera, NO al revés. Así el modelo aprende un mapeo genuino
feature→nivel en lugar de separar gaussianas ya etiquetadas. NO sustituye a un corpus
real etiquetado por evaluadores humanos.
Ejecutar (venv del backend, desde la raíz): ``python -m app.ml.training.generar_dataset``
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from app.ml import rubrica

DATA_DIR = Path(__file__).resolve().parent / "data"

N_MUESTRAS = 1500
PROP_NIVELES = [0.33, 0.40, 0.27]  # leve mayoría "MEDIO", como en la realidad
RUIDO_FEATURE = 0.9  # ruido individual por feature (rompe la colinealidad perfecta)
RUIDO_FRONTERA = 0.045  # ruido en el puntaje → casos ambiguos en los límites de nivel
SEED = 42


def generar(dim: str, n: int, rng: np.random.Generator) -> pd.DataFrame:
    """Muestrea `n` filas: features correlacionadas y el nivel DERIVADO de ellas."""
    indicadores = rubrica.DIMENSIONES[dim]
    # 1) Calidad latente compartida → todas las features se mueven juntas (correlación).
    calidad = np.clip(rng.normal(0.5, 0.22, size=n), 0.02, 0.98)

    columnas: dict[str, np.ndarray] = {}
    bondad = np.zeros((n, len(indicadores)))
    for j, (nombre, ind) in enumerate(indicadores.items()):
        # La media de cada feature interpola entre su ancla BAJO y ALTO según la calidad.
        ancla_bajo, ancla_alto = ind.dist["BAJO"][0], ind.dist["ALTO"][0]
        media = ancla_bajo + calidad * (ancla_alto - ancla_bajo)
        lo, hi = ind.rango
        valor = np.clip(rng.normal(media, ind.dist["MEDIO"][1] * RUIDO_FEATURE), lo, hi)
        columnas[nombre] = valor.round(4)
        norm = (valor - lo) / (hi - lo)
        bondad[:, j] = norm if ind.direccion == 1 else 1.0 - norm  # 0=peor … 1=mejor

    # 2) Nivel DERIVADO del puntaje. Razonamiento EXPERTO: media PONDERADA por la
    #    importancia pedagógica de cada indicador (rúbrica), no un promedio plano.
    pesos = np.array(rubrica.pesos(dim))
    puntaje = np.average(bondad, axis=1, weights=pesos) + rng.normal(0.0, RUIDO_FRONTERA, size=n)
    t_bajo, t_alto = np.quantile(puntaje, [PROP_NIVELES[0], PROP_NIVELES[0] + PROP_NIVELES[1]])
    niveles = np.where(puntaje < t_bajo, "BAJO", np.where(puntaje < t_alto, "MEDIO", "ALTO"))

    # 3) Prerregla (gatekeeper): un indicador CRÍTICO muy bajo impide el nivel ALTO —
    #    como en una rúbrica real (sin problema claro / sin fluidez, no es "Alto").
    idx = rubrica.features(dim).index(rubrica.CRITICO[dim])
    niveles[(niveles == "ALTO") & (bondad[:, idx] < 0.30)] = "MEDIO"

    df = pd.DataFrame(columnas)
    df["nivel"] = niveles
    return df


def main() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    rng = np.random.default_rng(SEED)
    for dim in rubrica.DIMENSIONES:
        df = generar(dim, N_MUESTRAS, rng)
        salida = DATA_DIR / f"dataset_{dim}.csv"
        df.to_csv(salida, index=False)
        print(f"[OK] {salida.name}: {len(df)} filas")
        print(df["nivel"].value_counts().reindex(rubrica.NIVELES).to_string(), "\n")


if __name__ == "__main__":
    main()
