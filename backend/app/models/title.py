from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, Integer, String, Text, false
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin

TITLE_STATUSES = ("released", "early_access", "coming_soon", "unreleased")


class Title(TimestampMixin, Base):
    __tablename__ = "titles"

    id: Mapped[int] = mapped_column(primary_key=True)
    steam_app_id: Mapped[int] = mapped_column(Integer, unique=True)
    demo_app_id: Mapped[int | None] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default="released")
    notes: Mapped[str | None] = mapped_column(Text)
    # Archived titles stay in the database but are hidden by default and skipped by the nightly sync.
    archived_at: Mapped[datetime | None] = mapped_column(DateTime)
    # Analyze new reviews every night (an admin switches this on; each night has a cost cap).
    auto_analyze: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())

    # Cached from Steam's appdetails store endpoint.
    header_image_url: Mapped[str | None] = mapped_column(String(500))
    release_date: Mapped[date | None] = mapped_column(Date)
    release_date_text: Mapped[str | None] = mapped_column(String(100))
    coming_soon: Mapped[bool | None] = mapped_column(Boolean)
    developers: Mapped[list | None] = mapped_column(JSON)
    publishers: Mapped[list | None] = mapped_column(JSON)
    appdetails_json: Mapped[dict | None] = mapped_column(JSON)
    appdetails_fetched_at: Mapped[datetime | None] = mapped_column(DateTime)

    @property
    def app_ids(self) -> list[int]:
        """Steam apps synced for this title: the main app, then the demo if there is one."""
        ids = [self.steam_app_id]
        if self.demo_app_id:
            ids.append(self.demo_app_id)
        return ids
