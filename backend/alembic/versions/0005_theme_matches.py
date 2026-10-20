"""theme matches

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-20 03:43:30.472536
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0005'
down_revision: str | None = '0004'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('theme_matches',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('codebook_key', sa.String(length=200), nullable=False),
    sa.Column('codebook_ids', sa.JSON(), nullable=False),
    sa.Column('model', sa.String(length=100), nullable=False),
    sa.Column('prompt_version', sa.String(length=40), nullable=False),
    sa.Column('groups', sa.JSON(), nullable=False),
    sa.Column('input_tokens', sa.Integer(), nullable=False),
    sa.Column('output_tokens', sa.Integer(), nullable=False),
    sa.Column('est_cost_usd', sa.Float(), nullable=False),
    sa.Column('cost_usd', sa.Float(), nullable=False),
    sa.Column('requested_by', sa.String(length=200), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_theme_matches')),
    sa.UniqueConstraint('codebook_key', name=op.f('uq_theme_matches_codebook_key'))
    )


def downgrade() -> None:
    op.drop_table('theme_matches')
