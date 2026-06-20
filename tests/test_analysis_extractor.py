"""Tests del extractor documental (partición + features). Sin red: usa el fallback local
(clientes AWS = None) para validar la lógica sin gastar créditos ni depender de AWS.
"""

from app.integrations.analysis.extraction import (
    SECCIONES_ESPERADAS,
    _seccion_de_encabezado,
    particionar,
    trozos,
)
from app.integrations.analysis.features import DocumentoFeatures

_TESIS = """Introduccion
Aborda el problema de la desercion y la pregunta de investigacion.
Objetivos
Determinar los factores de la desercion.
Metodologia
Diseno cuantitativo con una muestra de 200 estudiantes.
Resultados
El factor economico explica el 40 por ciento.
Conclusiones
La desercion se relaciona con factores economicos. (Garcia, 2020) [1]
Referencias
(Lopez, 2019)
"""


def test_particionar_detecta_secciones() -> None:
    secciones = particionar(_TESIS)
    for esperada in SECCIONES_ESPERADAS:
        assert esperada in secciones, esperada


_TESIS_REAL = """CAPÍTULO I. INTRODUCCIÓN
Aborda el problema de la deserción y la pregunta de investigación del estudio actual.
OBJETIVOS DE LA INVESTIGACIÓN
Determinar los factores de la deserción universitaria observada.
CAPÍTULO III: MARCO METODOLÓGICO
Diseño cuantitativo con una muestra de 200 estudiantes seleccionados al azar.
4. PRESENTACIÓN Y ANÁLISIS DE RESULTADOS
El factor económico explica el 40.5 por ciento de la varianza observada.
V. CONCLUSIONES Y RECOMENDACIONES
La deserción se relaciona con factores económicos según los datos analizados.
REFERENCIAS BIBLIOGRÁFICAS
García, J. (2020). Deserción universitaria. Revista de Educación.
"""


def test_particionar_encabezados_reales() -> None:
    """Encabezados de tesis reales: CAPÍTULO, numerales romanos, títulos descriptivos."""
    secciones = particionar(_TESIS_REAL)
    for esperada in SECCIONES_ESPERADAS:
        assert esperada in secciones, esperada


def test_prosa_no_se_confunde_con_encabezado() -> None:
    """Una línea de prosa (aunque mencione una palabra clave) NO debe partir sección."""
    assert _seccion_de_encabezado("Los objetivos se cumplieron de forma parcial este año.") is None
    assert _seccion_de_encabezado("En conclusión, el método resultó efectivo para el caso.") is None


def test_trozos_respeta_limite() -> None:
    texto = "palabra " * 5000
    partes = trozos(texto, max_bytes=1000)
    assert len(partes) > 1
    assert all(len(p.encode("utf-8")) <= 1000 for p in partes)


def test_features_fallback_sin_aws() -> None:
    # Clientes AWS = None -> fallback local (sin red).
    features = DocumentoFeatures(None, None).calcular(_TESIS)
    assert set(features) == {
        "coherencia_objetivos_resultados",
        "cohesion_secciones",
        "completitud_estructural",
        "formalidad_redaccion",
        "claridad_problema",
        "densidad_referencias",
    }
    assert all(0.0 <= v <= 1.0 for v in features.values())
    assert features["completitud_estructural"] == 1.0  # están las 5 secciones
