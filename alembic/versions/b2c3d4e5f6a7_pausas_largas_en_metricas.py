"""pausas largas medidas en metrica_biometrica (RF-05)

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-06-16 03:30:00.000000

Añade metrica_biometrica.pausas_largas_conteo: nº de pausas largas medidas desde el
timing de AWS Transcribe en ese segmento de audio (0 en filas de video). Alimenta la
feature `pausas_largas_por_min` de la IA evaluadora, que antes era un valor neutro.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b2c3d4e5f6a7"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "metrica_biometrica",
        sa.Column("pausas_largas_conteo", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("metrica_biometrica", "pausas_largas_conteo")
