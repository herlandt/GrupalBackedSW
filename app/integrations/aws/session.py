"""Proveedor de sesión boto3: única forma de obtener clientes de AWS.

Usa el perfil de AWS CLI configurado (por defecto `default`). Los puertos y
adaptadores concretos (S3, SES, SQS...) se añadirán cuando exista un caso de uso
que los consuma (Ciclo 2+), respetando YAGNI.
"""

import os
from functools import lru_cache
from typing import Any

import boto3
from botocore.config import Config

from app.core.config import settings

# Reintentos ADAPTATIVOS ante throttling (Bedrock/Comprehend/Textract aplican cuotas
# agresivas) + TIMEOUTS de cliente para que una llamada atascada no bloquee indefinidamente
# (tope duro dentro del hilo, complementa al fail_after del cierre de sesión).
_RETRY_CONFIG = Config(
    retries={"max_attempts": 4, "mode": "adaptive"},
    connect_timeout=5,
    read_timeout=20,
)


@lru_cache
def get_boto_session() -> boto3.Session:
    """Devuelve una sesión boto3 reutilizable según la configuración de AWS.

    Si hay un perfil configurado, usa las credenciales de `~/.aws`; si no, recurre
    a la cadena de credenciales por defecto (variables de entorno, rol IAM, etc.).
    """
    if settings.aws_profile:
        return boto3.Session(
            profile_name=settings.aws_profile,
            region_name=settings.aws_region,
        )
    # Sin perfil (producción: rol IAM de la instancia). OJO: si el entorno trae un
    # AWS_PROFILE VACÍO (`AWS_PROFILE=`), boto3 lo tomaría como el perfil "" y fallaría con
    # ProfileNotFound. Lo quitamos para usar la cadena de credenciales por defecto (rol EC2).
    os.environ.pop("AWS_PROFILE", None)
    return boto3.Session(region_name=settings.aws_region)


@lru_cache
def get_aws_client(service_name: str) -> Any:
    """Cliente boto3 CACHEADO (uno por servicio) con reintentos adaptativos.

    Crear un cliente boto3 es caro (parseo del modelo del servicio); el WS de video
    analiza un frame cada pocos segundos, así que reutilizar el cliente de Rekognition
    evita recrearlo en cada frame. Los clientes boto3 son seguros para invocar desde
    varios hilos (`anyio.to_thread`), por lo que se pueden compartir.
    """
    # boto3-stubs tipa `.client` con overloads por nombre Literal; aquí es genérico aposta
    # (un único helper para todos los servicios), por eso el overload no encaja.
    return get_boto_session().client(service_name, config=_RETRY_CONFIG)  # type: ignore[call-overload]
