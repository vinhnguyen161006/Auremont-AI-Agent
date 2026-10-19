"""add chat session status

The `status` column lets the AI know when it must stay silent and leave the floor to a Sale:
a customer session (anonymous/CUSTOMER) moves from BOT_HANDLING to WAITING_SALE when a real
person is needed, then to SALE_HANDLING when a Sale clicks "Tiếp nhận". A Sale's own
consultation session (sale_id-only) does not use this column and keeps the default.

Revision ID: b4c5d6e7f8a9
Revises: a3b4c5d6e7f8
Create Date: 2026-08-18

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b4c5d6e7f8a9"
down_revision: str | Sequence[str] | None = "a3b4c5d6e7f8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema.

    `batch_alter_table` vì SQLite không hỗ trợ ALTER thêm cột NOT NULL kèm server_default
    trực tiếp (`tests/test_migrations.py` chạy migration trên SQLite) — cùng convention
    với các migration trước.
    """
    with op.batch_alter_table("chat_sessions") as batch_op:
        batch_op.add_column(
            sa.Column("status", sa.String(length=20), nullable=False, server_default="bot_handling")
        )


def downgrade() -> None:
    with op.batch_alter_table("chat_sessions") as batch_op:
        batch_op.drop_column("status")
