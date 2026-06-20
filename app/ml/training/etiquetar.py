"""Etiqueta casos REALES y construye un dataset de validación con datos propios.

Aprovecha que el sistema PERSISTE el vector de features de cada análisis/simulación
(`resultado_auditoria.features` para documento, `resultado_simulacion.features` para
defensa). Recorre los casos aún sin etiquetar, muestra sus features + la predicción
actual del modelo, y pide al EVALUADOR HUMANO el nivel real (Alto/Medio/Bajo). Exporta
a ``data/dataset_{dim}_real.csv`` en el mismo formato que el sintético, para validar o
reentrenar con datos reales (cierra la deuda de "solo sintéticos").

Cómo conseguir los ~40 casos: correr análisis/simulaciones reales (propios + de
compañeros) — cada uno persiste su vector — y luego etiquetarlos aquí.

Ejecutar (venv del backend, desde la raíz):
    python -m app.ml.training.etiquetar defensa
    python -m app.ml.training.etiquetar documento
    python -m app.ml.training.etiquetar defensa --listar   # solo lista, no pregunta
"""

from __future__ import annotations

import asyncio
import csv
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import settings
from app.ml import predictor, rubrica
from app.modules.auditoria_documental.auditoria.models import ResultadoAuditoria
from app.modules.simulador.tribunal.models import ResultadoSimulacion

DATA_DIR = Path(__file__).resolve().parent / "data"

_MODELOS = {"documento": ResultadoAuditoria, "defensa": ResultadoSimulacion}
_NIVEL = {"A": "ALTO", "M": "MEDIO", "B": "BAJO"}
_PROMPT = "Nivel REAL [A=Alto / M=Medio / B=Bajo / Enter=saltar / q=salir]: "


async def _casos(dim: str) -> list[tuple[int, dict[str, Any]]]:
    """Lee (id, features) de los resultados reales que tienen vector persistido."""
    modelo = _MODELOS[dim]
    engine = create_async_engine(settings.database_url)
    try:
        async with engine.connect() as conn:
            filas = (
                await conn.execute(
                    select(modelo.id, modelo.features).where(modelo.features.is_not(None))
                )
            ).all()
        return [(int(cid), feats) for cid, feats in filas if feats]
    finally:
        await engine.dispose()


def _ya_etiquetados(salida: Path) -> set[str]:
    if not salida.exists():
        return set()
    with salida.open(encoding="utf-8") as f:
        return {fila["caso_id"] for fila in csv.DictReader(f)}


def _anexar(salida: Path, columnas: list[str], fila: dict[str, Any]) -> None:
    nuevo = not salida.exists()
    with salida.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["caso_id", *columnas, "nivel"])
        if nuevo:
            writer.writeheader()
        writer.writerow(fila)


async def _main(dim: str, listar: bool) -> int:
    if dim not in _MODELOS:
        print(f"Dimensión inválida: {dim!r}. Usa 'documento' o 'defensa'.")
        return 1

    columnas = rubrica.features(dim)
    salida = DATA_DIR / f"dataset_{dim}_real.csv"
    ya = _ya_etiquetados(salida)
    casos = [(cid, feats) for cid, feats in await _casos(dim) if str(cid) not in ya]

    print(
        f"Dimensión '{dim}': {len(casos)} caso(s) real(es) sin etiquetar "
        f"(ya etiquetados: {len(ya)}). Salida: {salida.name}"
    )
    if not casos:
        print("No hay casos nuevos. Corre análisis/simulaciones REALES y vuelve a intentarlo.")
        return 0
    if listar:
        for cid, feats in casos:
            print(f"  caso {cid}: {feats}")
        return 0

    DATA_DIR.mkdir(exist_ok=True)
    etiquetados = 0
    for cid, feats in casos:
        try:
            valores = {c: float(feats[c]) for c in columnas}
        except (KeyError, TypeError, ValueError):
            print(f"  caso {cid}: features incompletas, saltado.")
            continue
        pred = predictor.predecir(dim, valores)
        print(f"\n--- caso {cid} ---")
        for c in columnas:
            print(f"   {c}: {valores[c]}")
        print(f"   el modelo predice: {pred['nivel']} (confianza {pred['confianza']})")
        resp = input(_PROMPT).strip().upper()
        if resp == "Q":
            break
        if resp not in _NIVEL:
            continue
        fila: dict[str, Any] = {"caso_id": str(cid), "nivel": _NIVEL[resp], **valores}
        _anexar(salida, columnas, fila)  # guarda incremental por si se interrumpe
        etiquetados += 1

    print(f"\n{etiquetados} caso(s) etiquetado(s) -> {salida}")
    return 0


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    argumentos = sys.argv[1:]
    quiere_listar = "--listar" in argumentos
    dimension = next((a for a in argumentos if not a.startswith("-")), "")
    raise SystemExit(asyncio.run(_main(dimension, quiere_listar)))
