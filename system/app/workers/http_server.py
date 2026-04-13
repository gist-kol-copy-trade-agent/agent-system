from __future__ import annotations

import os

import uvicorn

from app.http_app import create_http_app
from app.services.app_runtime import build_application_runtime


def _get_env(name: str, default: str) -> str:
    value = os.getenv(name, default).strip()
    return value or default


def main() -> None:
    host = _get_env("APP_HOST", "0.0.0.0")
    port = int(_get_env("APP_PORT", "8000"))
    callback_url = _get_env("APP_CALLBACK_URL_MESSAGES", "http://localhost:8000/webhooks/scraper/messages")
    webhook_secret = _get_env("APP_WEBHOOK_SECRET", "dev-secret")

    runtime = build_application_runtime(
        callback_url=callback_url,
        callback_secret=webhook_secret,
    )
    app = create_http_app(runtime, webhook_secret=webhook_secret)
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
