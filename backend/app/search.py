"""Search across review text.

On SQLite, reviews_fts is an FTS5 index over reviews.display_text, kept in step by triggers. It
uses the trigram tokenizer, so a search matches any part of a word in any language (Chinese and
Japanese reviews have no spaces between words) and ignores letter case. Terms shorter than three
characters, and databases without the index (such as Postgres), use a plain substring match.

SQLite batch migrations rebuild a table by copying it, which drops its triggers. A migration that
batch-alters reviews must call install_search_index again afterwards.
"""

import re

from sqlalchemy import Connection, Integer, column, text
from sqlalchemy.orm import Session

from app.models import Review

FTS_TABLE = "reviews_fts"
MIN_FTS_TERM = 3

_DDL = [
    f"CREATE VIRTUAL TABLE IF NOT EXISTS {FTS_TABLE} USING fts5("
    "display_text, content='reviews', content_rowid='id', tokenize='trigram')",
    f"""CREATE TRIGGER IF NOT EXISTS reviews_fts_insert AFTER INSERT ON reviews BEGIN
        INSERT INTO {FTS_TABLE}(rowid, display_text) VALUES (new.id, coalesce(new.display_text, ''));
    END""",
    f"""CREATE TRIGGER IF NOT EXISTS reviews_fts_delete AFTER DELETE ON reviews BEGIN
        INSERT INTO {FTS_TABLE}({FTS_TABLE}, rowid, display_text) VALUES ('delete', old.id, coalesce(old.display_text, ''));
    END""",
    f"""CREATE TRIGGER IF NOT EXISTS reviews_fts_update AFTER UPDATE OF display_text ON reviews BEGIN
        INSERT INTO {FTS_TABLE}({FTS_TABLE}, rowid, display_text) VALUES ('delete', old.id, coalesce(old.display_text, ''));
        INSERT INTO {FTS_TABLE}(rowid, display_text) VALUES (new.id, coalesce(new.display_text, ''));
    END""",
]


def install_search_index(conn: Connection) -> None:
    """Create the index and its triggers if missing, then index every stored review."""
    if conn.dialect.name != "sqlite":
        return
    for statement in _DDL:
        conn.exec_driver_sql(statement)
    conn.exec_driver_sql(f"INSERT INTO {FTS_TABLE}({FTS_TABLE}) VALUES ('rebuild')")


def drop_search_index(conn: Connection) -> None:
    if conn.dialect.name != "sqlite":
        return
    for trigger in ("reviews_fts_insert", "reviews_fts_delete", "reviews_fts_update"):
        conn.exec_driver_sql(f"DROP TRIGGER IF EXISTS {trigger}")
    conn.exec_driver_sql(f"DROP TABLE IF EXISTS {FTS_TABLE}")


def is_search_table(name: str | None) -> bool:
    """The index and SQLite's shadow tables for it. Alembic's model comparison skips these."""
    return bool(name) and name.startswith(FTS_TABLE)


def parse_terms(query: str) -> list[str]:
    """Words, or "quoted phrases", from a search box. Every term must match."""
    terms = []
    for phrase, word in re.findall(r'"([^"]+)"|(\S+)', query or ""):
        term = (phrase or word).strip()
        if term and term.lower() not in (t.lower() for t in terms):
            terms.append(term)
    return terms[:10]


def _has_index(session: Session) -> bool:
    if session.get_bind().dialect.name != "sqlite":
        return False
    return session.execute(text("SELECT 1 FROM sqlite_master WHERE name = :n"), {"n": FTS_TABLE}).first() is not None


def _escape_like(term: str) -> str:
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def search_clauses(session: Session, terms: list[str]) -> list:
    """WHERE clauses on Review that keep reviews containing every term."""
    if not terms:
        return []
    clauses = []
    indexed = [t for t in terms if len(t) >= MIN_FTS_TERM] if _has_index(session) else []
    if indexed:
        match = " AND ".join('"' + t.replace('"', '""') + '"' for t in indexed)
        hits = text(f"SELECT rowid FROM {FTS_TABLE} WHERE {FTS_TABLE} MATCH :match").bindparams(match=match)
        clauses.append(Review.id.in_(hits.columns(column("rowid", Integer))))
    for term in terms:
        if term not in indexed:
            clauses.append(Review.display_text.ilike(f"%{_escape_like(term)}%", escape="\\"))
    return clauses


def match_spans(display_text: str, terms: list[str]) -> list[tuple[int, int]]:
    """Where the terms occur in the text, ignoring case, merged where they overlap."""
    spans = sorted(
        (m.start(), m.end()) for t in terms for m in re.finditer(re.escape(t), display_text or "", re.IGNORECASE)
    )
    merged: list[tuple[int, int]] = []
    for start, end in spans:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return merged
