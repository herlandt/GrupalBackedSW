"""Lógica de negocio — submódulo integracion (CU-14, dimensión defensa).

Cierra la sesión: agrega métricas (Fase 3) + evaluaciones (Fase 2), pide el nivel de
defensa a la IA evaluadora propia y persiste el `ResultadoSimulacion`.
"""

from collections.abc import Sequence
from dataclasses import asdict
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit.service import AuditService
from app.core.enums import EstadoSesion, NivelPreparacion
from app.core.exceptions import BusinessRuleError, ResourceNotFoundError
from app.integrations.evaluador.port import (
    DefensaFeatures,
    EvaluadorServiceError,
    EvaluadorServicePort,
)
from app.ml import rubrica
from app.modules.administracion.usuarios.models import Usuario
from app.modules.simulador.biometrico.models import MetricaBiometrica
from app.modules.simulador.biometrico.repository import MetricaBiometricaRepository
from app.modules.simulador.integracion.repository import (
    EvaluacionRespuestaRepository,
    ResultadoSimulacionRepository,
)
from app.modules.simulador.simulaciones.models import SesionSimulacion
from app.modules.simulador.simulaciones.repository import SesionSimulacionRepository
from app.modules.simulador.tribunal.models import EvaluacionRespuesta, ResultadoSimulacion

# Ritmo ideal de exposición (palabras/min). Neutro si no hay datos de la sesión.
_RITMO_IDEAL = 130.0


def _now() -> datetime:
    """Instante actual en UTC, sin zona (las columnas son TIMESTAMP naive)."""
    return datetime.now(UTC).replace(tzinfo=None)


def _media(valores: list[float]) -> float | None:
    return sum(valores) / len(valores) if valores else None


def _neutro(nombre: str) -> float:
    """Valor a imputar cuando falta una señal: media del nivel MEDIO de la rúbrica.

    Evita el sesgo de tratar la ausencia de datos como "perfecto" (muletillas/pausas=0)
    o "pésimo" (contacto/postura=0): un dato que no se midió debe ser NEUTRO.
    """
    return float(rubrica.DEFENSA[nombre].dist["MEDIO"][0])


