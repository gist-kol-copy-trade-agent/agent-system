import pytest
import sys
import types

from app.config.settings import get_settings
from app.graphs.runtime import _build_cached_checkpointer, build_checkpointer, build_thread_id


def test_settings_load() -> None:
    settings = get_settings()
    assert settings.environment == "development"
    assert settings.wallet.major_assets == ["BTC", "ETH", "SOL"]


def test_runtime_helpers() -> None:
    assert build_checkpointer() is not None
    assert build_thread_id("signal", "123") == "signal:123"


def test_postgres_checkpointer_backend_uses_postgres_saver(monkeypatch) -> None:
    class _FakeSaver:
        setup_called = 0

        @classmethod
        def from_conn_string(cls, conn_string: str):
            instance = cls()
            instance.conn_string = conn_string
            return instance

        def setup(self) -> None:
            type(self).setup_called += 1

    module = types.ModuleType("langgraph.checkpoint.postgres")
    module.PostgresSaver = _FakeSaver
    monkeypatch.setitem(sys.modules, "langgraph.checkpoint.postgres", module)
    _build_cached_checkpointer.cache_clear()

    saver = _build_cached_checkpointer("postgres", "postgresql+psycopg://postgres:postgres@localhost:5432/okx_agent")

    assert isinstance(saver, _FakeSaver)
    assert saver.conn_string.endswith("/okx_agent")
    assert _FakeSaver.setup_called == 1

    _build_cached_checkpointer.cache_clear()


def test_postgres_checkpointer_backend_requires_installed_dependency(monkeypatch) -> None:
    monkeypatch.setenv("OKX_AGENT_LANGGRAPH__CHECKPOINTER_BACKEND", "postgres")
    get_settings.cache_clear()
    _build_cached_checkpointer.cache_clear()
    with pytest.raises(RuntimeError, match="langgraph-checkpoint-postgres"):
        build_checkpointer()
    _build_cached_checkpointer.cache_clear()
    get_settings.cache_clear()


def test_database_bootstrap() -> None:
    pytest.importorskip("sqlalchemy")
    from app.persistence.session import create_all

    create_all()
