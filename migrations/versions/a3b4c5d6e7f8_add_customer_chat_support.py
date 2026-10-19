"""add customer chat support

Adds the Customer role: public visitors (no login required) can chat with the AI, limited
to PUBLIC-tier data. `chat_sessions` now serves all 3 owner kinds — see the `ChatSession`
model docstring for the invariant (exactly 1 of the 3 columns is set).

`sale_id` becomes nullable because a customer/anonymous session has no owning Sale; every
existing Sale query filters `WHERE sale_id = :user.id`, so existing data is unaffected.

Revision ID: a3b4c5d6e7f8
Revises: f2a3b4c5d6e7
Create Date: 2026-08-18

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a3b4c5d6e7f8"
down_revision: str | Sequence[str] | None = "f2a3b4c5d6e7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema.

    `batch_alter_table` vì SQLite không hỗ trợ ALTER để đổi nullable/thêm constraint
    (`tests/test_migrations.py` chạy migration trên SQLite) — cùng convention với
    a1f2c3d4e5b6_add_project_id_to_chat_sessions.py.
    """
    with op.batch_alter_table("chat_sessions") as batch_op:
        batch_op.alter_column("sale_id", existing_type=sa.Integer(), nullable=True)
        batch_op.add_column(sa.Column("customer_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("visitor_token", sa.String(length=64), nullable=True))
        batch_op.create_index(batch_op.f("ix_chat_sessions_customer_id"), ["customer_id"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_chat_sessions_visitor_token"), ["visitor_token"], unique=True
        )
        batch_op.create_foreign_key(
            "fk_chat_sessions_customer_id_users", "users", ["customer_id"], ["id"]
        )


def downgrade() -> None:
    """Downgrade schema.

    Drop the FK before the column, and do not drop_index customer_id by hand (the index
    backs an FK — MySQL raises error 1553; dropping the column cleans it up). visitor_token
    has no FK, so its index is dropped explicitly.
    """
    with op.batch_alter_table("chat_sessions") as batch_op:
        batch_op.drop_constraint("fk_chat_sessions_customer_id_users", type_="foreignkey")
        batch_op.drop_index(batch_op.f("ix_chat_sessions_visitor_token"))
        batch_op.drop_column("visitor_token")
        batch_op.drop_column("customer_id")
        batch_op.alter_column("sale_id", existing_type=sa.Integer(), nullable=False)
