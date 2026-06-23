"""Modelos ORM del submódulo Documentos (CU-08, CU-09, CU-11)."""

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import EstadoAnalisis, EstadoEticaTesis, FormatoDocumento
from app.models.base import Base, CreatedAtMixin, IdMixin, TimestampMixin


class Documento(Base, IdMixin, TimestampMixin):
    __tablename__ = "documento"

    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuario.id"), index=True)
    titulo: Mapped[str] = mapped_column(String(255))
    # CU-12: estado ético de la tesis; lo actualiza el sistema al abrir/resolver alertas.
    estado_etico: Mapped[EstadoEticaTesis] = mapped_column(
        SAEnum(EstadoEticaTesis, name="estado_etica_tesis"),
        default=EstadoEticaTesis.LIMPIO,
        server_default=EstadoEticaTesis.LIMPIO.value,
    )


class VersionDocumento(Base, IdMixin, CreatedAtMixin):
    __tablename__ = "version_documento"

    documento_id: Mapped[int] = mapped_column(ForeignKey("documento.id"), index=True)
    numero_version: Mapped[int] = mapped_column(Integer)
    archivo_url: Mapped[str] = mapped_column(String(500))
    formato: Mapped[FormatoDocumento] = mapped_column(
        SAEnum(FormatoDocumento, name="formato_documento")
    )
    estado_analisis: Mapped[EstadoAnalisis] = mapped_column(
        SAEnum(EstadoAnalisis, name="estado_analisis")
    )
