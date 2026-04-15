from app.persistence.repositories import InMemoryWalletSessionRepository, WalletSessionRecord
from app.persistence.session import build_session_factory, create_all
from app.services.readiness import RuntimeReadinessService


def test_runtime_readiness_reports_not_trade_ready_without_wallet_sessions(monkeypatch) -> None:
    create_all()
    service = RuntimeReadinessService(session_factory=build_session_factory())
    monkeypatch.setattr("app.services.readiness.shutil.which", lambda _: "/usr/local/bin/onchainos")
    monkeypatch.setattr(service, "_check_database", lambda: (True, "ok"))
    monkeypatch.setattr(service, "_check_checkpointer_backend", lambda: (True, "ok"))
    monkeypatch.setattr(service, "_check_onchainos_readonly_probe", lambda binary_path: (True, "ok"))
    monkeypatch.setattr(service, "_check_scraper_reachability", lambda: (True, "ok"))

    result = service.run()

    assert result.checks["wallet_sessions"]["ok"] is False
    assert result.checks["trading_runtime_ready"]["ok"] is False


def test_runtime_readiness_reports_trade_ready_with_usable_wallet(monkeypatch) -> None:
    create_all()
    repo = InMemoryWalletSessionRepository()
    repo.save(
        WalletSessionRecord(
            user_id="u1",
            logged_in=True,
            wallet_xlayer_address="0xabc",
        )
    )

    from app.persistence.repositories import SQLAlchemyWalletSessionRepository

    sql_repo = SQLAlchemyWalletSessionRepository(build_session_factory())
    sql_repo.save(
        WalletSessionRecord(
            user_id="u1",
            logged_in=True,
            wallet_xlayer_address="0xabc",
        )
    )

    service = RuntimeReadinessService(session_factory=build_session_factory())
    monkeypatch.setattr("app.services.readiness.shutil.which", lambda _: "/usr/local/bin/onchainos")
    monkeypatch.setattr(service, "_check_database", lambda: (True, "ok"))
    monkeypatch.setattr(service, "_check_checkpointer_backend", lambda: (True, "ok"))
    monkeypatch.setattr(service, "_check_onchainos_readonly_probe", lambda binary_path: (True, "ok"))
    monkeypatch.setattr(service, "_check_scraper_reachability", lambda: (True, "ok"))
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    service.telegram_client = type("ConfiguredTelegramClient", (), {})()

    result = service.run()

    assert result.checks["wallet_sessions"]["ok"] is True
    assert result.checks["trading_runtime_ready"]["ok"] is True
