from __future__ import annotations

import json
import sys

from app.config.settings import get_settings
from app.observability.logging import configure_logging
from app.persistence.session import build_session_factory, create_all
from app.services.readiness import RuntimeReadinessService


def run_preflight() -> dict:
    settings = get_settings()
    configure_logging(settings.environment)
    create_all()
    readiness = RuntimeReadinessService(session_factory=build_session_factory()).run()
    return {
        "environment": settings.environment,
        "readiness": {
            "ok": readiness.ok,
            "checks": readiness.checks,
            "trading_runtime_ready": readiness.checks.get("trading_runtime_ready", {}).get("ok", False),
        },
    }


def main() -> None:
    payload = run_preflight()
    print(json.dumps(payload, indent=2, sort_keys=True))
    if not payload["readiness"]["trading_runtime_ready"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
