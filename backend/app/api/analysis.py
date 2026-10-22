"""Analysis API: codebooks, cost estimates and runs, theme stats, tagged reviews, summary, quality."""

import random
from functools import lru_cache
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analysis.aggregate import Filters, current_tag_join, review_filter_clauses, theme_stats
from app.analysis.codebooks import CodebookError, ThemeInput, approve, approved_codebook, create_version, themes_for
from app.analysis.llm import AnthropicLLM, LLMClient, LLMNotConfigured
from app.analysis.nightly import expected_monthly_cost
from app.analysis.prep import PLAYTIME_BAND_LABELS
from app.analysis.runs import RunError, active_run, cancel, confirm, estimate_analysis, estimate_discovery, estimate_translation
from app.analysis.translation import unchecked_clauses
from app.analysis.tagging import pending_reviews
from app.api.common import filters_dep, resolve_app, review_brief, serialize_reviews, title_or_404
from app.auth import actor
from app.config import get_settings
from app.db import get_session
from app.models import AnalysisRun, Codebook, Review, ReviewTag, Summary, Theme, ThemeMention, Title

router = APIRouter(prefix="/api", tags=["analysis"])


@lru_cache
def _llm() -> AnthropicLLM:
    return AnthropicLLM(get_settings())


def get_llm() -> LLMClient:
    try:
        return _llm()
    except LLMNotConfigured as exc:
        raise HTTPException(400, str(exc)) from exc


# Helpers


def theme_out(t: Theme) -> dict:
    return {
        "id": t.id,
        "key": t.key,
        "name": t.name,
        "definition": t.definition,
        "include_notes": t.include_notes,
        "exclude_notes": t.exclude_notes,
        "example_review_ids": t.example_review_ids,
        "derived_from": t.derived_from,
        "sort_order": t.sort_order,
    }


def codebook_out(session: Session, cb: Codebook, with_themes: bool = True) -> dict:
    out = {
        "id": cb.id,
        "title_id": cb.title_id,
        "version": cb.version,
        "status": cb.status,
        "parent_id": cb.parent_id,
        "created_by": cb.created_by,
        "note": cb.note,
        "needs_review_reason": cb.needs_review_reason,
        "created_at": cb.created_at,
        "approved_at": cb.approved_at,
    }
    themes = themes_for(session, cb.id)
    out["theme_count"] = len(themes)
    if with_themes:
        out["themes"] = [theme_out(t) for t in themes]
    return out


def run_out(run: AnalysisRun) -> dict:
    details = dict(run.details or {})
    for big in ("review_ids", "qa_review_ids", "sample_review_ids", "retried_review_ids", "translate_review_ids", "retried_translation_ids"):
        details.pop(big, None)
    batches = {k: {kk: vv for kk, vv in v.items() if kk != "groups"} for k, v in (run.batches or {}).items()}
    return {
        "id": run.id,
        "title_id": run.title_id,
        "app_id": run.app_id,
        "codebook_id": run.codebook_id,
        "kind": run.kind,
        "status": run.status,
        "step": run.step,
        "mode": run.mode,
        "trigger": run.trigger,
        "requested_by": run.requested_by,
        "confirmed_by": run.confirmed_by,
        "estimate": run.estimate,
        "est_input_tokens": run.est_input_tokens,
        "est_output_tokens": run.est_output_tokens,
        "est_cost_usd": run.est_cost_usd,
        "usage": run.usage,
        "input_tokens": run.input_tokens,
        "output_tokens": run.output_tokens,
        "cache_read_tokens": run.cache_read_tokens,
        "cache_write_tokens": run.cache_write_tokens,
        "actual_cost_usd": run.actual_cost_usd,
        "reviews_in_scope": run.reviews_in_scope,
        "reviews_tagged": run.reviews_tagged,
        "reviews_failed": run.reviews_failed,
        "quotes_checked": run.quotes_checked,
        "quotes_dropped": run.quotes_dropped,
        "batches": batches,
        "details": details,
        "warning": run.warning,
        "error": run.error,
        "created_at": run.created_at,
        "confirmed_at": run.confirmed_at,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
    }


def _reviews_by_rec_id(session: Session, title_id: int, rec_ids: list[str]) -> dict[str, Review]:
    if not rec_ids:
        return {}
    return {
        r.recommendation_id: r
        for r in session.scalars(select(Review).where(Review.title_id == title_id, Review.recommendation_id.in_(rec_ids)))
    }


# Overview


