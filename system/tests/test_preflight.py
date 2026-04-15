from app.workers.preflight import run_preflight


def test_run_preflight_returns_readiness_payload(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.workers.preflight.RuntimeReadinessService.run",
        lambda self: type(
            "Result",
            (),
            {
                "ok": False,
                "checks": {
                    "database": {"ok": True, "detail": "ok"},
                    "trading_runtime_ready": {"ok": False, "detail": "missing prerequisites"},
                },
            },
        )(),
    )

    payload = run_preflight()

    assert "environment" in payload
    assert payload["readiness"]["ok"] is False
    assert payload["readiness"]["trading_runtime_ready"] is False
