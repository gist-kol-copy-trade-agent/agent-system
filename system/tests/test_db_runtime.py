from app.schemas.commands import CommandEnvelope
from app.persistence.session import build_engine
from app.services.app_runtime import build_application_runtime


def test_application_runtime_uses_db_backed_strategy_profiles() -> None:
    runtime = build_application_runtime(
        callback_url="http://localhost:8000/webhooks/scraper/messages",
        callback_secret="secret",
    )
    profile = runtime.strategy_profiles.get_or_create("u-db-1")
    loaded = runtime.strategy_profiles.get_or_create("u-db-1")

    assert profile.user_id == "u-db-1"
    assert loaded.user_id == "u-db-1"
    assert loaded.version == profile.version


def test_application_runtime_follow_command_persists_source() -> None:
    runtime = build_application_runtime(
        callback_url="http://localhost:8000/webhooks/scraper/messages",
        callback_secret="secret",
    )
    response = runtime.telegram_router.handle(CommandEnvelope(user_id="u-db-2", chat_id="c-db-2", raw_text="/follow alpha_kol"))

    assert response.ok is True
    stored = runtime.source_registry.repository.get_by_source_id("u-db-2:alpha_kol")
    assert stored is not None
    assert stored.status == "profiling_pending"
    assert stored.profile_job_id == "profile:u-db-2:alpha_kol"


def test_build_engine_is_cached() -> None:
    assert build_engine() is build_engine()
