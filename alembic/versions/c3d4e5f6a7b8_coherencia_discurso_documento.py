"""coherencia discurso↔documento (CU-14, dimensión defensa)

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-06-20 23:40:00.000000

Persiste el texto transcrito por segmento (metrica_biometrica.transcripcion_texto) para
poder medir, al cerrar la sesión, la similitud semántica entre lo que el estudiante DIJO
y su documento. Guarda ese puntaje en resultado_simulacion.coherencia_documento_score.
Alimenta la nueva 7ª feature `coherencia_discurso_documento` de la IA evaluadora.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c3d4e5f6a7b8"
down_revision: str | None = "b2c3d4e5f6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "metrica_biometrica",
        sa.Column("transcripcion_texto", sa.Text(), nullable=False, server_default=""),
    )
    op.add_column(
        "resultado_simulacion",
        sa.Column("coherencia_documento_score", sa.Numeric(5, 2), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("resultado_simulacion", "coherencia_documento_score")
    op.drop_column("metrica_biometrica", "transcripcion_texto")
