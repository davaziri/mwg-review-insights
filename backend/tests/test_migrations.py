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