@router.get("/titles/{title_id}/analysis")
def analysis_overview(title_id: int, app_id: int | None = None, session: Session = Depends(get_session)):
    title = title_or_404(session, title_id)
    app = resolve_app(title, app_id)
    approved = approved_codebook(session, title.id)
    latest = session.scalar(select(Codebook).where(Codebook.title_id == title.id).order_by(Codebook.version.desc()).limit(1))
    counts = dict(
        session.execute(
            select(Review.content_status, func.count())
            .where(Review.title_id == title.id, Review.app_id == app, Review.deleted_at.is_(None))
            .group_by(Review.content_status)
        ).all()
    )
    runs = session.scalars(
        select(AnalysisRun)
        .where(AnalysisRun.title_id == title.id, AnalysisRun.app_id == app, AnalysisRun.confirmed_at.is_not(None))
        .order_by(AnalysisRun.id.desc())
        .limit(10)
    ).all()
    active = active_run(session, title.id, app)
    return {
        "title": {"id": title.id, "name": title.name, "steam_app_id": title.steam_app_id, "demo_app_id": title.demo_app_id},
        "app_id": app,
        "reviews": {
            "total": sum(counts.values()),
            "with_content": counts.get("ok", 0),
            "no_content": counts.get("no_content", 0),
            "not_prepared": counts.get(None, 0),
            "pending": len(pending_reviews(session, title.id, app, approved.id)) if approved else None,
        },
        "min_reviews_for_discovery": get_settings().discovery_min_reviews,
        "approved_codebook": codebook_out(session, approved) if approved else None,
        "latest_codebook": codebook_out(session, latest) if latest else None,
        "active_run": run_out(active) if active else None,
        "runs": [run_out(r) for r in runs],
    }


@router.get("/titles/{title_id}/languages")
def language_status(title_id: int, app_id: int | None = None, session: Session = Depends(get_session)):
    """How many of an app's reviews still need their language checked, for the Reviews page."""
    title = title_or_404(session, title_id)
    app = resolve_app(title, app_id)
    unchecked = session.scalar(select(func.count()).select_from(Review).where(*unchecked_clauses(title.id, app)))
    translated = session.scalar(
        select(func.count())
        .select_from(Review)
        .where(Review.title_id == title.id, Review.app_id == app, Review.deleted_at.is_(None), Review.text_en.is_not(None))
    )
    active = active_run(session, title.id, app)
    return {"app_id": app, "unchecked": unchecked, "translated": translated, "active_run": run_out(active) if active else None}


# Codebooks


class ThemeIn(BaseModel):
    key: str | None = None
    name: str = Field(min_length=1, max_length=80)
    definition: str = Field(min_length=1)
    include_notes: str = ""
    exclude_notes: str = ""
    example_review_ids: list[str] = []
    derived_from: list[dict] = []


class CodebookIn(BaseModel):
    parent_id: int | None = None
    note: str | None = None
    themes: list[ThemeIn]
    approve: bool = False


@router.get("/titles/{title_id}/codebooks")
def list_codebooks(title_id: int, session: Session = Depends(get_session)):
    title_or_404(session, title_id)
    books = session.scalars(select(Codebook).where(Codebook.title_id == title_id).order_by(Codebook.version.desc()))
    return [codebook_out(session, cb, with_themes=False) for cb in books]


@router.get("/codebooks/{codebook_id}")
def get_codebook(codebook_id: int, session: Session = Depends(get_session)):
    cb = session.get(Codebook, codebook_id)
    if cb is None:
        raise HTTPException(404, "Codebook not found")
    out = codebook_out(session, cb)
    example_ids = sorted({i for t in out["themes"] for i in t["example_review_ids"]})
    reviews = _reviews_by_rec_id(session, cb.title_id, example_ids)
    out["examples"] = {rid: review_brief(r) for rid, r in reviews.items()}
    return out


@router.post("/titles/{title_id}/codebooks", status_code=201)
def save_codebook(title_id: int, body: CodebookIn, request: Request, session: Session = Depends(get_session)):
    """Save edits as a new version (versions never change after saving)."""
    title_or_404(session, title_id)
    try:
        cb = create_version(
            session,
            title_id,
            [ThemeInput(**t.model_dump()) for t in body.themes],
            created_by=actor(request),
            note=body.note,
            parent_id=body.parent_id,
        )
    except CodebookError as exc:
        raise HTTPException(400, str(exc)) from exc
    if body.approve:
        approve(session, cb, approved_by=actor(request))
    return codebook_out(session, cb)


@router.post("/codebooks/{codebook_id}/approve")
def approve_codebook(codebook_id: int, request: Request, session: Session = Depends(get_session)):
    cb = session.get(Codebook, codebook_id)
    if cb is None:
        raise HTTPException(404, "Codebook not found")
    if active_run(session, cb.title_id, session.get(Title, cb.title_id).steam_app_id):
        raise HTTPException(409, "An analysis is running for this title. Approve a codebook after it finishes.")
    approve(session, cb, approved_by=actor(request))
    return codebook_out(session, cb)


