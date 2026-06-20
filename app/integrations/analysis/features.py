"""Cálculo de las 6 features de la dimensión 'documento' a partir del texto.

Usa AWS **Comprehend** (frases clave) y **Titan Embeddings** (coherencia) cuando están
disponibles, con *fallback* local si no. NO decide el nivel: solo produce las features
que consume la IA evaluadora propia (`predictor.predecir`). Los EXTRACTORES miden; la
evaluadora decide.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from typing import Any

import numpy as np
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from app.core.config import settings
from app.integrations.analysis.extraction import SECCIONES_ESPERADAS, particionar, trozos

_CITA = re.compile(
    r"\([^)]*\b\d{4}[a-z]?\)"  # paréntesis con un año: (Autor, 2020), (X & Y, 2019)
    r"|\b[A-ZÁÉÍÓÚ][\wáéíóúñ'-]+\s+\(\d{4}[a-z]?\)"  # narrativa: García (2020)
    r"|\[\d+(?:[-,]\s?\d+)*\]"  # IEEE: [1], [1-3], [1, 2]
)
_PROBLEMA = ("problema", "pregunta de investigaci", "hipotesis", "hipótesis", "justificaci")


def _coseno(a: list[float], b: list[float]) -> float:
    va, vb = np.array(a), np.array(b)
    norma = float(np.linalg.norm(va) * np.linalg.norm(vb))
    return float(np.dot(va, vb) / norma) if norma else 0.0


def _cos_lexico(a: str, b: str) -> float:
    """Similitud léxica por coseno de vectores de conteo: mejor que Jaccard porque pondera
    por frecuencia y no colapsa a ~0 entre secciones con vocabulario distinto pero afín."""
    if not a.strip() or not b.strip():
        return 0.0
    try:
        m = CountVectorizer().fit_transform([a, b])
    except ValueError:  # sin vocabulario útil (solo símbolos/stopwords)
        return 0.0
    return float(cosine_similarity(m[0], m[1])[0][0])


class DocumentoFeatures:
    """Calcula las 6 features 'documento' usando clientes AWS (best-effort, con fallback)."""

    def __init__(self, comprehend: Any, bedrock: Any) -> None:
        self.comprehend = comprehend
        self.bedrock = bedrock
        self._cache_embed: dict[str, list[float] | None] = {}

    def _embed(self, texto: str) -> list[float] | None:
        """Embedding de Titan (Bedrock), CACHEADO por texto: cada sección se embebe una sola
        vez → menos llamadas y menos throttling. None si Bedrock no está disponible."""
        limpio = texto.strip()
        if not limpio:
            return None
        # Clave = hash del texto COMPLETO (no un prefijo de 8000 car.): dos secciones que
        # compartan el inicio no deben devolver el embedding equivocado. A Titan se le manda
        # el texto truncado (su límite de tokens), pero la caché distingue por contenido real.
        clave = hashlib.sha256(limpio.encode("utf-8")).hexdigest()
        if clave in self._cache_embed:
            return self._cache_embed[clave]
        emb: list[float] | None = None
        if self.bedrock is not None:
            try:
                resp = self.bedrock.invoke_model(
                    modelId=settings.bedrock_embeddings_model,
                    body=json.dumps({"inputText": limpio[:8000]}),
                )
                emb = list(json.loads(resp["body"].read())["embedding"])
            except Exception:  # Bedrock no habilitado / throttling / red -> fallback léxico
                emb = None
        self._cache_embed[clave] = emb
        return emb

    def _similitud(self, a: str, b: str) -> float:
        ea, eb = self._embed(a), self._embed(b)
        if ea is not None and eb is not None:
            return max(0.0, _coseno(ea, eb))
        return _cos_lexico(a, b)

    def _frases_clave(self, texto: str) -> int:
        if self.comprehend is None:
            return len(texto.split()) // 20
        total = 0
        for trozo in trozos(texto)[:4]:  # tope para no gastar de más
            try:
                r = self.comprehend.detect_key_phrases(Text=trozo, LanguageCode="es")
                total += len(r["KeyPhrases"])
            except Exception:
                total += len(trozo.split()) // 20
        return total

    def temas_clave(self, texto: str, n: int = 6) -> list[str]:
        """Frases clave más frecuentes (Comprehend) para el feedback de 'temas detectados'."""
        if self.comprehend is None:
            return []
        conteo: Counter[str] = Counter()
        for trozo in trozos(texto)[:4]:
            try:
                r = self.comprehend.detect_key_phrases(Text=trozo, LanguageCode="es")
            except Exception:
                continue
            for kp in r["KeyPhrases"]:
                tema = kp["Text"].strip().lower()
                if len(tema) > 3:
                    conteo[tema] += 1
        return [tema for tema, _ in conteo.most_common(n)]

    def calcular(self, texto: str) -> dict[str, float]:
        secciones = particionar(texto)
        presentes = [s for s in SECCIONES_ESPERADAS if s in secciones]

        objetivos = secciones.get("objetivos", "")
        cierre = " ".join(
            t for t in (secciones.get("resultados", ""), secciones.get("conclusiones", "")) if t
        )
        coherencia = self._similitud(objetivos, cierre) if objetivos and cierre else 0.5

        textos = [secciones[s] for s in SECCIONES_ESPERADAS if s in secciones]
        pares = [self._similitud(textos[i], textos[i + 1]) for i in range(len(textos) - 1)]
        cohesion = sum(pares) / len(pares) if pares else 0.5

        completitud = len(presentes) / len(SECCIONES_ESPERADAS)

        palabras = texto.split()
        # Cuenta fin de oración ignorando decimales (5.8) e iniciales/siglas (U.N.A.M., A.).
        # NO exige mayúscula después: el texto de PDF suele traer saltos de línea, no espacios.
        n_oraciones = len(re.findall(r"(?<!\d)(?<![A-ZÁÉÍÓÚ])[.!?]+", texto))
        long_media = len(palabras) / n_oraciones if n_oraciones else 0.0
        formalidad = max(0.0, 1.0 - abs(long_media - 22.0) / 22.0)  # ~22 palabras/oración ideal

        intro = f"{secciones.get('introduccion', '')} {secciones.get('problema', '')}"
        tiene_problema = any(p in intro.lower() for p in _PROBLEMA)
        claridad = min(
            1.0, 0.4 + (0.3 if tiene_problema else 0.0) + min(self._frases_clave(intro), 10) / 50
        )

        n_citas = len(_CITA.findall(texto))
        tiene_refs = "referencias" in secciones
        densidad = min(
            1.0, (n_citas / max(len(palabras) / 200.0, 1.0)) * 0.5 + (0.3 if tiene_refs else 0.0)
        )

        return {
            "coherencia_objetivos_resultados": round(coherencia, 3),
            "cohesion_secciones": round(cohesion, 3),
            "completitud_estructural": round(completitud, 3),
            "formalidad_redaccion": round(formalidad, 3),
            "claridad_problema": round(claridad, 3),
            "densidad_referencias": round(densidad, 3),
        }
