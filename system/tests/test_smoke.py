import pytest

from app.config.settings import get_settings
from app.graphs.runtime import build_checkpointer, build_thread_id


def test_settings_load() -> None:
    settings = get_settings()
    assert settings.environment == "development"
    assert settings.wallet.major_assets == ["BTC", "ETH", "SOL"]


def test_runtime_helpers() -> None:
    assert build_checkpointer() is not None
    assert build_thread_id("signal", "123") == "signal:123"


def test_database_bootstrap() -> None:
    pytest.importorskip("sqlalchemy")
    from app.persistence.session import create_all

    create_all()
