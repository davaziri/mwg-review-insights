from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.timeutil import utcnow

SYNC_MODES = ("full", "incremental")
SYNC_STATUSES = ("queued", "running", "succeeded", "failed")
ACTIVE_STATUSES = ("queued", "running")


class SyncRun(Base):
    """One pass over one Steam app's reviews. Also serves as the worker's job queue."""

    __tablename__ = "sync_runs"
    __table_args__ = (
        Index("ix_sync_runs_status_queued", "status", "queued_at"),
        Index("ix_sync_runs_title_app", "title_id", "app_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    title_id: Mapped[int] = mapped_column(ForeignKey("titles.id", ondelete="CASCADE"))
    app_id: Mapped[int] = mapped_column(Integer)
    mode: Mapped[str] = mapped_column(String(20))
    trigger: Mapped[str] = mapped_column(String(20))  # manual | schedule
    requested_by: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default="queued")

    # Resume state. cursor is saved after every page; a new run that resumes a failed one
    # copies cursor, crawl_started_at and high_water_mark from it.
    cursor: Mapped[str | None] = mapped_column(Text)
    resumed_from_id: Mapped[int | None] = mapped_column(ForeignKey("sync_runs.id", ondelete="SET NULL"))
    # When the crawl began, across resumes. A full crawl marks reviews not seen since then as deleted.
    crawl_started_at: Mapped[datetime | None] = mapped_column(DateTime)
    # Newest timestamp_updated stored before an incremental run; the run stops once it passes this.
    high_water_mark: Mapped[int | None] = mapped_column(BigInteger)

    pages_fetched: Mapped[int] = mapped_column(Integer, default=0)
    reviews_seen: Mapped[int] = mapped_column(Integer, default=0)
    new_count: Mapped[int] = mapped_column(Integer, default=0)
    updated_count: Mapped[int] = mapped_column(Integer, default=0)
    deleted_count: Mapped[int] = mapped_column(Integer, default=0)
    restored_count: Mapped[int] = mapped_column(Integer, default=0)
    steam_total: Mapped[int | None] = mapped_column(Integer)
    warning: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)

    queued_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
