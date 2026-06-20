"""Selección de adaptadores de integración según configuración/entorno.

Se inyectan en los services con `Depends(...)` y se sustituyen en tests con
`app.dependency_overrides`.
"""

from functools import lru_cache

from app.core.config import settings
from app.integrations.analysis.port import AnalysisQueuePort, AnalysisServicePort
from app.integrations.analysis.stub import StubAnalysisQueue, StubAnalysisService
from app.integrations.biometric.port import BiometricServicePort
from app.integrations.biometric.stub import StubBiometricService
from app.integrations.email.console import ConsoleEmail
from app.integrations.email.port import EmailPort
from app.integrations.evaluador.local import LocalEvaluadorService
from app.integrations.evaluador.port import EvaluadorServicePort
from app.integrations.llm.port import TribunalLLMPort
from app.integrations.llm.stub import StubTribunalLLM
from app.integrations.payments.port import PaymentGatewayPort
from app.integrations.payments.stripe_gateway import StripeGateway
from app.integrations.storage.local import LocalStorage
from app.integrations.storage.port import StoragePort


@lru_cache
def get_email_port() -> EmailPort:
    # En producción se conectará el adaptador SES (settings.email_backend == "ses").
    return ConsoleEmail()


@lru_cache
def get_storage_port() -> StoragePort:
    # En producción se conectará el adaptador S3 (settings.storage_backend == "s3").
    return LocalStorage()


@lru_cache
def get_payment_gateway() -> PaymentGatewayPort:
    return StripeGateway()


@lru_cache
def get_analysis_queue() -> AnalysisQueuePort:
    # En producción se conectará el adaptador SQS (settings).
    return StubAnalysisQueue()


@lru_cache
def get_analysis_service() -> AnalysisServicePort:
    # "aws": extractor real (Comprehend + Titan) que alimenta la IA evaluadora propia.
    if settings.analysis_backend == "aws":
        from app.integrations.analysis.aws import AwsAnalysisService

        return AwsAnalysisService()
    return StubAnalysisService()


@lru_cache
def get_tribunal_llm() -> TribunalLLMPort:
    # En producción se conectará el adaptador real del LLM (settings.tribunal_llm_backend).
    return StubTribunalLLM()


@lru_cache
def get_biometric_service() -> BiometricServicePort:
    # "aws": Rekognition (detect_faces por frame) para postura + contacto visual reales.
    if settings.biometric_backend == "aws":
        from app.integrations.biometric.aws import AwsBiometricService

        return AwsBiometricService()
    return StubBiometricService()


@lru_cache
def get_evaluador_service() -> EvaluadorServicePort:
    # IA evaluadora propia EN PROCESO: carga el modelo .pkl y predice dentro del backend.
    return LocalEvaluadorService()
