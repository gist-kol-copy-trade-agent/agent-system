import pytest

from app.config.settings import get_settings
from app.persistence.session import build_engine, build_session_factory


@pytest.fixture(autouse=True)
def _test_database_env(monkeypatch):
    monkeypatch.setenv("OKX_AGENT_PERSISTENCE__DATABASE_URL", "sqlite+pysqlite:///:memory:")
    monkeypatch.setenv("OKX_AGENT_LANGGRAPH__CHECKPOINTER_BACKEND", "memory")
    get_settings.cache_clear()
    build_engine.cache_clear()
    build_session_factory.cache_clear()
    yield
    get_settings.cache_clear()
    build_engine.cache_clear()
    build_session_factory.cache_clear()
