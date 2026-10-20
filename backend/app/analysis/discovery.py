"""Theme discovery: the analysis model reads a stratified sample and proposes a codebook."""

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.analysis import prompts
from app.analysis.codebooks import ThemeInput, create_version
from app.analysis.formatting import reviews_block
from app.analysis.llm import LLMRequest, LLMResult
from app.analysis.sampling import stratified_sample
from app.analysis.text_rules import clean_generated
from app.config import Settings
from app.models import AnalysisRun, Codebook, Review, ReviewSnapshot, Title

DISCOVERY_MAX_CHARS = 4000
DISCOVERY_OUTPUT_ESTIMATE = 10_000  # codebook plus the model's reasoning
MIN_THEMES, MAX_THEMES = 8, 15


def content_reviews(session: Session, title_id: int, app_id: int) -> list[Review]:
    return list(
        session.scalars(
            select(Review)
            .where(
                Review.title_id == title_id,
                Review.app_id == app_id,
                Review.deleted_at.is_(None),
                Review.content_status == "ok",
            )
            .order_by(Review.id)
        )
    )


def choose_sample(session: Session, settings: Settings, title_id: int, app_id: int) -> list[Review]:
    reviews = content_reviews(session, title_id, app_id)
    return stratified_sample(reviews, settings.discovery_sample_size, seed=title_id * 1_000_003 + app_id)


def _totals(session: Session, title_id: int, app_id: int) -> tuple[int, int]:
    snap = session.scalar(
        select(ReviewSnapshot)
        .where(ReviewSnapshot.title_id == title_id, ReviewSnapshot.app_id == app_id)
        .order_by(ReviewSnapshot.snapshot_date.desc())
        .limit(1)
    )
    if snap and snap.total_reviews:
        return snap.total_reviews, snap.total_positive or 0
    total, positive = session.execute(
        select(func.count(), func.sum(case((Review.voted_up.is_(True), 1), else_=0)))
        .where(Review.title_id == title_id, Review.app_id == app_id, Review.deleted_at.is_(None))
    ).one()
    return total or 0, positive or 0


def discovery_request(session: Session, settings: Settings, title: Title, app_id: int, sample: list[Review]) -> LLMRequest:
    total, positive = _totals(session, title.id, app_id)
    user = prompts.render(
        "discovery_user",
        game=title.name,
        developer=", ".join(title.developers or []) or "unknown",
        total_reviews=total,
        positive_pct=round(100 * positive / total) if total else 0,
        sample_size=len(sample),
        reviews=reviews_block(sample, max_chars=DISCOVERY_MAX_CHARS),
    )
    return LLMRequest(
        model=settings.model_analysis,
        system=prompts.text("discovery_system"),
        user=user,
        schema=prompts.DISCOVERY_SCHEMA,
        max_tokens=32_000,
        effort=settings.analysis_effort,
    )


def save_proposed_codebook(
    session: Session, run: AnalysisRun, sample: list[Review], result: LLMResult
) -> tuple[Codebook, list[str]]:
    """Validate the model's proposal and store it as a new draft version. Returns warnings."""
    data = clean_generated(result.data)
    sample_ids = {r.recommendation_id for r in sample}
    warnings: list[str] = []
    themes = []
    for t in data.get("themes", []):
        examples = [i for i in t.get("example_review_ids", []) if str(i) in sample_ids][:2]
        themes.append(
            ThemeInput(
                key=t.get("key") or None,
                name=t.get("name", ""),
                definition=t.get("definition", ""),
                include_notes=t.get("include", ""),
                exclude_notes=t.get("exclude", ""),
                example_review_ids=examples,
                derived_from=[{"op": "new"}],
            )
        )
    themes = [t for t in themes if t.name.strip() and t.definition.strip()]
    if not MIN_THEMES <= len(themes) <= MAX_THEMES:
        warnings.append(f"The model proposed {len(themes)} themes (asked for {MIN_THEMES} to {MAX_THEMES}). Review before approving.")
    codebook = create_version(
        session,
        run.title_id,
        themes,
        created_by=f"{result.model or 'model'} (theme discovery)",
        note=f"Proposed from {len(sample)} sampled reviews.",
        discovery_run_id=run.id,
        sample_review_ids=sorted(sample_ids),
    )
    return codebook, warnings
