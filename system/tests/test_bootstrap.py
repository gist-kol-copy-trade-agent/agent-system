from app.services.bootstrap import bootstrap_application


def test_bootstrap_returns_readiness_payload() -> None:
    result = bootstrap_application()
    assert "environment" in result
    assert "readiness" in result
    assert "ok" in result["readiness"]
    assert "checks" in result["readiness"]
