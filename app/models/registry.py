"""Importa todos los modelos para registrarlos en `Base.metadata`.

Lo importan Alembic (`alembic/env.py`) y los tests. Vive aparte del `__init__`
del paquete para no provocar imports circulares con `app.models.base`.
"""

from app.core.audit.models import Bitacora
from app.modules.administracion.monitoreo.models import AvanceFormal
from app.modules.administracion.notificaciones.models import NotificacionUsuario
from app.modules.administracion.pagos.models import EventoWebhook, Pago
from app.modules.administracion.suscripciones.models import PlanSuscripcion, Suscripcion
from app.modules.administracion.usuarios.models import TokenResetPassword, Usuario
from app.modules.auditoria_documental.auditoria.models import Observacion, ResultadoAuditoria
from app.modules.auditoria_documental.documentos.models import Documento, VersionDocumento
from app.modules.auditoria_documental.etica.models import AlertaEtica
from app.modules.simulador.biometrico.models import MetricaBiometrica
from app.modules.simulador.simulaciones.models import SesionSimulacion
from app.modules.simulador.tribunal.models import (
    EvaluacionRespuesta,
    PreguntaTribunal,
    RespuestaEstudiante,
    ResultadoSimulacion,
)

__all__ = [
    "AlertaEtica",
    "AvanceFormal",
    "Bitacora",
    "Documento",
    "EvaluacionRespuesta",
    "EventoWebhook",
    "MetricaBiometrica",
    "NotificacionUsuario",
    "Observacion",
    "Pago",
    "PlanSuscripcion",
    "PreguntaTribunal",
    "RespuestaEstudiante",
    "ResultadoAuditoria",
    "ResultadoSimulacion",
    "SesionSimulacion",
    "Suscripcion",
    "TokenResetPassword",
    "Usuario",
    "VersionDocumento",
]
