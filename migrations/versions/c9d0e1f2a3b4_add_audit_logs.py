"""add audit_logs table

Logs currently only go to stdout and vanish when the container is replaced. That is
enough to answer "what just broke", but not "who logged in last week" or "which Sale
confirmed that price" — which is what an audit trail is for.

Only business events (`salesmate.audit`) are written here. Diagnostic logs (tracebacks,
access logs) stay on stdout: they are high-volume, short-lived, and belong to the log
collector rather than the operational database.

`user_id` deliberately has NO ForeignKey: an audit row must outlive the user it refers
to. A cascade delete that wipes every trace of a removed account would defeat the very
purpose of keeping an audit.

`payload` is JSON rather than a wide table full of NULL columns: each event type has a
different shape, and adding a field to one event should not require a migration.

Revision ID: c9d0e1f2a3b4
Revises: b7c8d9e0f1a2
Create Date: 2026-08-13

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'c9d0e1f2a3b4'
down_revision: str | Sequence[str] | None = 'b7c8d9e0f1a2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'audit_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('event', sa.String(length=64), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('username', sa.String(length=50), nullable=True),
        sa.Column('request_id', sa.String(length=64), nullable=True),
        sa.Column('payload', sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_audit_logs_id'), 'audit_logs', ['id'])
    op.create_index(op.f('ix_audit_logs_event'), 'audit_logs', ['event'])
    op.create_index(op.f('ix_audit_logs_user_id'), 'audit_logs', ['user_id'])
    op.create_index(op.f('ix_audit_logs_created_at'), 'audit_logs', ['created_at'])
    op.create_index(op.f('ix_audit_logs_request_id'), 'audit_logs', ['request_id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_audit_logs_request_id'), table_name='audit_logs')
    op.drop_index(op.f('ix_audit_logs_created_at'), table_name='audit_logs')
    op.drop_index(op.f('ix_audit_logs_user_id'), table_name='audit_logs')
    op.drop_index(op.f('ix_audit_logs_event'), table_name='audit_logs')
    op.drop_index(op.f('ix_audit_logs_id'), table_name='audit_logs')
    op.drop_table('audit_logs')
