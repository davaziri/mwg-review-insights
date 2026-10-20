"""analysis pipeline

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-20 01:05:19.814250
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0002'
down_revision: str | None = '0001'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('codebooks',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('title_id', sa.Integer(), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('parent_id', sa.Integer(), nullable=True),
    sa.Column('created_by', sa.String(length=200), nullable=False),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('discovery_run_id', sa.Integer(), nullable=True),
    sa.Column('sample_review_ids', sa.JSON(), nullable=True),
    sa.Column('needs_review_reason', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('approved_at', sa.DateTime(), nullable=True),
    sa.Column('approved_by', sa.String(length=200), nullable=True),
    sa.ForeignKeyConstraint(['parent_id'], ['codebooks.id'], name=op.f('fk_codebooks_parent_id_codebooks'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['title_id'], ['titles.id'], name=op.f('fk_codebooks_title_id_titles'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_codebooks')),
    sa.UniqueConstraint('title_id', 'version', name=op.f('uq_codebooks_title_id'))
    )
    op.create_table('analysis_runs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('title_id', sa.Integer(), nullable=False),
    sa.Column('app_id', sa.Integer(), nullable=False),
    sa.Column('codebook_id', sa.Integer(), nullable=True),
    sa.Column('kind', sa.String(length=20), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('step', sa.String(length=30), nullable=True),
    sa.Column('trigger', sa.String(length=20), nullable=False),
    sa.Column('requested_by', sa.String(length=200), nullable=True),
    sa.Column('mode', sa.String(length=10), nullable=False),
    sa.Column('estimate', sa.JSON(), nullable=True),
    sa.Column('est_input_tokens', sa.Integer(), nullable=False),
    sa.Column('est_output_tokens', sa.Integer(), nullable=False),
    sa.Column('est_cost_usd', sa.Float(), nullable=False),
    sa.Column('confirmed_at', sa.DateTime(), nullable=True),
    sa.Column('confirmed_by', sa.String(length=200), nullable=True),
    sa.Column('usage', sa.JSON(), nullable=True),
    sa.Column('input_tokens', sa.Integer(), nullable=False),
    sa.Column('output_tokens', sa.Integer(), nullable=False),
    sa.Column('cache_read_tokens', sa.Integer(), nullable=False),
    sa.Column('cache_write_tokens', sa.Integer(), nullable=False),
    sa.Column('actual_cost_usd', sa.Float(), nullable=False),
    sa.Column('reviews_in_scope', sa.Integer(), nullable=False),
    sa.Column('reviews_tagged', sa.Integer(), nullable=False),
    sa.Column('reviews_failed', sa.Integer(), nullable=False),
    sa.Column('quotes_checked', sa.Integer(), nullable=False),
    sa.Column('quotes_dropped', sa.Integer(), nullable=False),
    sa.Column('batches', sa.JSON(), nullable=True),
    sa.Column('next_check_at', sa.DateTime(), nullable=True),
    sa.Column('details', sa.JSON(), nullable=True),
    sa.Column('warning', sa.Text(), nullable=True),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('started_at', sa.DateTime(), nullable=True),
    sa.Column('finished_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['codebook_id'], ['codebooks.id'], name=op.f('fk_analysis_runs_codebook_id_codebooks'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['title_id'], ['titles.id'], name=op.f('fk_analysis_runs_title_id_titles'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_analysis_runs'))
    )
    with op.batch_alter_table('analysis_runs', schema=None) as batch_op:
        batch_op.create_index('ix_analysis_runs_status', ['status'], unique=False)

    op.create_table('themes',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('codebook_id', sa.Integer(), nullable=False),
    sa.Column('key', sa.String(length=60), nullable=False),
    sa.Column('name', sa.String(length=80), nullable=False),
    sa.Column('definition', sa.Text(), nullable=False),
    sa.Column('include_notes', sa.Text(), nullable=False),
    sa.Column('exclude_notes', sa.Text(), nullable=False),
    sa.Column('example_review_ids', sa.JSON(), nullable=False),
    sa.Column('derived_from', sa.JSON(), nullable=False),
    sa.Column('sort_order', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['codebook_id'], ['codebooks.id'], name=op.f('fk_themes_codebook_id_codebooks'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_themes')),
    sa.UniqueConstraint('codebook_id', 'key', name=op.f('uq_themes_codebook_id'))
    )
    op.create_table('qa_results',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('analysis_run_id', sa.Integer(), nullable=False),
    sa.Column('review_id', sa.Integer(), nullable=False),
    sa.Column('theme_id', sa.Integer(), nullable=False),
    sa.Column('primary_present', sa.Boolean(), nullable=False),
    sa.Column('primary_sentiment', sa.String(length=10), nullable=True),
    sa.Column('qa_present', sa.Boolean(), nullable=False),
    sa.Column('qa_sentiment', sa.String(length=10), nullable=True),
    sa.ForeignKeyConstraint(['analysis_run_id'], ['analysis_runs.id'], name=op.f('fk_qa_results_analysis_run_id_analysis_runs'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['review_id'], ['reviews.id'], name=op.f('fk_qa_results_review_id_reviews'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['theme_id'], ['themes.id'], name=op.f('fk_qa_results_theme_id_themes'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_qa_results'))
    )
    op.create_table('review_tags',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('review_id', sa.Integer(), nullable=False),
    sa.Column('codebook_id', sa.Integer(), nullable=False),
    sa.Column('analysis_run_id', sa.Integer(), nullable=True),
    sa.Column('review_timestamp_updated', sa.BigInteger(), nullable=True),
    sa.Column('model', sa.String(length=100), nullable=False),
    sa.Column('gist_en', sa.Text(), nullable=True),
    sa.Column('other_flag', sa.Boolean(), nullable=False),
    sa.Column('other_note', sa.Text(), nullable=True),
    sa.Column('raw_output', sa.JSON(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['analysis_run_id'], ['analysis_runs.id'], name=op.f('fk_review_tags_analysis_run_id_analysis_runs'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['codebook_id'], ['codebooks.id'], name=op.f('fk_review_tags_codebook_id_codebooks'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['review_id'], ['reviews.id'], name=op.f('fk_review_tags_review_id_reviews'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_review_tags')),
    sa.UniqueConstraint('review_id', 'codebook_id', 'review_timestamp_updated', name=op.f('uq_review_tags_review_id'))
    )
    with op.batch_alter_table('review_tags', schema=None) as batch_op:
        batch_op.create_index('ix_review_tags_codebook_review', ['codebook_id', 'review_id'], unique=False)

    op.create_table('summaries',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('title_id', sa.Integer(), nullable=False),
    sa.Column('app_id', sa.Integer(), nullable=False),
    sa.Column('analysis_run_id', sa.Integer(), nullable=True),
    sa.Column('codebook_id', sa.Integer(), nullable=True),
    sa.Column('model', sa.String(length=100), nullable=False),
    sa.Column('content', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['analysis_run_id'], ['analysis_runs.id'], name=op.f('fk_summaries_analysis_run_id_analysis_runs'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['codebook_id'], ['codebooks.id'], name=op.f('fk_summaries_codebook_id_codebooks'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['title_id'], ['titles.id'], name=op.f('fk_summaries_title_id_titles'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_summaries'))
    )
    op.create_table('theme_mentions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('review_tag_id', sa.Integer(), nullable=False),
    sa.Column('theme_id', sa.Integer(), nullable=False),
    sa.Column('sentiment', sa.String(length=10), nullable=False),
    sa.Column('quote_start', sa.Integer(), nullable=True),
    sa.Column('quote_end', sa.Integer(), nullable=True),
    sa.Column('quote_status', sa.String(length=10), nullable=False),
    sa.Column('raw_quote', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['review_tag_id'], ['review_tags.id'], name=op.f('fk_theme_mentions_review_tag_id_review_tags'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['theme_id'], ['themes.id'], name=op.f('fk_theme_mentions_theme_id_themes'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_theme_mentions')),
    sa.UniqueConstraint('review_tag_id', 'theme_id', name=op.f('uq_theme_mentions_review_tag_id'))
    )
    with op.batch_alter_table('theme_mentions', schema=None) as batch_op:
        batch_op.create_index('ix_theme_mentions_theme', ['theme_id'], unique=False)

    with op.batch_alter_table('reviews', schema=None) as batch_op:
        batch_op.add_column(sa.Column('display_text', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('content_status', sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column('playtime_band', sa.String(length=20), nullable=True))



def downgrade() -> None:
    with op.batch_alter_table('reviews', schema=None) as batch_op:
        batch_op.drop_column('playtime_band')
        batch_op.drop_column('content_status')
        batch_op.drop_column('display_text')

    with op.batch_alter_table('theme_mentions', schema=None) as batch_op:
        batch_op.drop_index('ix_theme_mentions_theme')

    op.drop_table('theme_mentions')
    op.drop_table('summaries')
    with op.batch_alter_table('review_tags', schema=None) as batch_op:
        batch_op.drop_index('ix_review_tags_codebook_review')

    op.drop_table('review_tags')
    op.drop_table('qa_results')
    op.drop_table('themes')
    with op.batch_alter_table('analysis_runs', schema=None) as batch_op:
        batch_op.drop_index('ix_analysis_runs_status')

    op.drop_table('analysis_runs')
    op.drop_table('codebooks')
