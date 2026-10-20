from datetime import date, datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.timeutil import utcnow


class Review(Base):
    """One Steam review. Rows are never hard-deleted; reviews removed on Steam get deleted_at."""

    __tablename__ = "reviews"
    __table_args__ = (
        Index("ix_reviews_title_app_created", "title_id", "app_id", "timestamp_created"),
        Index("ix_reviews_title_app_deleted", "title_id", "app_id", "deleted_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    title_id: Mapped[int] = mapped_column(ForeignKey("titles.id", ondelete="CASCADE"))
    # The Steam app the review was written on: the title's main app or its demo.
    app_id: Mapped[int] = mapped_column(Integer)
    recommendation_id: Mapped[str] = mapped_column(String(32), unique=True)

    language: Mapped[str | None] = mapped_column(String(40))
    review_text: Mapped[str] = mapped_column(Text, default="")
    timestamp_created: Mapped[int | None] = mapped_column(BigInteger)
    timestamp_updated: Mapped[int | None] = mapped_column(BigInteger)
    voted_up: Mapped[bool | None] = mapped_column(Boolean)
    votes_up: Mapped[int | None] = mapped_column(Integer)
    votes_funny: Mapped[int | None] = mapped_column(Integer)
    weighted_vote_score: Mapped[float | None] = mapped_column(Float)
    comment_count: Mapped[int | None] = mapped_column(Integer)
    steam_purchase: Mapped[bool | None] = mapped_column(Boolean)
    received_for_free: Mapped[bool | None] = mapped_column(Boolean)
    written_during_early_access: Mapped[bool | None] = mapped_column(Boolean)
    primarily_steam_deck: Mapped[bool | None] = mapped_column(Boolean)
    refunded: Mapped[bool | None] = mapped_column(Boolean)
    developer_response: Mapped[str | None] = mapped_column(Text)
    timestamp_dev_responded: Mapped[int | None] = mapped_column(BigInteger)

    # Author fields. Playtime values are minutes, last_played is a unix timestamp.
    author_steamid: Mapped[str | None] = mapped_column(String(32))
    author_num_games_owned: Mapped[int | None] = mapped_column(Integer)
    author_num_reviews: Mapped[int | None] = mapped_column(Integer)
    author_playtime_forever: Mapped[int | None] = mapped_column(Integer)
    author_playtime_last_two_weeks: Mapped[int | None] = mapped_column(Integer)
    author_playtime_at_review: Mapped[int | None] = mapped_column(Integer)
    author_deck_playtime_at_review: Mapped[int | None] = mapped_column(Integer)
    author_last_played: Mapped[int | None] = mapped_column(BigInteger)

    # The review exactly as Steam returned it, so no field is ever lost.
    raw_json: Mapped[dict] = mapped_column(JSON)

    # Derived by app.analysis.prep whenever the review is stored or edited.
    # display_text is review_text with Steam's [b]/[h1]/[list] markup removed; quotes index into it.
    display_text: Mapped[str | None] = mapped_column(Text)
    content_status: Mapped[str | None] = mapped_column(String(20))  # ok | no_content
    playtime_band: Mapped[str | None] = mapped_column(String(20))

    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime)


class ReviewSnapshot(Base):
    """Steam's query_summary for an app, captured at most once per day (the latest sync wins)."""

    __tablename__ = "review_snapshots"
    __table_args__ = (UniqueConstraint("title_id", "app_id", "snapshot_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    title_id: Mapped[int] = mapped_column(ForeignKey("titles.id", ondelete="CASCADE"))
    app_id: Mapped[int] = mapped_column(Integer)
    snapshot_date: Mapped[date] = mapped_column(Date)
    total_reviews: Mapped[int | None] = mapped_column(Integer)
    total_positive: Mapped[int | None] = mapped_column(Integer)
    total_negative: Mapped[int | None] = mapped_column(Integer)
    review_score: Mapped[int | None] = mapped_column(Integer)
    review_score_desc: Mapped[str | None] = mapped_column(String(100))
    raw_json: Mapped[dict | None] = mapped_column(JSON)
    captured_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
