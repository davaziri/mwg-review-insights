"""Codebook versions. A version never changes after it is saved: edits produce a new version,
and only an approved version is used for tagging."""

import re
from dataclasses import dataclass, field

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.analysis.text_rules import strip_em_dashes
from app.models import Codebook, Theme
from app.timeutil import utcnow

MAX_THEMES = 30


class CodebookError(ValueError):
    pass


@dataclass
class ThemeInput:
    name: str
    definition: str
    include_notes: str = ""
    exclude_notes: str = ""
    key: str | None = None
    example_review_ids: list[str] = field(default_factory=list)
    derived_from: list[dict] = field(default_factory=list)


def slugify(text: str, max_len: int = 40) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return slug[:max_len].rstrip("_") or "theme"


def approved_codebook(session: Session, title_id: int) -> Codebook | None:
    return session.scalar(
        select(Codebook).where(Codebook.title_id == title_id, Codebook.status == "approved").limit(1)
    )


def themes_for(session: Session, codebook_id: int) -> list[Theme]:
    return list(
        session.scalars(select(Theme).where(Theme.codebook_id == codebook_id).order_by(Theme.sort_order, Theme.id))
    )


def create_version(
    session: Session,
    title_id: int,
    themes: list[ThemeInput],
    *,
    created_by: str,
    note: str | None = None,
    parent_id: int | None = None,
    discovery_run_id: int | None = None,
    sample_review_ids: list[str] | None = None,
) -> Codebook:
    """Save a new draft version. Theme text is cleaned of em dashes and keys are made unique."""
    if not themes:
        raise CodebookError("A codebook needs at least one theme.")
    if len(themes) > MAX_THEMES:
        raise CodebookError(f"A codebook can have at most {MAX_THEMES} themes.")
    if parent_id is not None:
        parent = session.get(Codebook, parent_id)
        if parent is None or parent.title_id != title_id:
            raise CodebookError("The parent codebook belongs to another title.")

    version = (session.scalar(select(func.max(Codebook.version)).where(Codebook.title_id == title_id)) or 0) + 1
    codebook = Codebook(
        title_id=title_id,
        version=version,
        status="draft",
        parent_id=parent_id,
        created_by=created_by,
        note=strip_em_dashes(note) if note else None,
        discovery_run_id=discovery_run_id,
        sample_review_ids=sample_review_ids,
    )
    session.add(codebook)
    session.flush()

    used: set[str] = set()
    for order, t in enumerate(themes):
        name = strip_em_dashes(t.name.strip())[:80]
        definition = strip_em_dashes(t.definition.strip())
        if not name or not definition:
            raise CodebookError("Every theme needs a name and a definition.")
        key = slugify(t.key or name)
        base, n = key, 2
        while key in used:
            key = f"{base[:37]}_{n}"
            n += 1
        used.add(key)
        session.add(
            Theme(
                codebook_id=codebook.id,
                key=key,
                name=name,
                definition=definition,
                include_notes=strip_em_dashes(t.include_notes.strip()),
                exclude_notes=strip_em_dashes(t.exclude_notes.strip()),
                example_review_ids=[str(i) for i in t.example_review_ids][:5],
                derived_from=t.derived_from,
                sort_order=order,
            )
        )
    session.commit()
    return codebook


def approve(session: Session, codebook: Codebook, approved_by: str) -> Codebook:
    """Make this version the one used for tagging. The previously approved version is superseded."""
    session.execute(
        update(Codebook)
        .where(Codebook.title_id == codebook.title_id, Codebook.status == "approved", Codebook.id != codebook.id)
        .values(status="superseded")
    )
    codebook.status = "approved"
    codebook.approved_at = utcnow()
    codebook.approved_by = approved_by
    session.commit()
    return codebook
