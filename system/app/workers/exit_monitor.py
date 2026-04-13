from __future__ import annotations

import os
import time
from datetime import datetime, timezone

from app.config.settings import get_settings
from app.services.app_runtime import build_application_runtime


def _get_env(name: str, default: str) -> str:
    value = os.getenv(name, default).strip()
    return value or default


def _cycle_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def main() -> None:
    callback_url = _get_env("APP_CALLBACK_URL_MESSAGES", "http://localhost:8000/webhooks/scraper/messages")
    webhook_secret = _get_env("APP_WEBHOOK_SECRET", "dev-secret")
    runtime = build_application_runtime(
        callback_url=callback_url,
        callback_secret=webhook_secret,
    )

    settings = get_settings()
    interval = max(settings.monitoring.position_refresh_interval_seconds, 10)

    while True:
        runtime.position_monitor.run_cycle(cycle_id=_cycle_id())
        time.sleep(interval)


if __name__ == "__main__":
    main()
