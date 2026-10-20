from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect

from app.cli import init_db
from app.db import create_db_engine
from app.models import Base
from app.search import is_search_table


def test_migrations_build_the_same_schema_as_the_models(tmp_path):
    url = f"sqlite:///{tmp_path / 'migrated.db'}"
    init_db(url)

    engine = create_db_engine(url)
    with engine.connect() as conn:
        assert set(inspect(conn).get_table_names()) >= {"titles", "reviews", "review_snapshots", "sync_runs"}
        assert "reviews_fts" in inspect(conn).get_table_names()
        skip_search = {"include_name": lambda name, type_, _: not (type_ == "table" and is_search_table(name))}
        diff = compare_metadata(MigrationContext.configure(conn, opts=skip_search), Base.metadata)
    engine.dispose()
    assert diff == []


def _filler(column):
    """A value for a required column, good enough to satisfy the schema."""
    from datetime import date, datetime

    from sqlalchemy import JSON, BigInteger, Boolean, Date, DateTime, Float, Integer

    kind = type(column.type)
    if issubclass(kind, (Integer, BigInteger)):
        return 1
    if issubclass(kind, Boolean):
        return False
    if issubclass(kind, Float):
        return 0.0
    if issubclass(kind, DateTime):
        return datetime(2026, 1, 1)
    if issubclass(kind, Date):
        return date(2026, 1, 1)
    if issubclass(kind, JSON):
        return {}
    return "x"


def test_upgrading_keeps_existing_data(tmp_path):
    """SQLite rebuilds a table to alter it; that must never cascade into deleting child rows."""
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import MetaData, func, select

    from app.cli import BACKEND_DIR

    url = f"sqlite:///{tmp_path / 'old.db'}"
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "0002")  # before the migrations that rebuild review_tags and alter titles

    engine = create_db_engine(url)  # foreign keys enforced, as the app runs
    tables = ["titles", "reviews", "codebooks", "themes", "analysis_runs", "review_tags", "theme_mentions", "qa_results", "summaries"]
    meta = MetaData()
    meta.reflect(engine, only=tables)
    with engine.begin() as conn:
        for name in tables:
            table = meta.tables[name]
            row = {c.name: _filler(c) for c in table.columns if not c.primary_key and not c.nullable and c.server_default is None}
            conn.execute(table.insert().values(**row))
    engine.dispose()

    command.upgrade(cfg, "head")

    engine = create_db_engine(url)
    with engine.connect() as conn:
        counts = {name: conn.execute(select(func.count()).select_from(meta.tables[name])).scalar() for name in tables}
        assert conn.exec_driver_sql("PRAGMA foreign_key_check").fetchall() == []
    engine.dispose()
    assert counts == dict.fromkeys(tables, 1)
