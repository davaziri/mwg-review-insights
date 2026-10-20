"""initial schema: titles, reviews, snapshots, sync runs

Revision ID: 0001
Revises: 
Create Date: 2026-10-19 23:53:35.311810
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0001'
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('titles',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('steam_app_id', sa.Integer(), nullable=False),
    sa.Column('demo_app_id', sa.Integer(), nullable=True),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('archived_at', sa.DateTime(), nullable=True),
    sa.Column('header_image_url', sa.String(length=500), nullable=True),
    sa.Column('release_date', sa.Date(), nullable=True),
    sa.Column('release_date_text', sa.String(length=100), nullable=True),
    sa.Column('coming_soon', sa.Boolean(), nullable=True),
    sa.Column('developers', sa.JSON(), nullable=True),
    sa.Column('publishers', sa.JSON(), nullable=True),
    sa.Column('appdetails_json', sa.JSON(), nullable=True),
    sa.Column('appdetails_fetched_at', sa.DateTime(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_titles')),
    sa.UniqueConstraint('steam_app_id', name=op.f('uq_titles_steam_app_id'))
    )
    op.create_table('review_snapshots',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('title_id', sa.Integer(), nullable=False),
    sa.Column('app_id', sa.Integer(), nullable=False),
    sa.Column('snapshot_date', sa.Date(), nullable=False),
    sa.Column('total_reviews', sa.Integer(), nullable=True),
    sa.Column('total_positive', sa.Integer(), nullable=True),
    sa.Column('total_negative', sa.Integer(), nullable=True),
    sa.Column('review_score', sa.Integer(), nullable=True),
    sa.Column('review_score_desc', sa.String(length=100), nullable=True),
    sa.Column('raw_json', sa.JSON(), nullable=True),
    sa.Column('captured_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['title_id'], ['titles.id'], name=op.f('fk_review_snapshots_title_id_titles'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_review_snapshots')),
    sa.UniqueConstraint('title_id', 'app_id', 'snapshot_date', name=op.f('uq_review_snapshots_title_id'))
    )
    op.create_table('reviews',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('title_id', sa.Integer(), nullable=False),
    sa.Column('app_id', sa.Integer(), nullable=False),
    sa.Column('recommendation_id', sa.String(length=32), nullable=False),
    sa.Column('language', sa.String(length=40), nullable=True),
    sa.Column('review_text', sa.Text(), nullable=False),
    sa.Column('timestamp_created', sa.BigInteger(), nullable=True),
    sa.Column('timestamp_updated', sa.BigInteger(), nullable=True),
    sa.Column('voted_up', sa.Boolean(), nullable=True),
    sa.Column('votes_up', sa.Integer(), nullable=True),
    sa.Column('votes_funny', sa.Integer(), nullable=True),
    sa.Column('weighted_vote_score', sa.Float(), nullable=True),
    sa.Column('comment_count', sa.Integer(), nullable=True),
    sa.Column('steam_purchase', sa.Boolean(), nullable=True),
    sa.Column('received_for_free', sa.Boolean(), nullable=True),
    sa.Column('written_during_early_access', sa.Boolean(), nullable=True),
    sa.Column('primarily_steam_deck', sa.Boolean(), nullable=True),
    sa.Column('refunded', sa.Boolean(), nullable=True),
    sa.Column('developer_response', sa.Text(), nullable=True),
    sa.Column('timestamp_dev_responded', sa.BigInteger(), nullable=True),
    sa.Column('author_steamid', sa.String(length=32), nullable=True),
    sa.Column('author_num_games_owned', sa.Integer(), nullable=True),
    sa.Column('author_num_reviews', sa.Integer(), nullable=True),
    sa.Column('author_playtime_forever', sa.Integer(), nullable=True),
    sa.Column('author_playtime_last_two_weeks', sa.Integer(), nullable=True),
    sa.Column('author_playtime_at_review', sa.Integer(), nullable=True),
    sa.Column('author_deck_playtime_at_review', sa.Integer(), nullable=True),
    sa.Column('author_last_played', sa.BigInteger(), nullable=True),
    sa.Column('raw_json', sa.JSON(), nullable=False),
    sa.Column('first_seen_at', sa.DateTime(), nullable=False),
    sa.Column('last_seen_at', sa.DateTime(), nullable=False),
    sa.Column('deleted_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['title_id'], ['titles.id'], name=op.f('fk_reviews_title_id_titles'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_reviews')),
    sa.UniqueConstraint('recommendation_id', name=op.f('uq_reviews_recommendation_id'))
    )
    with op.batch_alter_table('reviews', schema=None) as batch_op:
        batch_op.create_index('ix_reviews_title_app_created', ['title_id', 'app_id', 'timestamp_created'], unique=False)
        batch_op.create_index('ix_reviews_title_app_deleted', ['title_id', 'app_id', 'deleted_at'], unique=False)

    op.create_table('sync_runs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('title_id', sa.Integer(), nullable=False),
    sa.Column('app_id', sa.Integer(), nullable=False),
    sa.Column('mode', sa.String(length=20), nullable=False),
    sa.Column('trigger', sa.String(length=20), nullable=False),
    sa.Column('requested_by', sa.String(length=200), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('cursor', sa.Text(), nullable=True),
    sa.Column('resumed_from_id', sa.Integer(), nullable=True),
    sa.Column('crawl_started_at', sa.DateTime(), nullable=True),
    sa.Column('high_water_mark', sa.BigInteger(), nullable=True),
    sa.Column('pages_fetched', sa.Integer(), nullable=False),
    sa.Column('reviews_seen', sa.Integer(), nullable=False),
    sa.Column('new_count', sa.Integer(), nullable=False),
    sa.Column('updated_count', sa.Integer(), nullable=False),
    sa.Column('deleted_count', sa.Integer(), nullable=False),
    sa.Column('restored_count', sa.Integer(), nullable=False),
    sa.Column('steam_total', sa.Integer(), nullable=True),
    sa.Column('warning', sa.Text(), nullable=True),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('queued_at', sa.DateTime(), nullable=False),
    sa.Column('started_at', sa.DateTime(), nullable=True),
    sa.Column('finished_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['resumed_from_id'], ['sync_runs.id'], name=op.f('fk_sync_runs_resumed_from_id_sync_runs'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['title_id'], ['titles.id'], name=op.f('fk_sync_runs_title_id_titles'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sync_runs'))
    )
    with op.batch_alter_table('sync_runs', schema=None) as batch_op:
        batch_op.create_index('ix_sync_runs_status_queued', ['status', 'queued_at'], unique=False)
        batch_op.create_index('ix_sync_runs_title_app', ['title_id', 'app_id'], unique=False)



def downgrade() -> None:
    with op.batch_alter_table('sync_runs', schema=None) as batch_op:
        batch_op.drop_index('ix_sync_runs_title_app')
        batch_op.drop_index('ix_sync_runs_status_queued')

    op.drop_table('sync_runs')
    with op.batch_alter_table('reviews', schema=None) as batch_op:
        batch_op.drop_index('ix_reviews_title_app_deleted')
        batch_op.drop_index('ix_reviews_title_app_created')

    op.drop_table('reviews')
    op.drop_table('review_snapshots')
    op.drop_table('titles')
