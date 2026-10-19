"""add project_id to chat_sessions

A consultation session needs to know which project it belongs to: the Agent Pipeline uses
`project_id` to look up real-time stock (`lookup_inventory` requires it) and to restrict
retrieval from Qdrant to that project's documents.

Nullable because sessions created before this migration have no value, and a Sale can
still open a session for general questions not tied to any project.

Revision ID: a1f2c3d4e5b6
Revises: df3813c946cc
Create Date: 2026-08-07

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'a1f2c3d4e5b6'
down_revision: str | Sequence[str] | None = 'df3813c946cc'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema.

    Dùng `batch_alter_table` vì SQLite không hỗ trợ ALTER để thêm constraint
    (`tests/test_migrations.py` chạy migration trên SQLite). Batch mode dựng bảng
    mới rồi copy dữ liệu sang; trên MySQL nó chạy ALTER thẳng như bình thường.
    """
    with op.batch_alter_table('chat_sessions') as batch_op:
        batch_op.add_column(sa.Column('project_id', sa.String(length=36), nullable=True))
        batch_op.create_index(batch_op.f('ix_chat_sessions_project_id'), ['project_id'], unique=False)
        batch_op.create_foreign_key(
            'fk_chat_sessions_project_id_projects', 'projects', ['project_id'], ['id']
        )


def downgrade() -> None:
    """Downgrade schema.

    Drop the FK before the column. Do not call `drop_index` for this column's index —
    MySQL raises error 1553 while the index backs an FK, and dropping the column removes
    the index anyway. This is the same convention as the baseline migration.
    """
    with op.batch_alter_table('chat_sessions') as batch_op:
        batch_op.drop_constraint('fk_chat_sessions_project_id_projects', type_='foreignkey')
        batch_op.drop_column('project_id')
