"""add handoff_requested_at to chat_sessions

The "Khách đang chờ" queue (live inbox) used to compute waiting time from the session's
`created_at` — wrong, because a session can be created long before a real person is actually
needed (the customer chats with the AI for a while before asking). This new column is
written exactly when the session moves to WAITING_SALE (see
repositories/chat_session.py::enter_waiting_queue), so it reflects when the wait started.

Revision ID: c5d6e7f8a9b0
Revises: b4c5d6e7f8a9
Create Date: 2026-08-18

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c5d6e7f8a9b0"
down_revision: str | Sequence[str] | None = "b4c5d6e7f8a9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("chat_sessions") as batch_op:
        batch_op.add_column(sa.Column("handoff_requested_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("chat_sessions") as batch_op:
        batch_op.drop_column("handoff_requested_at")
