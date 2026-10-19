"""add message emotion

The new column lets the avatar (AuremontAvatar.tsx) change its expression/motion to match
the AI's answer — happy for a good answer, regretful when information is missing or a unit
is sold out, polite when handing over to a Sale or declining gracefully. Computed from
existing pipeline/gate signals, with no extra LLM call (see
backend/services/chat/agent_pipeline.py, routers/customer_chat.py).

Revision ID: d6e7f8a9b0c1
Revises: c5d6e7f8a9b0
Create Date: 2026-08-18

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d6e7f8a9b0c1"
down_revision: str | Sequence[str] | None = "c5d6e7f8a9b0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("messages") as batch_op:
        batch_op.add_column(sa.Column("emotion", sa.String(length=20), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("messages") as batch_op:
        batch_op.drop_column("emotion")
