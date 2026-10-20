"""Matching themes across games for the compare view.

Each title's themes come from its own reviews, so the same topic can have a different name in
each game. The analysis model groups themes that are about the same aspect across the titles
being compared. The result is stored per set of approved codebooks and reused until one of those
titles approves a new codebook. Like every model call, it runs only after its cost is confirmed.
"""

import json
import string
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analysis import prompts
from app.analysis.llm import LLMClient, LLMRequest
from app.analysis.pricing import Usage, request_cost
from app.analysis.text_rules import clean_generated
from app.config import Settings
from app.models import Codebook, Theme, ThemeMatch, Title

OUTPUT_ESTIMATE = 1_500
MAX_TITLES = 4


@dataclass
class Side:
    """One title in a comparison, with its approved codebook and themes."""

    label: str
    title: Title
    codebook: Codebook
    themes: list[Theme]


def codebook_key(codebook_ids: Sequence[int]) -> str:
    return ",".join(str(i) for i in sorted(codebook_ids))


def sides_for(titles: Sequence[tuple[Title, Codebook, list[Theme]]]) -> list[Side]:
    return [Side(string.ascii_uppercase[i], t, cb, themes) for i, (t, cb, themes) in enumerate(titles)]


def stored_match(session: Session, sides: Sequence[Side]) -> ThemeMatch | None:
    key = codebook_key([s.codebook.id for s in sides])
    return session.scalar(select(ThemeMatch).where(ThemeMatch.codebook_key == key))


def build_request(settings: Settings, sides: Sequence[Side]) -> LLMRequest:
    games = [
        {
            "game": s.label,
            "title": s.title.name,
            "themes": [{"key": t.key, "name": t.name, "definition": t.definition} for t in s.themes],
        }
        for s in sides
    ]
    return LLMRequest(
        model=settings.model_analysis,
        system=prompts.text("theme_match_system"),
        user=f"Games and their themes (JSON):\n{json.dumps(games, ensure_ascii=False, indent=1)}\n\nGroup the matching themes.",
        schema=prompts.theme_match_schema([s.label for s in sides], [t.key for s in sides for t in s.themes]),
        max_tokens=16_000,
        effort=settings.analysis_effort,
    )


def estimate(settings: Settings, llm: LLMClient, sides: Sequence[Side]) -> dict:
    request = build_request(settings, sides)
    input_tokens = llm.count_input_tokens(request)
    usage = Usage(input_tokens=input_tokens, output_tokens=OUTPUT_ESTIMATE)
    return {
        "model": request.model,
        "input_tokens": input_tokens,
        "output_tokens": OUTPUT_ESTIMATE,
        "cost_usd": round(request_cost(request.model, usage, batch=False, settings=settings), 4),
    }


def clean_groups(data: dict | None, sides: Sequence[Side]) -> list[dict]:
    """Keep only groups that hold real themes from at least two games, each theme used once."""
    by_label = {s.label: s for s in sides}
    used: set[tuple[int, str]] = set()
    groups = []
    for group in (data or {}).get("groups", []):
        members, games = [], set()
        for m in group.get("themes", []):
            side = by_label.get(m.get("game"))
            if side is None or side.label in games:
                continue
            if m.get("theme_key") not in {t.key for t in side.themes}:
                continue
            ref = (side.codebook.id, m["theme_key"])
            if ref in used:
                continue
            games.add(side.label)
            members.append({"codebook_id": side.codebook.id, "theme_key": m["theme_key"]})
        if len(members) < 2:
            continue
        used.update((m["codebook_id"], m["theme_key"]) for m in members)
        name = clean_generated(str(group.get("name") or "")).strip() or "Shared theme"
        groups.append({"name": name[:80], "members": members})
    return groups


class ThemeMatchError(Exception):
    pass


def run(
    session: Session, settings: Settings, llm: LLMClient, sides: Sequence[Side], requested_by: str | None = None
) -> ThemeMatch:
    est = estimate(settings, llm, sides)
    result = llm.complete(build_request(settings, sides))
    if not result.ok:
        raise ThemeMatchError(result.error or "The model did not return an answer.")
    match = stored_match(session, sides) or ThemeMatch(codebook_key=codebook_key([s.codebook.id for s in sides]))
    match.codebook_ids = sorted(s.codebook.id for s in sides)
    match.model = result.model
    match.prompt_version = prompts.PROMPT_VERSION
    match.groups = clean_groups(result.data, sides)
    match.input_tokens = result.usage.prompt_tokens
    match.output_tokens = result.usage.output_tokens
    match.est_cost_usd = est["cost_usd"]
    match.cost_usd = request_cost(result.model, result.usage, batch=False, settings=settings)
    match.requested_by = requested_by
    session.add(match)
    session.commit()
    return match
