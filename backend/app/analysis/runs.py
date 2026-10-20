"""Analysis runs: estimate, confirm, execute.

Every run is created as an estimate (input tokens counted by Anthropic's token counter, output
tokens estimated) and does nothing until a person confirms it. The worker then advances confirmed
runs as far as it can without waiting: a batch step is submitted on one pass and collected on a
later one, so a long batch never blocks review syncing.

Run kinds:
- discovery: the analysis model proposes a codebook from a stratified sample (saved as a draft).
- analysis: tag every review that has no tag for its current version under the approved codebook,
  re-tag a QA sample with the analysis model, then write the executive summary.
"""

import logging
import random
from collections.abc import Callable, Iterator, Sequence
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analysis import summary as summary_step
from app.analysis.aggregate import Filters, load_rows
from app.analysis.codebooks import approved_codebook, themes_for
from app.analysis.discovery import (
    DISCOVERY_OUTPUT_ESTIMATE,
    choose_sample,
    content_reviews,
    discovery_request,
    save_proposed_codebook,
)
from app.analysis.llm import LLMClient, LLMNotConfigured, LLMRequest
from app.analysis.prep import prepare_missing
from app.analysis.pricing import Usage, request_cost
from app.analysis.prompts import PROMPT_VERSION
from app.analysis.qa import agreement, choose_qa_sample, qa_count
from app.analysis.tagging import (
    ingest,
    mentions_by_key,
    parse_entries,
    pending_reviews,
    remaining,
    tagging_request,
)
from app.config import Settings
from app.models import AnalysisRun, Codebook, QAResult, Review, ReviewTag, Theme, ThemeMention, Title
from app.timeutil import utcnow

log = logging.getLogger(__name__)

ACTIVE = ("queued", "running")
ESTIMATE_TTL = timedelta(hours=24)
QA_OUTPUT_PER_REVIEW = 600
TOKEN_COUNT_CHUNK = 200


class RunError(Exception):
    pass


# Bookkeeping


def _set(run: AnalysisRun, attr: str, key: str, value) -> None:
    """Update one key of a JSON column (reassigning so SQLAlchemy sees the change)."""
    data = dict(getattr(run, attr) or {})
    data[key] = value
    setattr(run, attr, data)


def _append_warning(run: AnalysisRun, text: str) -> None:
    run.warning = f"{run.warning} {text}".strip() if run.warning else text


def add_usage(run: AnalysisRun, settings: Settings, step: str, model: str, usage: Usage, *, batch: bool) -> None:
    cost = request_cost(model, usage, batch=batch, settings=settings)
    entry = dict(
        (run.usage or {}).get(step)
        or {"model": model, "requests": 0, "input_tokens": 0, "output_tokens": 0, "cache_read_tokens": 0, "cache_write_tokens": 0, "cost_usd": 0.0}
    )
    entry["requests"] += 1
    for key, value in usage.as_dict().items():
        entry[key] += value
    entry["cost_usd"] = round(entry["cost_usd"] + cost, 6)
    _set(run, "usage", step, entry)
    run.input_tokens += usage.input_tokens
    run.output_tokens += usage.output_tokens
    run.cache_read_tokens += usage.cache_read_tokens
    run.cache_write_tokens += usage.cache_write_tokens
    run.actual_cost_usd = round(run.actual_cost_usd + cost, 6)


def _chunks(seq: Sequence, size: int) -> Iterator[list]:
    for i in range(0, len(seq), size):
        yield list(seq[i : i + size])


def _load_reviews(session: Session, ids: Sequence[int]) -> list[Review]:
    out: list[Review] = []
    for chunk in _chunks(list(ids), 900):
        out.extend(session.scalars(select(Review).where(Review.id.in_(chunk))))
    return sorted(out, key=lambda r: r.id)


def active_run(session: Session, title_id: int, app_id: int) -> AnalysisRun | None:
    return session.scalar(
        select(AnalysisRun)
        .where(AnalysisRun.title_id == title_id, AnalysisRun.app_id == app_id, AnalysisRun.status.in_(ACTIVE))
        .limit(1)
    )


