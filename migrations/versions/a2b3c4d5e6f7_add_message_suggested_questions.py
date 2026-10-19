"""add message suggested_questions

The new column stores the 2-3 follow-up questions the AI suggests after each answer (e.g.
"Giá căn 2PN bao nhiêu?"), based on the topic of the chat session. Unlike `quick_replies`
(customer flow only, ANSWER options to the question the AI just asked), this column applies
to BOTH Sales and customers and holds NEW questions the user may want to ask next.

Generated in the same LLM call as the answer (schema-constrained decoding), with no extra
round trip. See backend/ai/prompts.py::ConsultAnswer / SaleAnswer and
backend/services/chat/agent_pipeline.py::_generate.

Revision ID: a2b3c4d5e6f7
Revises: f1a2b3c4d5e6
Create Date: 2026-08-21

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a2b3c4d5e6f7"
down_revision: str | Sequence[str] | None = "f1a2b3c4d5e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("messages") as batch_op:
        batch_op.add_column(sa.Column("suggested_questions", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("messages") as batch_op:
        batch_op.drop_column("suggested_questions")
