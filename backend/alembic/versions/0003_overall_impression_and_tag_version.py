"""overall impression and tag version

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-20 02:47:24.532243
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0003'
down_revision: str | None = '0002'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('review_tags', schema=None) as batch_op:
        batch_op.add_column(sa.Column('tag_version', sa.Integer(), server_default='1', nullable=False))
        batch_op.add_column(sa.Column('overall_sentiment', sa.String(length=10), nullable=True))
        batch_op.add_column(sa.Column('overall_quote_start', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('overall_quote_end', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('overall_quote_status', sa.String(length=10), nullable=True))
        batch_op.add_column(sa.Column('overall_raw_quote', sa.Text(), nullable=True))
        batch_op.drop_constraint(batch_op.f('uq_review_tags_review_id'), type_='unique')
        batch_op.create_unique_constraint(batch_op.f('uq_review_tags_review_id'), ['review_id', 'codebook_id', 'review_timestamp_updated', 'tag_version'])



def downgrade() -> None:
    with op.batch_alter_table('review_tags', schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f('uq_review_tags_review_id'), type_='unique')
        batch_op.create_unique_constraint(batch_op.f('uq_review_tags_review_id'), ['review_id', 'codebook_id', 'review_timestamp_updated'])
        batch_op.drop_column('overall_raw_quote')
        batch_op.drop_column('overall_quote_status')
        batch_op.drop_column('overall_quote_end')
        batch_op.drop_column('overall_quote_start')
        batch_op.drop_column('overall_sentiment')
        batch_op.drop_column('tag_version')

