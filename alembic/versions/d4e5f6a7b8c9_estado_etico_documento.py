"""estado ético de la tesis (CU-12)

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-06-22 12:00:00.000000

Añade `documento.estado_etico` (LIMPIO|EN_REVISION|OBSERVADA). El sistema lo actualiza al
abrir una alerta de ética (EN_REVISION) y al resolverla el administrador (OBSERVADA si la
confirma, LIMPIO si la desestima), cumpliendo la postcondición del CU-12.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d4e5f6a7b8c9"
down_revision: str | None = "c3d4e5f6a7b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    estado = sa.Enum("LIMPIO", "EN_REVISION", "OBSERVADA", name="estado_etica_tesis")
    estado.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "documento",
        sa.Column("estado_etico", estado, nullable=False, server_default="LIMPIO"),
    )


def downgrade() -> None:
    op.drop_column("documento", "estado_etico")
    sa.Enum(name="estado_etica_tesis").drop(op.get_bind(), checkfirst=True)
