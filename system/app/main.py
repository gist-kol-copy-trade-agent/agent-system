"""Application entrypoints for local bootstrap, HTTP webhook app, and Telegram bot."""

import os

from app.http_app import create_http_app
from app.services.app_runtime import build_application_runtime
from app.services.bootstrap import bootstrap_application
from app.telegram_bot import build_polling_bot


def main() -> None:
    bootstrap_application()


def _require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def build_http_app():
    callback_url = _require_env("APP_CALLBACK_URL_MESSAGES")
    webhook_secret = _require_env("APP_WEBHOOK_SECRET")
    runtime = build_application_runtime(
        callback_url=callback_url,
        callback_secret=webhook_secret,
    )
    return create_http_app(runtime, webhook_secret=webhook_secret)


def build_telegram_polling_app(*, bot_token: str):
    callback_url = _require_env("APP_CALLBACK_URL_MESSAGES")
    webhook_secret = _require_env("APP_WEBHOOK_SECRET")
    runtime = build_application_runtime(
        callback_url=callback_url,
        callback_secret=webhook_secret,
    )
    return build_polling_bot(runtime.telegram_router, bot_token=bot_token)


if __name__ == "__main__":
    main()
