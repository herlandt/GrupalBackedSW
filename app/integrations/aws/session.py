"""Proveedor de sesión boto3: única forma de obtener clientes de AWS.

Usa el perfil de AWS CLI configurado (por defecto `default`). Los puertos y
adaptadores concretos (S3, SES, SQS...) se añadirán cuando exista un caso de uso
que los consuma (Ciclo 2+), respetando YAGNI.
"""

from functools import lru_cache

import boto3

from app.core.config import settings


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
    return boto3.Session(region_name=settings.aws_region)
