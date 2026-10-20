import pytest
import respx
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.config import Settings
from app.db import create_db_engine, get_session
from app.main import create_app
from app.models import Base, Title
from app.search import install_search_index
from app.seed import seed_titles
from app.steam.client import APPDETAILS_URL, REVIEWS_URL, SteamClient
from tests.fakes import FakeSteam


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        _env_file=None,
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        steam_publisher_key=None,
        steam_request_interval_seconds=0,
        steam_max_retries=2,
        auth_mode="local",
    )


@pytest.fixture
def engine(settings):
    engine = create_db_engine(settings.database_url)
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        install_search_index(conn)
    yield engine
    engine.dispose()


@pytest.fixture
def session_factory(engine):
    return sessionmaker(bind=engine, expire_on_commit=False)


@pytest.fixture
def session(session_factory):
    with session_factory() as session:
        yield session


@pytest.fixture
def sleeps() -> list[float]:
    return []


@pytest.fixture
def fake_steam():
    fake = FakeSteam()
    with respx.mock(assert_all_called=False) as mock:
        mock.get(REVIEWS_URL).mock(side_effect=fake.reviews_handler)
        mock.get(APPDETAILS_URL).mock(side_effect=fake.appdetails_handler)
        yield fake


@pytest.fixture
def steam_client(sleeps, fake_steam):
    client = SteamClient(min_interval=0, max_retries=2, sleep=sleeps.append, jitter=lambda: 0.0)
    yield client
    client.close()


@pytest.fixture
def fake_llm():
    from tests.fake_llm import FakeLLM

    return FakeLLM()


@pytest.fixture
def api(session_factory, settings, monkeypatch, fake_llm) -> TestClient:
    """The FastAPI app wired to the test database, settings and fake LLM, with seed titles loaded."""
    from app.api import analysis

    for module in ("app.api.titles", "app.api.sync", "app.api.analysis", "app.api.portfolio", "app.api.exports", "app.api.auth", "app.api.alerts", "app.auth"):
        monkeypatch.setattr(f"{module}.get_settings", lambda: settings)
    monkeypatch.setattr(analysis, "_llm", lambda: fake_llm)
    app = create_app()

    def _session():
        with session_factory() as s:
            yield s

    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[analysis.get_llm] = lambda: fake_llm
    with session_factory() as s:
        seed_titles(s)
    return TestClient(app)


@pytest.fixture
def title(session) -> Title:
    t = Title(name="Tombwater", steam_app_id=3308200, status="released")
    session.add(t)
    session.commit()
    return t