# Nightly analysis


@router.get("/titles/{title_id}/auto-analysis")
def auto_analysis(title_id: int, session: Session = Depends(get_session)):
    """Whether new reviews are analyzed nightly, the nightly limit, and the expected monthly cost."""
    return expected_monthly_cost(session, get_settings(), title_or_404(session, title_id))


# Runs


class EstimateIn(BaseModel):
    kind: Literal["discovery", "analysis", "translation"]
    app_id: int | None = None


@router.post("/titles/{title_id}/analysis/estimate", status_code=201)
def create_estimate(
    title_id: int, body: EstimateIn, request: Request, session: Session = Depends(get_session), llm: LLMClient = Depends(get_llm)
):
    """Price a run before anything is spent. Nothing runs until the estimate is confirmed."""
    title = title_or_404(session, title_id)
    app = resolve_app(title, body.app_id)
    settings = get_settings()
    try:
        if body.kind == "discovery":
            run = estimate_discovery(session, settings, llm, title, app, requested_by=actor(request))
        elif body.kind == "translation":
            run = estimate_translation(session, settings, llm, title, app, requested_by=actor(request))
        else:
            run = estimate_analysis(session, settings, llm, title, app, requested_by=actor(request))
    except RunError as exc:
        raise HTTPException(400, str(exc)) from exc
    return run_out(run)


def _run(session: Session, run_id: int) -> AnalysisRun:
    run = session.get(AnalysisRun, run_id)
    if run is None:
        raise HTTPException(404, "Run not found")
    return run


@router.post("/analysis-runs/{run_id}/confirm")
def confirm_run(run_id: int, request: Request, session: Session = Depends(get_session)):
    try:
        return run_out(confirm(session, _run(session, run_id), confirmed_by=actor(request)))
    except RunError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/analysis-runs/{run_id}/cancel")
def cancel_run(run_id: int, session: Session = Depends(get_session)):
    run = _run(session, run_id)
    llm = None
    if run.batches:
        try:
            llm = _llm()
        except LLMNotConfigured:
            llm = None
    try:
        return run_out(cancel(session, run, llm))
    except RunError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/analysis-runs/{run_id}")
def get_run(run_id: int, session: Session = Depends(get_session)):
    return run_out(_run(session, run_id))


@router.get("/analysis-runs")
def list_runs(title_id: int | None = None, limit: int = Query(50, ge=1, le=500), session: Session = Depends(get_session)):
    query = select(AnalysisRun, Title.name).join(Title, Title.id == AnalysisRun.title_id)
    if title_id is not None:
        query = query.where(AnalysisRun.title_id == title_id)
    rows = session.execute(query.order_by(AnalysisRun.id.desc()).limit(limit)).all()
    return [{**run_out(run), "title_name": name} for run, name in rows]


# Stats and reviews


@router.get("/titles/{title_id}/themes/stats")
def stats(title_id: int, f: Filters = Depends(filters_dep), session: Session = Depends(get_session)):
    title = title_or_404(session, title_id)
    f.app_id = resolve_app(title, f.app_id)
    cb = approved_codebook(session, title.id)
    themes = themes_for(session, cb.id) if cb else []
    out = theme_stats(session, title.id, cb.id if cb else None, themes, f)
    out["codebook"] = {"id": cb.id, "version": cb.version} if cb else None
    out["playtime_labels"] = PLAYTIME_BAND_LABELS
    return out


@router.get("/titles/{title_id}/reviews/tagged")
def tagged_reviews(
    title_id: int,
    f: Filters = Depends(filters_dep),
    theme: str | None = None,
    sentiment: Literal["positive", "negative", "mixed"] | None = None,
    overall: Literal["positive", "negative", "mixed", "none"] | None = None,
    random_sample: int | None = Query(None, alias="random", ge=1, le=100),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session: Session = Depends(get_session),
):
    """Analyzed reviews with their themes and verified quotes. random=N gives a fresh random sample
    (the spot check); otherwise newest first, optionally limited to one theme and sentiment, or to
    one overall impression."""
    title = title_or_404(session, title_id)
    f.app_id = resolve_app(title, f.app_id)
    cb = approved_codebook(session, title.id)
    if cb is None:
        return {"total": 0, "reviews": []}
    themes = {t.id: t for t in themes_for(session, cb.id)}
    query = (
        select(Review.id, ReviewTag.id)
        .join(ReviewTag, current_tag_join(cb.id))
        .where(*review_filter_clauses(title.id, f), Review.content_status == "ok")
    )
    if theme:
        theme_obj = next((t for t in themes.values() if t.key == theme), None)
        if theme_obj is None:
            raise HTTPException(400, f"Unknown theme '{theme}'")
        mention = select(ThemeMention.review_tag_id).where(ThemeMention.theme_id == theme_obj.id)
        if sentiment:
            mention = mention.where(ThemeMention.sentiment == sentiment)
        query = query.where(ReviewTag.id.in_(mention))
    if overall:
        query = query.where(func.coalesce(ReviewTag.overall_sentiment, "none") == overall)
    pairs = session.execute(query.order_by(Review.timestamp_created.desc())).all()
    total = len(pairs)
    if random_sample:
        pairs = random.sample(pairs, min(random_sample, total))
    else:
        pairs = pairs[(page - 1) * page_size : page * page_size]

    out = serialize_reviews(session, [(p[0], p[1]) for p in pairs], themes)
    return {"total": total, "reviews": out, "codebook": {"id": cb.id, "version": cb.version}}


