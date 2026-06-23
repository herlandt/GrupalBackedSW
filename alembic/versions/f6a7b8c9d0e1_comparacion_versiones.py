"""comparación entre versiones del documento (CU-09 / RF-09)

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-06-22 13:00:00.000000

Añade `resultado_auditoria.comparacion` (JSONB): tendencia y deltas de features respecto a
la versión anterior, generados por el worker de análisis al reanalizar una nueva versión.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "f6a7b8c9d0e1"
down_revision: str | None = "e5f6a7b8c9d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "resultado_auditoria",
        sa.Column("comparacion", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("resultado_auditoria", "comparacion")
