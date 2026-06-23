"""notificaciones in-app del usuario (CU-02)

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-06-22 12:30:00.000000

Tabla `notificacion_usuario`: avisos en el sistema (in-app) para el usuario. La usa el
cambio de tarifa (CU-02) además del correo, y queda disponible para otros avisos.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e5f6a7b8c9d0"
down_revision: str | None = "d4e5f6a7b8c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "notificacion_usuario",
        sa.Column("usuario_id", sa.BigInteger(), nullable=False),
        sa.Column("titulo", sa.String(length=160), nullable=False),
        sa.Column("cuerpo", sa.Text(), nullable=False),
        sa.Column("leida", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuario.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_notificacion_usuario_usuario_id"),
        "notificacion_usuario",
        ["usuario_id"],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_notificacion_usuario_usuario_id"), table_name="notificacion_usuario")
    op.drop_table("notificacion_usuario")
