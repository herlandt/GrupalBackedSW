"""Excepciones propias del dominio.

Los services lanzan estas excepciones (que no saben nada de HTTP).
La capa de API las traduce a respuestas HTTP en main.py.
"""


class DomainError(Exception):
    """Base de los errores de negocio."""


class ResourceNotFoundError(DomainError):
    """Un recurso solicitado no existe."""


class BusinessRuleError(DomainError):
    """Se violó una regla de negocio."""


class AuthenticationError(DomainError):
    """Falló la autenticación (credenciales inválidas). La API la traduce a 401."""
