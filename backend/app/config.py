from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = REPO_ROOT / "data" / "mwg.db"


class Settings(BaseSettings):
    """All runtime configuration. Values come from environment variables or the repo's .env file."""

    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = f"sqlite:///{DEFAULT_DB_PATH}"
    # Built frontend served by the API in production. Defaults to frontend/dist in the repo.
    frontend_dist: str | None = None

    # Steam
    steam_publisher_key: str | None = None
    steam_request_interval_seconds: float = 1.0
    steam_request_interval_with_key_seconds: float = 0.25
    steam_max_retries: int = 8
    steam_backoff_base_seconds: float = 2.0
    steam_backoff_max_seconds: float = 300.0
    steam_timeout_seconds: float = 30.0
    # GetAppReviews sort orders. Recent (1) walks reviews by creation date and is used for full
    # crawls; Updated walks by last edit and is used for incremental syncs so edits surface first.
    steam_filter_full: int = 1
    steam_filter_incremental: int = 2
    steam_num_per_page: int = 100

    # Sync behavior
    appdetails_max_age_hours: int = 24
    full_sync_interval_days: int = 7
    # Incremental syncs re-read this much history before the last high point, to absorb
    # Steam's response caching and clock differences.
    incremental_overlap_seconds: int = 86_400
    # A full crawl will not mark reviews deleted if more than this share would disappear at once.
    deletion_guard_ratio: float = 0.2
    # If Steam's reported total exceeds our stored count by more than this, the next sync is a full crawl.
    count_drift_tolerance: float = 0.01
    resume_window_hours: int = 48

    # Worker
    sync_cron: str = "0 3 * * *"
    sync_timezone: str = "America/Chicago"
    worker_poll_seconds: float = 5.0

    # Anthropic
    anthropic_api_key: str | None = None
    # Set explicitly so an ANTHROPIC_BASE_URL meant for other tools never redirects the app.
    anthropic_api_base: str = "https://api.anthropic.com"
    model_tagging: str = "claude-haiku-5-5"
    model_analysis: str = "claude-sonnet-5-5"
    tagging_effort: str = "low"
    analysis_effort: str = "high"
    # Extra or overriding prices, USD per million tokens, e.g.
    # MODEL_PRICES='{"claude-haiku-5-5": {"input": 0.1, "output": 0.5, "cache_write": 0.125, "cache_read": 0.01}}'
    model_prices: dict[str, dict[str, float]] = {}

    # Analysis pipeline
    tagging_reviews_per_request: int = 20
    tagging_output_tokens_per_review: int = 250  # estimate only, until real runs give an average
    discovery_sample_size: int = 400
    discovery_min_reviews: int = 30
    qa_sample_rate: float = 0.05
    qa_min_reviews: int = 20
    other_flag_threshold: float = 0.10
    # Runs that tag fewer reviews than this call the API directly; larger ones use the Batches API.
    direct_max_reviews: int = 100
    batch_poll_seconds: int = 30

    @property
    def steam_request_interval(self) -> float:
        if self.steam_publisher_key:
            return self.steam_request_interval_with_key_seconds
        return self.steam_request_interval_seconds


@lru_cache
def get_settings() -> Settings:
    return Settings()
