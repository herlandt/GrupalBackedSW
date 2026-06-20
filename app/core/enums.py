"""Enumeraciones del dominio (compartidas por los modelos ORM).

Se definen como `StrEnum` (el valor coincide con el nombre) y se usan en los
modelos vía `mapped_column(SAEnum(MiEnum, name="mi_enum"))`, donde `name` es el
nombre del tipo ENUM en PostgreSQL.
"""

from enum import StrEnum


class RolUsuario(StrEnum):
    ESTUDIANTE = "ESTUDIANTE"
    ADMINISTRADOR = "ADMINISTRADOR"


class EstadoSuscripcion(StrEnum):
    PENDIENTE = "PENDIENTE"
    ACTIVA = "ACTIVA"
    EXPIRADA = "EXPIRADA"
    CANCELADA = "CANCELADA"


class EstadoPago(StrEnum):
    PENDIENTE = "PENDIENTE"
    PAGADO = "PAGADO"
    FALLIDO = "FALLIDO"
    REEMBOLSADO = "REEMBOLSADO"


class FormatoDocumento(StrEnum):
    DOCX = "DOCX"
    PDF = "PDF"


class EstadoAnalisis(StrEnum):
    PENDIENTE = "PENDIENTE"
    EN_PROCESO = "EN_PROCESO"
    COMPLETADO = "COMPLETADO"
    ERROR = "ERROR"


class NivelPreparacion(StrEnum):
    ALTO = "ALTO"
    MEDIO = "MEDIO"
    BAJO = "BAJO"


class CategoriaObservacion(StrEnum):
    COHERENCIA = "COHERENCIA"
    NORMAS = "NORMAS"
    SUGERENCIA = "SUGERENCIA"


class EstadoAlertaEtica(StrEnum):
    PENDIENTE = "PENDIENTE"
    EN_REVISION = "EN_REVISION"
    CONFIRMADA = "CONFIRMADA"
    DESESTIMADA = "DESESTIMADA"


class NivelDificultad(StrEnum):
    EXPLORACION = "EXPLORACION"
    ESTANDAR = "ESTANDAR"
    RIGUROSO = "RIGUROSO"


class EstadoSesion(StrEnum):
    EN_CURSO = "EN_CURSO"
    FINALIZADA = "FINALIZADA"
    CANCELADA = "CANCELADA"


class EstadoAvance(StrEnum):
    PENDIENTE = "PENDIENTE"
    APROBADO = "APROBADO"
    RECHAZADO = "RECHAZADO"
