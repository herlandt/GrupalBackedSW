"""Adaptador stub del LLM del tribunal para desarrollo/test.

Devuelve preguntas y evaluaciones de ejemplo deterministas, sin llamar a un LLM real.
El adaptador real (OpenAI/Anthropic/Bedrock o microservicio interno) se conecta por entorno.
"""

from app.integrations.llm.port import (
    EvaluacionDTO,
    PreguntaGeneradaDTO,
    TribunalLLMPort,
)

_PLANTILLA = {
    "EXPLORACION": [
        "¿Cuál es el objetivo general de tu investigación?",
        "Describe brevemente la metodología que empleaste.",
        "¿Qué resultados principales obtuviste?",
    ],
    "ESTANDAR": [
        "Justifica la elección de tu diseño metodológico frente a alternativas.",
        "¿Cómo garantizaste la validez y confiabilidad de tus instrumentos?",
        "Relaciona tus resultados con el marco teórico que planteaste.",
        "¿Qué limitaciones reconoces en tu estudio?",
    ],
    "RIGUROSO": [
        "Defiende la consistencia interna entre tu pregunta, objetivos e hipótesis.",
        "¿Qué amenazas a la validez interna y externa identificas y cómo las controlaste?",
        "Cuestiona críticamente la representatividad de tu muestra.",
        "¿Cómo dialogan tus hallazgos con la literatura más reciente del campo?",
        "Si repitieras el estudio, ¿qué cambiarías metodológicamente y por qué?",
    ],
}


class StubTribunalLLM(TribunalLLMPort):
    async def generar_preguntas(
        self, *, archivo_url: str, formato: str, nivel_dificultad: str
    ) -> list[PreguntaGeneradaDTO]:
        textos = _PLANTILLA.get(nivel_dificultad, _PLANTILLA["ESTANDAR"])
        return [
            PreguntaGeneradaDTO(orden=i, texto=texto) for i, texto in enumerate(textos, start=1)
        ]

    async def evaluar_respuesta(self, *, pregunta: str, respuesta: str) -> EvaluacionDTO:
        # Heurística trivial de ejemplo: respuestas más largas puntúan algo más.
        longitud = len(respuesta.strip())
        if longitud == 0:
            return EvaluacionDTO(
                puntuacion=0.0,
                observaciones="No se registró contenido en la respuesta.",
                profundidad="baja",
            )
        puntuacion = min(10.0, 4.0 + longitud / 50.0)
        profundidad = "alta" if longitud > 300 else "media" if longitud > 120 else "baja"
        return EvaluacionDTO(
            puntuacion=round(puntuacion, 2),
            observaciones=(
                "Respuesta de ejemplo: cubre la idea principal; "
                "refuerza la precisión conceptual y aporta evidencia metodológica."
            ),
            profundidad=profundidad,
        )
