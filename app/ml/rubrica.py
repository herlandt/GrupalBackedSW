"""Rúbrica de evaluación: features, niveles y distribuciones por nivel.

Fuente de verdad de la IA evaluadora propia: qué mide cada dimensión, en qué rango vive
cada indicador, hacia dónde es "mejor" y cómo se distribuye por nivel (Alto/Medio/Bajo).
La usan el entrenamiento (para muestrear) y la inferencia (para explicar qué reforzar).
"""

from __future__ import annotations

from dataclasses import dataclass

NIVELES: tuple[str, ...] = ("BAJO", "MEDIO", "ALTO")
ORDEN_NIVEL: dict[str, int] = {"BAJO": 0, "MEDIO": 1, "ALTO": 2}


@dataclass(frozen=True)
class Indicador:
    """Un indicador medible de una dimensión.

    dist:      (media, desviación) por nivel — genera datos sintéticos realistas.
    rango:     (mín, máx) físico del indicador — recorte y normalización.
    direccion: +1 si "mayor = mejor", -1 si "menor = mejor" — explica qué reforzar.
    """

    dist: dict[str, tuple[float, float]]
    rango: tuple[float, float]
    direccion: int


# --- Dimensión 1: Documento (competencia metodológica y argumentativa, RF-01) ---
DOCUMENTO: dict[str, Indicador] = {
    "coherencia_objetivos_resultados": Indicador(
        {"BAJO": (0.30, 0.12), "MEDIO": (0.57, 0.12), "ALTO": (0.85, 0.09)}, (0.0, 1.0), +1),
    "cohesion_secciones": Indicador(
        {"BAJO": (0.35, 0.13), "MEDIO": (0.60, 0.13), "ALTO": (0.83, 0.10)}, (0.0, 1.0), +1),
    "completitud_estructural": Indicador(
        {"BAJO": (0.45, 0.15), "MEDIO": (0.68, 0.14), "ALTO": (0.88, 0.09)}, (0.0, 1.0), +1),
    "formalidad_redaccion": Indicador(
        {"BAJO": (0.40, 0.14), "MEDIO": (0.62, 0.13), "ALTO": (0.84, 0.10)}, (0.0, 1.0), +1),
    "claridad_problema": Indicador(
        {"BAJO": (0.32, 0.12), "MEDIO": (0.58, 0.12), "ALTO": (0.86, 0.09)}, (0.0, 1.0), +1),
    "densidad_referencias": Indicador(
        {"BAJO": (0.38, 0.15), "MEDIO": (0.60, 0.15), "ALTO": (0.80, 0.12)}, (0.0, 1.0), +1),
}

# --- Dimensión 2: Defensa oral (competencia comunicativa, RF-04/RF-05) ---
DEFENSA: dict[str, Indicador] = {
    "fluidez": Indicador(
        {"BAJO": (0.34, 0.13), "MEDIO": (0.60, 0.12), "ALTO": (0.85, 0.09)}, (0.0, 1.0), +1),
    "contacto_visual": Indicador(
        {"BAJO": (0.35, 0.15), "MEDIO": (0.62, 0.14), "ALTO": (0.83, 0.11)}, (0.0, 1.0), +1),
    "estabilidad_postura": Indicador(
        {"BAJO": (0.40, 0.14), "MEDIO": (0.65, 0.13), "ALTO": (0.84, 0.10)}, (0.0, 1.0), +1),
    "muletillas_por_min": Indicador(
        {"BAJO": (14.0, 4.0), "MEDIO": (7.0, 3.0), "ALTO": (2.5, 1.5)}, (0.0, 30.0), -1),
    "ritmo_ppm": Indicador(
        {"BAJO": (100.0, 22.0), "MEDIO": (118.0, 16.0), "ALTO": (138.0, 10.0)}, (60.0, 200.0), +1),
    "pausas_largas_por_min": Indicador(
        {"BAJO": (5.0, 2.0), "MEDIO": (2.5, 1.3), "ALTO": (0.8, 0.6)}, (0.0, 15.0), -1),
    # Coherencia entre lo que el estudiante DICE (transcripción) y su DOCUMENTO: similitud
    # semántica (embeddings). Mide que la exposición cubra y no contradiga la tesis (↑ mejor).
    "coherencia_discurso_documento": Indicador(
        {"BAJO": (0.40, 0.14), "MEDIO": (0.62, 0.13), "ALTO": (0.82, 0.10)}, (0.0, 1.0), +1),
}

DIMENSIONES: dict[str, dict[str, Indicador]] = {"documento": DOCUMENTO, "defensa": DEFENSA}


def features(dim: str) -> list[str]:
    """Nombres de los indicadores de la dimensión, en orden estable."""
    return list(DIMENSIONES[dim].keys())


