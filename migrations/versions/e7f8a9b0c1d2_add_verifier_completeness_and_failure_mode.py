"""add verifier completeness and failure_mode

Two columns for Admin Tab 2 (AI Evaluation). `completeness` is the third scoring criterion
next to faithfulness/relevancy — for a multi-part question answered only in part, the other
two criteria stay high while the answer is not actually usable. `failure_mode` classifies
why an answer failed (invented figures / missing parts / off-question / context with no
data / unsupported commitment), so the Admin can filter by cause instead of looking at an
undifferentiated list of low scores — "the model invents numbers" and "the knowledge base
is missing a file" need completely different fixes.

Both are nullable: rows written before these columns existed, answers taken from the cache,
and every edge-case notice (empty state, lost inventory connection) skip the Verifier.

See backend/services/chat/verifier_service.py.

Revision ID: e7f8a9b0c1d2
Revises: d6e7f8a9b0c1
Create Date: 2026-08-19

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e7f8a9b0c1d2"
down_revision: str | Sequence[str] | None = "d6e7f8a9b0c1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("messages") as batch_op:
        batch_op.add_column(sa.Column("completeness", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("failure_mode", sa.String(length=32), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("messages") as batch_op:
        batch_op.drop_column("failure_mode")
        batch_op.drop_column("completeness")
