"""Verificación rápida de conectividad con AWS usando el perfil del AWS CLI.

Prueba que el backend (corriendo en local) puede consumir AWS con tus credenciales de
`~/.aws`, SIN llaves en el código. Hace llamadas reales (baratas) a STS y Comprehend.
Ejecutar (venv del backend, desde la raíz):  ``python -m app.integrations.aws.check``
"""

from typing import Any

from app.core.config import settings
from app.integrations.aws.session import get_boto_session

TEXTO = (
    "Esta investigación analiza la coherencia metodológica entre los objetivos, la "
    "metodología y las conclusiones de un trabajo de grado de ingeniería de software."
)


def main() -> None:
    session = get_boto_session()
    print(f"Perfil: {settings.aws_profile} | region: {settings.aws_region}")

    sts: Any = session.client("sts")
    print("Cuenta AWS:", sts.get_caller_identity()["Account"])

    comp: Any = session.client("comprehend")
    idioma = comp.detect_dominant_language(Text=TEXTO)["Languages"][0]
    print(f"Comprehend - idioma dominante: {idioma['LanguageCode']} ({idioma['Score']:.2f})")
    frases = comp.detect_key_phrases(Text=TEXTO, LanguageCode="es")["KeyPhrases"]
    print(f"Comprehend - {len(frases)} frases clave:", [f["Text"] for f in frases[:5]])

    print("\nOK: el backend local consume AWS correctamente con tu perfil.")


if __name__ == "__main__":
    main()
