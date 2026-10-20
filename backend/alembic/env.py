from alembic import context

from app.config import get_settings
from app.db import create_db_engine
from app.models import Base

config = context.config
target_metadata = Base.metadata


def _url() -> str:
    # Tests pass an explicit URL through the Alembic config; otherwise use app settings.
    return config.get_main_option("sqlalchemy.url") or get_settings().database_url


def run_migrations_offline() -> None:
    context.configure(
        url=_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_db_engine(_url())
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # Batch mode lets ALTER-style migrations work on SQLite.
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
