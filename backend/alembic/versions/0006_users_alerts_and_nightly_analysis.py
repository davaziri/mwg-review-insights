"""users alerts and nightly analysis

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-20 16:01:47.535643
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0006'
down_revision: str | None = '0005'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('users',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('email', sa.String(length=320), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=True),
    sa.Column('role', sa.String(length=10), nullable=False),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('last_login_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_users')),
    sa.UniqueConstraint('email', name=op.f('uq_users_email'))
    )
    op.create_table('alerts',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('kind', sa.String(length=30), nullable=False),
    sa.Column('title_id', sa.Integer(), nullable=True),
    sa.Column('dedupe_key', sa.String(length=200), nullable=False),
    sa.Column('subject', sa.String(length=300), nullable=False),
    sa.Column('body', sa.Text(), nullable=False),
    sa.Column('channels', sa.JSON(), nullable=False),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['title_id'], ['titles.id'], name=op.f('fk_alerts_title_id_titles'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_alerts')),
    sa.UniqueConstraint('dedupe_key', name=op.f('uq_alerts_dedupe_key'))
    )
    # A plain ADD COLUMN: titles has many child tables, so it is never rebuilt in place.
    op.add_column('titles', sa.Column('auto_analyze', sa.Boolean(), server_default=sa.false(), nullable=False))


def downgrade() -> None:
    with op.batch_alter_table('titles', schema=None) as batch_op:
        batch_op.drop_column('auto_analyze')

    op.drop_table('alerts')
    op.drop_table('users')
