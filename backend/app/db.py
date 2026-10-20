from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings


def create_db_engine(url: str) -> Engine:
    parsed = make_url(url)
    connect_args = {}
    if parsed.get_backend_name() == "sqlite":
        if parsed.database and parsed.database != ":memory:":
            Path(parsed.database).parent.mkdir(parents=True, exist_ok=True)
        # The app and the worker share the file; let writers wait instead of failing.
        connect_args = {"check_same_thread": False, "timeout": 30}

    engine = create_engine(url, connect_args=connect_args)

    if parsed.get_backend_name() == "sqlite":

        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_conn, _record):
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute("PRAGMA busy_timeout=30000")
            cur.close()

    return engine


engine = create_db_engine(get_settings().database_url)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_session() -> Iterator[Session]:
    """FastAPI dependency."""
    with SessionLocal() as session:
        yield session
