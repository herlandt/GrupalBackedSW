"""persistir features de la IA + indice compuesto de metricas

Revision ID: a1b2c3d4e5f6
Revises: 7f43134b7e86
Create Date: 2026-06-15 14:30:00.000000

Añade:
- resultado_auditoria.features (JSONB) y resultado_simulacion.features/confianza:
  guardan el vector que alimentó a la IA evaluadora (trazabilidad + futuro reentrenamiento).
- índice compuesto metrica_biometrica(sesion_id, momento), que reemplaza al índice
  simple de la FK: las lecturas filtran por sesión y ordenan por momento, y con el
  análisis continuo cada sesión acumula muchas filas.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "7f43134b7e86"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "resultado_auditoria",
        sa.Column("features", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "resultado_simulacion",
        sa.Column("features", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "resultado_simulacion",
        sa.Column("confianza", sa.Numeric(precision=4, scale=3), nullable=True),
    )
    # Reemplaza el índice simple de la FK por uno compuesto (filtro + orden).
    op.drop_index("ix_metrica_biometrica_sesion_id", table_name="metrica_biometrica")
    op.create_index(
        "ix_metrica_biometrica_sesion_momento",
        "metrica_biometrica",
        ["sesion_id", "momento"],
    )


def downgrade() -> None:
    op.drop_index("ix_metrica_biometrica_sesion_momento", table_name="metrica_biometrica")
    op.create_index(
        "ix_metrica_biometrica_sesion_id", "metrica_biometrica", ["sesion_id"]
    )
    op.drop_column("resultado_simulacion", "confianza")
    op.drop_column("resultado_simulacion", "features")
    op.drop_column("resultado_auditoria", "features")
