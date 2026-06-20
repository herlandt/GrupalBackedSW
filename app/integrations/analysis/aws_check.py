"""Prueba REAL del extractor AWS: corre Comprehend (+ Titan si esta habilitado) sobre un
texto de ejemplo y muestra las 6 features y el nivel que DECIDE la IA evaluadora propia.
Ejecutar (venv del backend):  python -m app.integrations.analysis.aws_check
"""

from app.integrations.analysis.features import DocumentoFeatures
from app.integrations.aws.session import get_boto_session
from app.ml import predictor

TESIS = """Introduccion
Este trabajo aborda el problema de la desercion estudiantil en la universidad, una
pregunta de investigacion relevante para la retencion academica.
Objetivos
Determinar los factores asociados a la desercion estudiantil de primer ano.
Metodologia
Se aplico un diseno cuantitativo correlacional con una muestra de 200 estudiantes y
encuestas validadas para garantizar la confiabilidad de los instrumentos.
Resultados
Los resultados muestran que el factor economico explica el 40 por ciento de la desercion
y se relaciona con el rendimiento academico del estudiante.
Conclusiones
Se concluye que la desercion estudiantil se relaciona con factores economicos y
academicos, en linea con los objetivos planteados.
Referencias
(Garcia, 2020) (Lopez, 2019) [1] [2]
"""


def main() -> None:
    session = get_boto_session()
    extractor = DocumentoFeatures(
        session.client("comprehend"), session.client("bedrock-runtime")
    )
    features = extractor.calcular(TESIS)
    print("Features (AWS Comprehend/Titan + reglas):")
    for nombre, valor in features.items():
        print(f"  {valor:.3f}  {nombre}")

    juicio = predictor.predecir("documento", features)
    print(f"\nNivel que DECIDE tu RandomForest: {juicio['nivel']} (conf {juicio['confianza']})")
    print("A reforzar:", ", ".join(juicio["factores_a_reforzar"]))


if __name__ == "__main__":
    main()
