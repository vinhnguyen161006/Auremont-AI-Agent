"""add faithfulness and answer_relevancy to messages

Admin Tab 2 (AI Evaluation & Analysis) shows Faithfulness and Answer Relevancy as two
separate tiles, but `messages.verifier_score` only stores `min(faithfulness, relevancy)`
— one number cannot be split back into two. These two columns keep the component scores
given by the Verifier Agent.

They are separate because the two metrics diagnose different problems: low faithfulness
means the model invents figures (fix the prompt/verifier), low relevancy means retrieval
fetched the wrong documents (fix chunking/ingestion).

Nullable: messages written before this migration have no value, and neither do messages
that never went through the Verifier (cache hits, edge-case notices such as the empty
state or a lost connection to the inventory API).

Revision ID: b7c8d9e0f1a2
Revises: a1f2c3d4e5b6
Create Date: 2026-08-09

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'b7c8d9e0f1a2'
down_revision: str | Sequence[str] | None = 'a1f2c3d4e5b6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema.

    Uses `batch_alter_table` following the convention of earlier migrations: SQLite
    (used in tests/test_migrations.py) does not fully support ALTER, while on MySQL
    batch mode runs a plain ALTER as usual.
    """
    with op.batch_alter_table('messages') as batch_op:
        batch_op.add_column(sa.Column('faithfulness', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('answer_relevancy', sa.Float(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('messages') as batch_op:
        batch_op.drop_column('answer_relevancy')
        batch_op.drop_column('faithfulness')
