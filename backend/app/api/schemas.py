from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

TitleStatus = Literal["released", "early_access", "coming_soon", "unreleased"]
SyncMode = Literal["full", "incremental"]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class SnapshotOut(ORM):
    snapshot_date: date
    total_reviews: int | None
    total_positive: int | None
    total_negative: int | None
    review_score: int | None
    review_score_desc: str | None


class SyncRunOut(ORM):
    id: int
    title_id: int
    app_id: int
    mode: str
    trigger: str
    requested_by: str | None
    status: str
    resumed_from_id: int | None
    pages_fetched: int
    reviews_seen: int
    new_count: int
    updated_count: int
    deleted_count: int
    restored_count: int
    steam_total: int | None
    warning: str | None
    error: str | None
    queued_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class SyncRunWithTitle(SyncRunOut):
    title_name: str


class AppStats(BaseModel):
    app_id: int
    is_demo: bool
    stored_reviews: int
    stored_positive: int
    latest_snapshot: SnapshotOut | None
    last_run: SyncRunOut | None
    active_run: SyncRunOut | None


class TitleOut(ORM):
    id: int
    steam_app_id: int
    demo_app_id: int | None
    name: str
    status: str
    notes: str | None
    archived_at: datetime | None
    header_image_url: str | None
    release_date: date | None
    release_date_text: str | None
    coming_soon: bool | None
    developers: list[str] | None
    publishers: list[str] | None
    appdetails_fetched_at: datetime | None
    created_at: datetime
    auto_analyze: bool = False
    last_synced_at: datetime | None = None
    apps: list[AppStats] = []


class TitleCreate(BaseModel):
    steam_app_id: int = Field(gt=0)
    status: TitleStatus = "released"
    demo_app_id: int | None = Field(default=None, gt=0)
    name: str | None = Field(default=None, max_length=200)
    notes: str | None = None
    sync_now: bool = True


class TitleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    status: TitleStatus | None = None
    demo_app_id: int | None = Field(default=None, gt=0)
    notes: str | None = None
    auto_analyze: bool | None = None


class SyncRequest(BaseModel):
    mode: SyncMode | None = None