class IntegracionService:
    def __init__(self, db: AsyncSession, evaluador: EvaluadorServicePort) -> None:
        self.db = db
        self.resultados = ResultadoSimulacionRepository(db)
        self.metricas = MetricaBiometricaRepository(db)
        self.evaluaciones = EvaluacionRespuestaRepository(db)
        self.sesiones = SesionSimulacionRepository(db)
        self.audit = AuditService(db)
        self.evaluador = evaluador

    # --- Helpers (IDOR) -------------------------------------------------
    async def _sesion_del_usuario(self, sesion_id: int, usuario: Usuario) -> SesionSimulacion:
        sesion = await self.sesiones.get_de_usuario(sesion_id, usuario.id)
        if sesion is None:
            # No revelar sesiones ajenas: se tratan como inexistentes (404).
            raise ResourceNotFoundError(f"Sesión {sesion_id} no existe")
        return sesion

    # --- Mapeo a las 6 features de la dimensión `defensa` ---------------
    def _features_defensa(
        self, sesion: SesionSimulacion, metricas: Sequence[MetricaBiometrica]
    ) -> DefensaFeatures:
        contactos = [
            float(m.contacto_visual_pct) for m in metricas if m.contacto_visual_pct is not None
        ]
        posturas = [float(m.postura_score) for m in metricas if m.postura_score is not None]
        ritmos = [float(m.ritmo_wpm) for m in metricas if m.ritmo_wpm is not None]
        total_muletillas = sum(m.muletillas_conteo for m in metricas)
        hay_voz = bool(ritmos) or total_muletillas > 0

        # Duración real de la sesión en minutos (mínimo 1 para no dividir por 0).
        fin = sesion.fecha_fin or _now()
        minutos = max((fin - sesion.fecha_inicio).total_seconds() / 60.0, 1.0)

        # Video: si no hubo medición, NEUTRO (antes faltar daba contacto=0 = "pésimo").
        contacto_avg = _media(contactos)
        contacto = contacto_avg / 100.0 if contacto_avg is not None else _neutro("contacto_visual")
        postura_avg = _media(posturas)
        postura = postura_avg / 100.0 if postura_avg is not None else _neutro("estabilidad_postura")

        # Voz: si no se captó, las features de habla van NEUTRAS (antes faltar daba
        # muletillas=0/ritmo=ideal = "perfecto", lo que INFLABA el veredicto).
        if hay_voz:
            ritmo_avg = _media(ritmos)
            ritmo = ritmo_avg if ritmo_avg is not None else _neutro("ritmo_ppm")
            muletillas_min = total_muletillas / minutos
            # Pausas largas REALES (Transcribe): total medido / minutos de defensa.
            pausas_min = sum(m.pausas_largas_conteo for m in metricas) / minutos
            cercania = max(0.0, 1.0 - abs(ritmo - _RITMO_IDEAL) / _RITMO_IDEAL)
            fluidez = max(0.0, min(1.0, cercania - 0.05 * muletillas_min))
        else:
            ritmo = _neutro("ritmo_ppm")
            muletillas_min = _neutro("muletillas_por_min")
            pausas_min = _neutro("pausas_largas_por_min")
            fluidez = _neutro("fluidez")

        return DefensaFeatures(
            fluidez=round(fluidez, 3),
            contacto_visual=round(contacto, 3),
            estabilidad_postura=round(postura, 3),
            muletillas_por_min=round(muletillas_min, 2),
            ritmo_ppm=round(ritmo, 1),
            pausas_largas_por_min=round(pausas_min, 2),
        )

    @staticmethod
    def _dominio_score(evaluaciones: Sequence[EvaluacionRespuesta]) -> Decimal | None:
        """Media de las puntuaciones de respuestas (RF-07). Informa, no decide el nivel."""
        if not evaluaciones:
            return None
        media = sum(float(e.puntuacion) for e in evaluaciones) / len(evaluaciones)
        return Decimal(str(round(media, 2)))

    # --- CU-14: cierre de la sesión y resultado -------------------------
    async def generar_resultado(self, sesion_id: int, usuario: Usuario) -> ResultadoSimulacion:
        """Agrega señales, pide el nivel a la IA evaluadora y persiste el resultado.

        Idempotente: una sesión solo puede tener un resultado (409 si ya existe).
        """
        sesion = await self._sesion_del_usuario(sesion_id, usuario)
        if sesion.estado is EstadoSesion.CANCELADA:
            raise BusinessRuleError("La sesión fue cancelada; no se puede evaluar.")
        # Idempotente: si la sesión ya tiene resultado, lo devolvemos en vez de fallar.
        existente = await self.resultados.por_sesion(sesion_id)
        if existente is not None:
            return existente

        metricas = await self.metricas.por_sesion(sesion_id)
        evaluaciones = await self.evaluaciones.por_sesion(sesion_id)

        features = self._features_defensa(sesion, metricas)
        try:
            evaluacion = await self.evaluador.evaluar_defensa(features)
        except EvaluadorServiceError as exc:
            raise BusinessRuleError(
                "La IA evaluadora no está disponible; intenta de nuevo más tarde."
            ) from exc

        oratoria = Decimal(str(round(features.fluidez * 100, 2)))
        no_verbal = Decimal(
            str(round((features.contacto_visual + features.estabilidad_postura) / 2 * 100, 2))
        )
        # Feedback ACCIONABLE: traduce los factores débiles a consejos con valor + objetivo.
        mejoras = rubrica.consejos("defensa", evaluacion.factores_a_reforzar, asdict(features))
        texto_mejora = "; ".join(mejoras) or "—"
        # Honestidad: si no se captó voz, el veredicto se apoya casi solo en lo visual.
        sin_voz = not any(m.ritmo_wpm is not None for m in metricas) and (
            sum(m.muletillas_conteo for m in metricas) == 0
        )
        nota_voz = (
            " (datos de voz limitados: el veredicto se apoya sobre todo en el lenguaje corporal)"
            if sin_voz
            else ""
        )
        # Abstención honesta: si el caso es de frontera (confianza/margen bajos), se avisa
        # en vez de sentenciar un nivel dudoso.
        nota_revision = (
            " ⚠️ Caso límite (confianza baja): conviene una revisión humana del nivel."
            if evaluacion.revision_sugerida
            else ""
        )

        resultado = ResultadoSimulacion(
            sesion_id=sesion.id,
            nivel_defensa=NivelPreparacion(evaluacion.nivel),
            oratoria_score=oratoria,
            comunicacion_no_verbal_score=no_verbal,
            dominio_score=self._dominio_score(evaluaciones),
            resumen=(
                f"Nivel de defensa: {evaluacion.nivel}. Para mejorar: {texto_mejora}."
                f"{nota_voz}{nota_revision}"
            ),
            confianza=Decimal(str(round(evaluacion.confianza, 3))),
            features=asdict(features),
        )
        await self.resultados.add(resultado)  # flush -> resultado.id

        # Cierra la sesión (si no se había cerrado ya con /finalizar).
        sesion.estado = EstadoSesion.FINALIZADA
        sesion.fecha_fin = sesion.fecha_fin or _now()
        await self.db.flush()

        await self.audit.log(
            actor_id=usuario.id,
            accion="SIMULACION_RESULTADO_GENERADO",
            entidad="resultado_simulacion",
            entidad_id=resultado.id,
            metadata={"sesion_id": sesion.id, "nivel_defensa": resultado.nivel_defensa.value},
        )
        return resultado

    async def obtener_resultado(self, sesion_id: int, usuario: Usuario) -> ResultadoSimulacion:
        await self._sesion_del_usuario(sesion_id, usuario)
        resultado = await self.resultados.por_sesion(sesion_id)
        if resultado is None:
            raise ResourceNotFoundError("Aún no hay resultado para esta sesión.")
        return resultado
