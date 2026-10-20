from datetime import UTC, datetime


def utcnow() -> datetime:
    """Current UTC time as a naive datetime.

    Every stored datetime is naive UTC so comparisons behave the same on SQLite and Postgres.
    """
    return datetime.now(UTC).replace(tzinfo=None)


def from_unix(ts: int | None) -> datetime | None:
    if not ts:
        return None
    return datetime.fromtimestamp(ts, UTC).replace(tzinfo=None)
