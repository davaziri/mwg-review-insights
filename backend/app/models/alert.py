from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.timeutil import utcnow

ALERT_KINDS = ("sync_failed", "analysis_failed", "needs_confirmation", "positive_drop")


class Alert(Base):
    """Something the team should know about, sent to Slack and/or email and listed in the run log.

    dedupe_key makes each alert happen once: per failed run, or per title and week for a drop.
    """

    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(30))
    title_id: Mapped[int | None] = mapped_column(ForeignKey("titles.id", ondelete="CASCADE"))
    dedupe_key: Mapped[str] = mapped_column(String(200), unique=True)
    subject: Mapped[str] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text)
    # Where it went: ["slack", "email"], or [] when no channel is set up.
    channels: Mapped[list] = mapped_column(JSON, default=list)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
