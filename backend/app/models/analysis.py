from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
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

CODEBOOK_STATUSES = ("draft", "approved", "superseded")
RUN_KINDS = ("discovery", "analysis")
RUN_STATUSES = ("estimated", "queued", "running", "succeeded", "failed", "canceled")
SENTIMENTS = ("positive", "negative", "mixed")
OVERALL_SENTIMENTS = ("positive", "negative", "mixed", "none")

# What a tag records. Bump this when tagging starts recording something new: tags made under an
# older version stop counting as current, and the next analysis run redoes them.
# 1: themes, sentiment, quotes, other flag, gist.  2: adds the overall impression.
CURRENT_TAG_VERSION = 2


class Codebook(Base):
    """A versioned set of themes for one title. Edits never change a version; they create a new one."""

    __tablename__ = "codebooks"
    __table_args__ = (UniqueConstraint("title_id", "version"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    title_id: Mapped[int] = mapped_column(ForeignKey("titles.id", ondelete="CASCADE"))
    version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("codebooks.id", ondelete="SET NULL"))
    created_by: Mapped[str] = mapped_column(String(200))
    note: Mapped[str | None] = mapped_column(Text)
    # The discovery run that proposed this version, and the reviews it read.
    discovery_run_id: Mapped[int | None] = mapped_column(Integer)
    sample_review_ids: Mapped[list | None] = mapped_column(JSON)
    # Set when tagging suggests the codebook needs another look (e.g. too many "other" points).
    needs_review_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime)
    approved_by: Mapped[str | None] = mapped_column(String(200))


class Theme(Base):
    __tablename__ = "themes"
    __table_args__ = (UniqueConstraint("codebook_id", "key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    codebook_id: Mapped[int] = mapped_column(ForeignKey("codebooks.id", ondelete="CASCADE"))
    # Stable slug. Carried across versions when a theme is kept or renamed.
    key: Mapped[str] = mapped_column(String(60))
    name: Mapped[str] = mapped_column(String(80))
    definition: Mapped[str] = mapped_column(Text)
    include_notes: Mapped[str] = mapped_column(Text, default="")
    exclude_notes: Mapped[str] = mapped_column(Text, default="")
    example_review_ids: Mapped[list] = mapped_column(JSON, default=list)
    # How this theme came from the previous version: [{"key": ..., "op": "kept|renamed|merged|split|new"}]
    derived_from: Mapped[list] = mapped_column(JSON, default=list)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class AnalysisRun(Base):
    """One confirmed piece of LLM work for a title: theme discovery, or tagging + QA + summary.

    Every run starts as 'estimated' and only executes after someone confirms the estimate.
    """

    __tablename__ = "analysis_runs"
    __table_args__ = (Index("ix_analysis_runs_status", "status"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    title_id: Mapped[int] = mapped_column(ForeignKey("titles.id", ondelete="CASCADE"))
    # Which Steam app's reviews this run reads: the title's main app, or its demo.
    app_id: Mapped[int] = mapped_column(Integer)
    codebook_id: Mapped[int | None] = mapped_column(ForeignKey("codebooks.id", ondelete="SET NULL"))
    kind: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="estimated")
    step: Mapped[str | None] = mapped_column(String(30))
    trigger: Mapped[str] = mapped_column(String(20), default="manual")
    requested_by: Mapped[str | None] = mapped_column(String(200))
    mode: Mapped[str] = mapped_column(String(10), default="direct")  # direct | batch

    estimate: Mapped[dict | None] = mapped_column(JSON)
    est_input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    est_output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    est_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime)
    confirmed_by: Mapped[str | None] = mapped_column(String(200))

    usage: Mapped[dict | None] = mapped_column(JSON)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cache_read_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cache_write_tokens: Mapped[int] = mapped_column(Integer, default=0)
    actual_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)

    reviews_in_scope: Mapped[int] = mapped_column(Integer, default=0)
    reviews_tagged: Mapped[int] = mapped_column(Integer, default=0)
    reviews_failed: Mapped[int] = mapped_column(Integer, default=0)
    quotes_checked: Mapped[int] = mapped_column(Integer, default=0)
    quotes_dropped: Mapped[int] = mapped_column(Integer, default=0)

    # Batch bookkeeping: {"tagging": {"id": ..., "submitted_at": ...}, "qa": {...}}
    batches: Mapped[dict | None] = mapped_column(JSON)
    next_check_at: Mapped[datetime | None] = mapped_column(DateTime)
    details: Mapped[dict | None] = mapped_column(JSON)
    warning: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)