@router.get("/titles/{title_id}/summary")
def latest_summary(title_id: int, app_id: int | None = None, session: Session = Depends(get_session)):
    title = title_or_404(session, title_id)
    app = resolve_app(title, app_id)
    s = session.scalar(
        select(Summary).where(Summary.title_id == title.id, Summary.app_id == app).order_by(Summary.id.desc()).limit(1)
    )
    if s is None:
        return None
    content = s.content
    ids = {i for item in content.get("strengths", []) + content.get("problems", []) for i in item.get("review_ids", [])}
    ids |= set(content.get("last_30_days", {}).get("review_ids", []))
    reviews = _reviews_by_rec_id(session, title.id, sorted(ids))
    return {
        "id": s.id,
        "model": s.model,
        "created_at": s.created_at,
        "codebook_id": s.codebook_id,
        "content": content,
        "cited_reviews": {rid: review_brief(r, 300) for rid, r in reviews.items()},
    }


@router.get("/titles/{title_id}/quality")
def quality(title_id: int, app_id: int | None = None, session: Session = Depends(get_session)):
    """Everything the Analysis quality page shows for one title."""
    title = title_or_404(session, title_id)
    app = resolve_app(title, app_id)
    cb = approved_codebook(session, title.id)
    qa_run = session.scalar(
        select(AnalysisRun)
        .where(AnalysisRun.title_id == title.id, AnalysisRun.app_id == app, AnalysisRun.kind == "analysis", AnalysisRun.status == "succeeded")
        .where(AnalysisRun.details["qa"].is_not(None))
        .order_by(AnalysisRun.id.desc())
        .limit(1)
    )
    quotes = {}
    other_notes: list[dict] = []
    analyzed = 0
    if cb:
        quotes = dict(
            session.execute(
                select(ThemeMention.quote_status, func.count())
                .join(ReviewTag, ReviewTag.id == ThemeMention.review_tag_id)
                .join(Review, current_tag_join(cb.id))
                .where(Review.title_id == title.id, Review.app_id == app, Review.deleted_at.is_(None))
                .group_by(ThemeMention.quote_status)
            ).all()
        )
        rows = session.execute(
            select(Review, ReviewTag)
            .join(ReviewTag, current_tag_join(cb.id))
            .where(Review.title_id == title.id, Review.app_id == app, Review.deleted_at.is_(None))
        ).all()
        analyzed = len(rows)
        # Overall impression quotes go through the same verbatim check, so they count here too.
        for _, t in rows:
            status = t.overall_quote_status or "none"
            quotes[status] = quotes.get(status, 0) + 1
        flagged = [(r, t) for r, t in rows if t.other_flag]
        flagged.sort(key=lambda x: -(x[0].timestamp_created or 0))
        other_notes = [{"note": t.other_note, **review_brief(r, 200)} for r, t in flagged[:50]]
        other_count = len(flagged)
    else:
        other_count = 0
    # Estimates closed without running are not part of the log.
    runs = session.scalars(
        select(AnalysisRun)
        .where(
            AnalysisRun.title_id == title.id,
            AnalysisRun.status.in_(["succeeded", "failed", "canceled"]),
            AnalysisRun.confirmed_at.is_not(None),
        )
        .order_by(AnalysisRun.id.desc())
        .limit(20)
    ).all()
    return {
        "codebook": codebook_out(session, cb, with_themes=False) if cb else None,
        "analyzed_reviews": analyzed,
        "qa": (qa_run.details or {}).get("qa") if qa_run else None,
        "qa_run_id": qa_run.id if qa_run else None,
        "quotes": {
            "verified": quotes.get("ok", 0),
            "dropped": quotes.get("dropped", 0),
            "no_quote": quotes.get("none", 0),
        },
        "other": {
            "count": other_count,
            "share": other_count / analyzed if analyzed else 0.0,
            "threshold": get_settings().other_flag_threshold,
            "notes": other_notes,
        },
        "runs": [run_out(r) for r in runs],
    }