# Pesos PEDAGÓGICOS por indicador: cuánto pesa en el juicio, según la rúbrica/literatura
# (no es un promedio plano). AJUSTABLES por el equipo/docente. Claridad y coherencia son el
# núcleo intelectual; fluidez es el núcleo de la oratoria.
PESOS: dict[str, dict[str, float]] = {
    "documento": {
        "coherencia_objetivos_resultados": 1.5,
        "cohesion_secciones": 1.0,
        "completitud_estructural": 1.0,
        "formalidad_redaccion": 0.8,
        "claridad_problema": 1.5,
        "densidad_referencias": 0.8,
    },
    "defensa": {
        "fluidez": 1.5,
        "contacto_visual": 1.0,
        "estabilidad_postura": 1.0,
        "muletillas_por_min": 1.0,
        "ritmo_ppm": 1.0,
        "pausas_largas_por_min": 0.8,
        # Dominar y exponer fielmente el documento es núcleo de una buena defensa.
        "coherencia_discurso_documento": 1.4,
    },
}

# Indicador CRÍTICO (gatekeeper): si está muy bajo, impide el nivel ALTO, como en una
# rúbrica real (una prerregla, no un promedio).
CRITICO: dict[str, str] = {"documento": "claridad_problema", "defensa": "fluidez"}


def pesos(dim: str) -> list[float]:
    """Pesos de los indicadores de la dimensión, en el mismo orden que `features()`."""
    return [PESOS[dim][nombre] for nombre in features(dim)]


def combinar_niveles(nivel_doc: str, nivel_def: str) -> str:
    """Nivel general = promedio ordinal de documento y defensa, con EMPATE hacia arriba.

    Se usa `(a+b+1)//2` (no `round`, que aplica banker's rounding y desempataba asimétrico:
    BAJO+MEDIO→BAJO pero MEDIO+ALTO→ALTO). Ahora los empates suben de forma consistente.
    """
    indice = (ORDEN_NIVEL[nivel_doc] + ORDEN_NIVEL[nivel_def] + 1) // 2
    return NIVELES[indice]


def factores_debiles(
    dim: str,
    valores: dict[str, float],
    importancias: dict[str, float] | None = None,
    top: int = 3,
) -> list[str]:
    """Indicadores que más arrastran el nivel hacia abajo (qué reforzar primero).

    Si se pasan las `importancias` del modelo, el déficit de cada indicador se pondera
    por cuánto pesa ese indicador en la decisión. Así la explicación queda alineada con
    el razonamiento REAL del modelo, no con una regla independiente.
    """
    pesos = importancias or {}
    debilidades: list[tuple[float, str]] = []
    for nombre, ind in DIMENSIONES[dim].items():
        lo, hi = ind.rango
        norm = (valores[nombre] - lo) / (hi - lo) if hi > lo else 0.0
        # Recorta a [0,1]: ritmo/muletillas pueden venir fuera de rango (sin clip) y un
        # déficit negativo o >1 distorsionaría el ranking de factores a reforzar.
        norm = min(1.0, max(0.0, norm))
        deficit = (1.0 - norm) if ind.direccion == 1 else norm
        debilidades.append((deficit * pesos.get(nombre, 1.0), nombre))
    debilidades.sort(reverse=True)
    return [nombre for _, nombre in debilidades[:top]]


# Texto humano por indicador (presentación; el sustantivo se redacta a mano, mientras que
# el verbo de mejora y el objetivo salen de la rúbrica). Convierte claves crudas en consejos.
ETIQUETA: dict[str, str] = {
    "coherencia_objetivos_resultados": "la coherencia entre objetivos y resultados",
    "cohesion_secciones": "la cohesión entre secciones",
    "completitud_estructural": "la completitud estructural del documento",
    "formalidad_redaccion": "la formalidad de la redacción",
    "claridad_problema": "la claridad del planteamiento del problema",
    "densidad_referencias": "la densidad de referencias y citas",
    "fluidez": "la fluidez al hablar",
    "contacto_visual": "el contacto visual con el tribunal",
    "estabilidad_postura": "la estabilidad de la postura",
    "muletillas_por_min": "las muletillas por minuto",
    "ritmo_ppm": "el ritmo de habla (palabras/min)",
    "pausas_largas_por_min": "las pausas largas",
    "coherencia_discurso_documento": "la coherencia entre tu exposición y tu documento",
}


def consejo(dim: str, nombre: str, valor: float) -> str:
    """Frase accionable para un indicador débil: qué hacer + valor actual + objetivo (ALTO)."""
    ind = DIMENSIONES[dim][nombre]
    etiqueta = ETIQUETA.get(nombre, nombre)
    objetivo = ind.dist["ALTO"][0]
    if ind.direccion == 1:
        return f"sube {etiqueta} (vas en {valor:g}, apunta a ≥ {objetivo:g})"
    return f"reduce {etiqueta} (vas en {valor:g}, apunta a ≤ {objetivo:g})"


def consejos(dim: str, factores: list[str], valores: dict[str, float]) -> list[str]:
    """Consejos accionables para los factores débiles, cada uno con su valor y objetivo."""
    return [consejo(dim, n, valores[n]) for n in factores if n in valores]