class ReviewTag(Base):
    """The tagging model's reading of one review version under one codebook version."""

    __tablename__ = "review_tags"
    __table_args__ = (
        UniqueConstraint("review_id", "codebook_id", "review_timestamp_updated", "tag_version"),
        Index("ix_review_tags_codebook_review", "codebook_id", "review_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    review_id: Mapped[int] = mapped_column(ForeignKey("reviews.id", ondelete="CASCADE"))
    codebook_id: Mapped[int] = mapped_column(ForeignKey("codebooks.id", ondelete="CASCADE"))
    analysis_run_id: Mapped[int | None] = mapped_column(ForeignKey("analysis_runs.id", ondelete="SET NULL"))
    # The review's timestamp_updated when it was tagged. A different value means the review was edited.
    review_timestamp_updated: Mapped[int | None] = mapped_column(BigInteger)
    model: Mapped[str] = mapped_column(String(100))
    gist_en: Mapped[str | None] = mapped_column(Text)
    other_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    other_note: Mapped[str | None] = mapped_column(Text)
    raw_output: Mapped[dict | None] = mapped_column(JSON)
    tag_version: Mapped[int] = mapped_column(Integer, default=CURRENT_TAG_VERSION, server_default="1")
    # The reviewer's overall impression of the game as a whole, kept apart from the themes.
    # The quote offsets index into reviews.display_text, like theme quotes.
    overall_sentiment: Mapped[str | None] = mapped_column(String(10))  # positive | negative | mixed | none
    overall_quote_start: Mapped[int | None] = mapped_column(Integer)
    overall_quote_end: Mapped[int | None] = mapped_column(Integer)
    overall_quote_status: Mapped[str | None] = mapped_column(String(10))  # ok | dropped | none
    overall_raw_quote: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ThemeMention(Base):
    """A theme found in a review, with its sentiment and (if it passed the verbatim check) a quote.

    quote_start/quote_end index into reviews.display_text, so the quote shown is always the
    reviewer's own text.
    """

    __tablename__ = "theme_mentions"
    __table_args__ = (
        UniqueConstraint("review_tag_id", "theme_id"),
        Index("ix_theme_mentions_theme", "theme_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    review_tag_id: Mapped[int] = mapped_column(ForeignKey("review_tags.id", ondelete="CASCADE"))
    theme_id: Mapped[int] = mapped_column(ForeignKey("themes.id", ondelete="CASCADE"))
    sentiment: Mapped[str] = mapped_column(String(10))
    quote_start: Mapped[int | None] = mapped_column(Integer)
    quote_end: Mapped[int | None] = mapped_column(Integer)
    quote_status: Mapped[str] = mapped_column(String(10))  # ok | dropped | none
    raw_quote: Mapped[str | None] = mapped_column(Text)


class QAResult(Base):
    """One review x theme comparison between the tagging model and the analysis model."""

    __tablename__ = "qa_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    analysis_run_id: Mapped[int] = mapped_column(ForeignKey("analysis_runs.id", ondelete="CASCADE"))
    review_id: Mapped[int] = mapped_column(ForeignKey("reviews.id", ondelete="CASCADE"))
    theme_id: Mapped[int] = mapped_column(ForeignKey("themes.id", ondelete="CASCADE"))
    primary_present: Mapped[bool] = mapped_column(Boolean)
    primary_sentiment: Mapped[str | None] = mapped_column(String(10))
    qa_present: Mapped[bool] = mapped_column(Boolean)
    qa_sentiment: Mapped[str | None] = mapped_column(String(10))


class Summary(Base):
    __tablename__ = "summaries"

    id: Mapped[int] = mapped_column(primary_key=True)
    title_id: Mapped[int] = mapped_column(ForeignKey("titles.id", ondelete="CASCADE"))
    app_id: Mapped[int] = mapped_column(Integer)
    analysis_run_id: Mapped[int | None] = mapped_column(ForeignKey("analysis_runs.id", ondelete="SET NULL"))
    codebook_id: Mapped[int | None] = mapped_column(ForeignKey("codebooks.id", ondelete="SET NULL"))
    model: Mapped[str] = mapped_column(String(100))
    # {"strengths": [...], "problems": [...], "last_30_days": {...}}; every item cites review IDs.
    content: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ThemeMatch(Base):
    """Which themes mean the same thing across games, for the compare view.

    Made by the analysis model for one set of approved codebooks (one per title) and reused
    until any of those titles approves a new codebook.
    """

    __tablename__ = "theme_matches"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Sorted codebook ids joined with commas: the set of codebooks this match covers.
    codebook_key: Mapped[str] = mapped_column(String(200), unique=True)
    codebook_ids: Mapped[list] = mapped_column(JSON)
    model: Mapped[str] = mapped_column(String(100))
    prompt_version: Mapped[str] = mapped_column(String(40))
    # [{"name": ..., "members": [{"codebook_id": ..., "theme_key": ...}]}]
    groups: Mapped[list] = mapped_column(JSON)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    est_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    requested_by: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
