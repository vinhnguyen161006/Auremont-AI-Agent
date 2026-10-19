"""add message quick_replies

The new column lets the AI (when consulting customers via SYSTEM_INSTRUCTION_PUBLIC) attach
2-4 short answer options to the needs-discovery question it just asked (e.g. "Để ở"/"Đầu tư"),
so the customer can tap instead of typing. The model decides per question whether to offer
options — there is no fixed option set in the backend. See backend/ai/prompts.py::ConsultAnswer
and backend/services/chat/agent_pipeline.py.

Revision ID: f1a2b3c4d5e6
Revises: e7f8a9b0c1d2
Create Date: 2026-08-19

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f1a2b3c4d5e6"
down_revision: str | Sequence[str] | None = "e7f8a9b0c1d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("messages") as batch_op:
        batch_op.add_column(sa.Column("quick_replies", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("messages") as batch_op:
        batch_op.drop_column("quick_replies")