# Estimates


def _step(step: str, model: str, requests: int, input_tokens: int, output_tokens: int, *, batch: bool, settings: Settings, **extra) -> dict:
    cost = 0.0
    if requests:
        per_request = Usage(input_tokens=input_tokens // requests, output_tokens=output_tokens // requests)
        cost = request_cost(model, per_request, batch=batch, settings=settings) * requests
    return {
        "step": step,
        "model": model,
        "requests": requests,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "batch": batch,
        "cost_usd": round(cost, 4),
        **extra,
    }


def _apply_estimate(run: AnalysisRun, steps: list[dict], notes: list[str]) -> None:
    run.estimate = {"steps": steps, "notes": notes, "prompt_version": PROMPT_VERSION}
    run.est_input_tokens = sum(s["input_tokens"] for s in steps)
    run.est_output_tokens = sum(s["output_tokens"] for s in steps)
    run.est_cost_usd = round(sum(s["cost_usd"] for s in steps), 4)


def _learned_output_per_review(session: Session, settings: Settings) -> tuple[int, bool]:
    """Average tagging output tokens per review over recent runs, or the configured default."""
    runs = session.scalars(
        select(AnalysisRun)
        .where(AnalysisRun.kind == "analysis", AnalysisRun.status == "succeeded", AnalysisRun.reviews_tagged > 0)
        .order_by(AnalysisRun.id.desc())
        .limit(5)
    ).all()
    tokens = reviews = 0
    for r in runs:
        tagging = (r.usage or {}).get("tagging")
        if tagging and tagging.get("model") == settings.model_tagging:
            tokens += tagging["output_tokens"]
            reviews += r.reviews_tagged
    if reviews >= 20:
        return max(1, round(tokens / reviews)), True
    return settings.tagging_output_tokens_per_review, False


def _check_app(title: Title, app_id: int) -> None:
    if app_id not in title.app_ids:
        raise RunError(f"App {app_id} does not belong to {title.name}.")


def estimate_discovery(
    session: Session, settings: Settings, llm: LLMClient, title: Title, app_id: int, requested_by: str | None = None
) -> AnalysisRun:
    _check_app(title, app_id)
    prepare_missing(session, title.id)
    available = len(content_reviews(session, title.id, app_id))
    if available < settings.discovery_min_reviews:
        raise RunError(
            f"Theme discovery needs at least {settings.discovery_min_reviews} reviews with text; "
            f"this app has {available}."
        )
    sample = choose_sample(session, settings, title.id, app_id)
    request = discovery_request(session, settings, title, app_id, sample)
    input_tokens = llm.count_input_tokens(request)
    run = AnalysisRun(
        title_id=title.id,
        app_id=app_id,
        kind="discovery",
        status="estimated",
        mode="direct",
        requested_by=requested_by,
        details={"sample_review_ids": [r.id for r in sample], "prompt_version": PROMPT_VERSION},
    )
    _apply_estimate(
        run,
        [_step("discovery", request.model, 1, input_tokens, DISCOVERY_OUTPUT_ESTIMATE, batch=False, settings=settings, reviews=len(sample))],
        [
            f"Reads a sample of {len(sample)} of {available} reviews with text and proposes 8 to 15 themes.",
            "Input tokens are counted exactly by Anthropic's token counter. Output tokens are an estimate.",
        ],
    )
    session.add(run)
    session.commit()
    return run


def estimate_analysis(
    session: Session, settings: Settings, llm: LLMClient, title: Title, app_id: int, requested_by: str | None = None
) -> AnalysisRun:
    _check_app(title, app_id)
    codebook = approved_codebook(session, title.id)
    if codebook is None:
        raise RunError("Approve a codebook before analyzing reviews.")
    themes = themes_for(session, codebook.id)
    prepare_missing(session, title.id)
    pending = pending_reviews(session, title.id, app_id, codebook.id)
    n = len(pending)
    batch = n >= settings.direct_max_reviews
    per = settings.tagging_reviews_per_request
    tag_requests = -(-n // per)

    steps: list[dict] = []
    notes: list[str] = []
    tag_input = 0
    if n:
        base = llm.count_input_tokens(tagging_request(title, themes, [], model=settings.model_tagging, effort=settings.tagging_effort))
        review_tokens = 0
        for chunk in _chunks(pending, TOKEN_COUNT_CHUNK):
            req = tagging_request(title, themes, chunk, model=settings.model_tagging, effort=settings.tagging_effort)
            review_tokens += llm.count_input_tokens(req) - base
        tag_input = base * tag_requests + review_tokens
    per_review, learned = _learned_output_per_review(session, settings)
    steps.append(
        _step("tagging", settings.model_tagging, tag_requests, tag_input, n * per_review, batch=batch, settings=settings, reviews=n)
    )

    qa_n = qa_count(n, settings)
    qa_ids = choose_qa_sample([r.id for r in pending], qa_n, seed=random.randrange(1 << 30)) if qa_n else []
    if qa_n:
        qa_reviews = [r for r in pending if r.id in set(qa_ids)]
        qa_requests = -(-qa_n // per)
        qa_base = llm.count_input_tokens(tagging_request(title, themes, [], model=settings.model_analysis, effort=settings.analysis_effort))
        qa_review_tokens = 0
        for chunk in _chunks(qa_reviews, TOKEN_COUNT_CHUNK):
            req = tagging_request(title, themes, chunk, model=settings.model_analysis, effort=settings.analysis_effort)
            qa_review_tokens += llm.count_input_tokens(req) - qa_base
        steps.append(
            _step(
                "qa",
                settings.model_analysis,
                qa_requests,
                qa_base * qa_requests + qa_review_tokens,
                qa_n * QA_OUTPUT_PER_REVIEW,
                batch=batch,
                settings=settings,
                reviews=qa_n,
            )
        )
    steps.append(
        _step(
            "summary",
            settings.model_analysis,
            1,
            summary_step.SUMMARY_INPUT_ESTIMATE,
            summary_step.SUMMARY_OUTPUT_ESTIMATE,
            batch=False,
            settings=settings,
        )
    )

    if n == 0:
        notes.append("Every review is already tagged under this codebook, so only the summary would be rewritten.")
    else:
        notes.append(
            f"Tags {n} reviews that have no tag for their current text under codebook v{codebook.version}. "
            "Reviews already tagged are never re-tagged."
        )
        notes.append(
            "Uses the Batches API (half price, usually done within an hour)." if batch else "Calls the API directly (small run)."
        )
    notes.append("Input tokens for tagging and QA are counted by Anthropic's token counter; output tokens and the summary are estimates.")
    if not learned:
        notes.append(f"Output is estimated at {per_review} tokens per review until a real run gives an average.")

    run = AnalysisRun(
        title_id=title.id,
        app_id=app_id,
        codebook_id=codebook.id,
        kind="analysis",
        status="estimated",
        mode="batch" if batch else "direct",
        requested_by=requested_by,
        reviews_in_scope=n,
        details={"review_ids": [r.id for r in pending], "qa_review_ids": qa_ids, "prompt_version": PROMPT_VERSION},
    )
    _apply_estimate(run, steps, notes)
    session.add(run)
    session.commit()
    return run


# Confirm / cancel


def confirm(session: Session, run: AnalysisRun, confirmed_by: str | None = None) -> AnalysisRun:
    if run.status != "estimated":
        raise RunError("This run was already confirmed or canceled.")
    if utcnow() - run.created_at > ESTIMATE_TTL:
        raise RunError("This estimate is more than a day old. Make a new one.")
    if active_run(session, run.title_id, run.app_id):
        raise RunError("Another analysis for this title is already queued or running.")
    if run.kind == "analysis":
        current = approved_codebook(session, run.title_id)
        if current is None or current.id != run.codebook_id:
            raise RunError("The approved codebook changed after this estimate. Make a new estimate.")
    run.status = "queued"
    run.confirmed_at = utcnow()
    run.confirmed_by = confirmed_by
    session.commit()
    return run


def cancel(session: Session, run: AnalysisRun, llm: LLMClient | None = None) -> AnalysisRun:
    if run.status not in ("estimated", *ACTIVE):
        raise RunError("Only estimated, queued or running analyses can be canceled.")
    if run.status == "running" and llm is not None:
        for info in (run.batches or {}).values():
            if not info.get("ingested"):
                try:
                    llm.cancel_batch(info["id"])
                except Exception:  # best effort; the run is marked canceled either way
                    log.warning("Could not cancel batch %s", info.get("id"))
    run.status = "canceled"
    run.finished_at = utcnow()
    session.commit()
    return run


# Execution


def _finish(session: Session, run: AnalysisRun) -> None:
    run.status = "succeeded"
    run.step = None
    run.next_check_at = None
    run.finished_at = utcnow()
    if run.kind == "analysis":
        run.reviews_failed = max(0, run.reviews_in_scope - run.reviews_tagged)
    session.commit()


def _batch_ready(session: Session, settings: Settings, llm: LLMClient, run: AnalysisRun, info: dict) -> bool:
    if run.next_check_at and utcnow() < run.next_check_at:
        return False
    if llm.batch_ended(info["id"]):
        return True
    run.next_check_at = utcnow() + timedelta(seconds=settings.batch_poll_seconds)
    session.commit()
    return False


def _submit(session: Session, settings: Settings, llm: LLMClient, run: AnalysisRun, step: str, groups: list[list[Review]], build: Callable[[list[Review]], LLMRequest]) -> None:
    items = [(f"run{run.id}-{step}-{i}", build(g)) for i, g in enumerate(groups)]
    batch_id = llm.submit_batch(items)
    _set(
        run,
        "batches",
        step,
        {
            "id": batch_id,
            "submitted_at": utcnow().isoformat(),
            "requests": len(items),
            "groups": {cid: [r.id for r in g] for (cid, _), g in zip(items, groups)},
            "ingested": False,
        },
    )
    run.next_check_at = utcnow() + timedelta(seconds=settings.batch_poll_seconds)
    session.commit()


def _discovery(session: Session, settings: Settings, llm: LLMClient, run: AnalysisRun, title: Title) -> None:
    sample = _load_reviews(session, run.details.get("sample_review_ids", []))
    request = discovery_request(session, settings, title, run.app_id, sample)
    result = llm.complete(request)
    add_usage(run, settings, "discovery", request.model, result.usage, batch=False)
    session.commit()
    if not result.ok:
        raise RunError(f"Theme discovery failed: {result.error}")
    codebook, warnings = save_proposed_codebook(session, run, sample, result)
    run.codebook_id = codebook.id
    _set(run, "details", "raw_output", result.data)  # the model's answer as given, for auditing
    for w in warnings:
        _append_warning(run, w)
    _finish(session, run)


def _tagging(session, settings, llm, run, title, codebook, themes) -> bool:
    """Returns True when every planned review has been attempted."""
    planned = run.details.get("review_ids", [])
    per = settings.tagging_reviews_per_request
    model = settings.model_tagging

    def build(group: list[Review]) -> LLMRequest:
        return tagging_request(title, themes, group, model=model, effort=settings.tagging_effort)

    if run.mode == "direct":
        for group in _chunks(remaining(session, codebook.id, planned), per):
            result = llm.complete(build(group))
            add_usage(run, settings, "tagging", model, result.usage, batch=False)
            ingest(session, run, codebook.id, themes, group, result)
            session.commit()
    else:
        info = (run.batches or {}).get("tagging")
        if info is None:
            todo = remaining(session, codebook.id, planned)
            if todo:
                _submit(session, settings, llm, run, "tagging", list(_chunks(todo, per)), build)
                return False
        elif not info["ingested"]:
            if not _batch_ready(session, settings, llm, run, info):
                return False
            for custom_id, result in llm.batch_results(info["id"]):
                group = _load_reviews(session, info["groups"].get(custom_id, []))
                add_usage(run, settings, "tagging", model, result.usage, batch=True)
                ingest(session, run, codebook.id, themes, group, result)
            _set(run, "batches", "tagging", {**info, "ingested": True})
            session.commit()

    # Anything the grouped requests missed (an omitted review, a declined or invalid response)
    # gets one more try on its own.
    retried = set(run.details.get("retried_review_ids", []))
    for review in [r for r in remaining(session, codebook.id, planned) if r.id not in retried]:
        result = llm.complete(build([review]))
        add_usage(run, settings, "tagging", model, result.usage, batch=False)
        ingest(session, run, codebook.id, themes, [review], result)
        retried.add(review.id)
        _set(run, "details", "retried_review_ids", sorted(retried))
        session.commit()
    return True


def _primary_mentions(session: Session, tag_ids: list[int]) -> dict[int, dict[str, str]]:
    out: dict[int, dict[str, str]] = {t: {} for t in tag_ids}
    for chunk in _chunks(tag_ids, 900):
        for tag_id, key, sentiment in session.execute(
            select(ThemeMention.review_tag_id, Theme.key, ThemeMention.sentiment)
            .join(Theme, Theme.id == ThemeMention.theme_id)
            .where(ThemeMention.review_tag_id.in_(chunk))
        ):
            out[tag_id][key] = sentiment
    return out


def _qa(session, settings, llm, run, title, codebook, themes) -> bool:
    qa_ids = run.details.get("qa_review_ids", [])
    tags = {
        t.review_id: t
        for t in session.scalars(select(ReviewTag).where(ReviewTag.analysis_run_id == run.id, ReviewTag.review_id.in_(qa_ids or [-1])))
    }
    primary = _primary_mentions(session, [t.id for t in tags.values()])
    keys = {t.key for t in themes}
    model = settings.model_analysis
    per = settings.tagging_reviews_per_request

    def build(group: list[Review]) -> LLMRequest:
        return tagging_request(title, themes, group, model=model, effort=settings.analysis_effort)

    def record(group: list[Review], result) -> None:
        entries = parse_entries(result)
        for review in group:
            entry = entries.get(review.recommendation_id)
            if entry is None or review.id not in tags:
                continue
            exists = session.scalar(select(QAResult.id).where(QAResult.analysis_run_id == run.id, QAResult.review_id == review.id).limit(1))
            if exists:
                continue
            qa_m = {k: m["sentiment"] for k, m in mentions_by_key(entry, keys).items()}
            mine = primary.get(tags[review.id].id, {})
            for t in themes:
                session.add(
                    QAResult(
                        analysis_run_id=run.id,
                        review_id=review.id,
                        theme_id=t.id,
                        primary_present=t.key in mine,
                        primary_sentiment=mine.get(t.key),
                        qa_present=t.key in qa_m,
                        qa_sentiment=qa_m.get(t.key),
                    )
                )

    done = set(session.scalars(select(QAResult.review_id).where(QAResult.analysis_run_id == run.id).distinct()))
    todo = [r for r in _load_reviews(session, list(tags)) if r.id not in done]

    if run.mode == "direct":
        for group in _chunks(todo, per):
            result = llm.complete(build(group))
            add_usage(run, settings, "qa", model, result.usage, batch=False)
            record(group, result)
            session.commit()
    else:
        info = (run.batches or {}).get("qa")
        if info is None:
            if todo:
                _submit(session, settings, llm, run, "qa", list(_chunks(todo, per)), build)
                return False
        elif not info["ingested"]:
            if not _batch_ready(session, settings, llm, run, info):
                return False
            for custom_id, result in llm.batch_results(info["id"]):
                group = _load_reviews(session, info["groups"].get(custom_id, []))
                add_usage(run, settings, "qa", model, result.usage, batch=True)
                record(group, result)
            _set(run, "batches", "qa", {**info, "ingested": True})
            session.commit()

    rows = session.execute(
        select(QAResult.theme_id, QAResult.primary_present, QAResult.primary_sentiment, QAResult.qa_present, QAResult.qa_sentiment)
        .where(QAResult.analysis_run_id == run.id)
    ).all()
    checked = len({r for r in session.scalars(select(QAResult.review_id).where(QAResult.analysis_run_id == run.id))})
    _set(run, "details", "qa", {"model": model, "reviews_checked": checked, **agreement(themes, rows)})
    session.commit()
    return True


def _check_other_rate(session: Session, settings: Settings, run: AnalysisRun, codebook: Codebook) -> None:
    rows = load_rows(session, run.title_id, codebook.id, Filters(app_id=run.app_id))
    analyzed = [r for r in rows if r.tag_id is not None]
    flagged = sum(1 for r in analyzed if r.other_flag)
    rate = flagged / len(analyzed) if analyzed else 0.0
    _set(run, "details", "other_rate", rate)
    if len(analyzed) >= 20 and rate > settings.other_flag_threshold:
        codebook.needs_review_reason = (
            f"{rate:.0%} of analyzed reviews raise points no theme covers (the limit is "
            f"{settings.other_flag_threshold:.0%}). Read the 'other' notes and consider adding or widening a theme."
        )
    else:
        codebook.needs_review_reason = None
    session.commit()


def _summary(session, settings, llm, run, title, codebook, themes) -> None:
    request, allowed, analyzed = summary_step.build_request(session, settings, title, run.app_id, codebook, themes)
    if request is None:
        _append_warning(run, "No summary: no reviews have been analyzed yet.")
        return
    result = llm.complete(request)
    add_usage(run, settings, "summary", request.model, result.usage, batch=False)
    session.commit()
    if not result.ok:
        _append_warning(run, f"The summary was not written: {result.error}.")
        return
    _, removed = summary_step.save(session, run, codebook, result, allowed, analyzed)
    if removed:
        _append_warning(run, f"Removed {removed} summary citation(s) of reviews the model was not shown.")
    session.commit()


def advance(session: Session, settings: Settings, llm: LLMClient, run: AnalysisRun) -> None:
    """Move a confirmed run forward as far as possible without waiting on a batch."""
    if run.status == "queued":
        run.status = "running"
        run.started_at = utcnow()
        run.step = "discovery" if run.kind == "discovery" else "tagging"
        session.commit()
    if run.status != "running":
        return
    title = session.get(Title, run.title_id)
    try:
        if run.kind == "discovery":
            _discovery(session, settings, llm, run, title)
            return
        codebook = session.get(Codebook, run.codebook_id)
        themes = themes_for(session, codebook.id)
        if run.step == "tagging":
            if not _tagging(session, settings, llm, run, title, codebook, themes):
                return
            _check_other_rate(session, settings, run, codebook)
            run.step = "qa"
            session.commit()
        if run.step == "qa":
            if not _qa(session, settings, llm, run, title, codebook, themes):
                return
            run.step = "summary"
            session.commit()
        if run.step == "summary":
            _summary(session, settings, llm, run, title, codebook, themes)
        _finish(session, run)
    except Exception as exc:
        session.rollback()
        log.exception("Analysis run %s failed", run.id)
        run.status = "failed"
        run.error = f"{type(exc).__name__}: {exc}"[:2000]
        run.finished_at = utcnow()
        session.commit()


def process_analysis(session_factory: Callable[[], Session], settings: Settings, llm_factory: Callable[[], LLMClient]) -> int:
    """Advance every queued or running analysis once. Returns how many were looked at."""
    with session_factory() as session:
        ids = session.scalars(select(AnalysisRun.id).where(AnalysisRun.status.in_(ACTIVE)).order_by(AnalysisRun.id)).all()
    for run_id in ids:
        with session_factory() as session:
            run = session.get(AnalysisRun, run_id)
            try:
                llm = llm_factory()
            except LLMNotConfigured as exc:
                run.status = "failed"
                run.error = str(exc)
                run.finished_at = utcnow()
                session.commit()
                continue
            advance(session, settings, llm, run)
    return len(ids)
