"""review language check and translation

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-22 18:00:00
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0007'
down_revision: str | None = '0006'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Plain ADD COLUMNs: reviews carries the search index triggers and child tables, so it is never
    # rebuilt in place.
    op.add_column('reviews', sa.Column('text_language', sa.String(length=40), nullable=True))
    op.add_column('reviews', sa.Column('text_en', sa.Text(), nullable=True))
    op.add_column('reviews', sa.Column('language_checked_for', sa.BigInteger(), nullable=True))
    op.add_column('reviews', sa.Column('translation_model', sa.String(length=64), nullable=True))


def downgrade() -> None:
    # SQLite 3.35+ drops columns in place, which keeps the search index triggers.
    for column in ('translation_model', 'language_checked_for', 'text_en', 'text_language'):
        op.drop_column('reviews', column)
