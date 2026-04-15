from __future__ import annotations

import os

from app.services.app_runtime import build_application_runtime
from app.telegram_bot import build_polling_bot


def _require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def main() -> None:
    bot_token = _require_env("TELEGRAM_BOT_TOKEN")
    callback_url = _require_env("APP_CALLBACK_URL_MESSAGES")
    webhook_secret = _require_env("APP_WEBHOOK_SECRET")

    runtime = build_application_runtime(
        callback_url=callback_url,
        callback_secret=webhook_secret,
    )
    app = build_polling_bot(runtime.telegram_router, bot_token=bot_token)
    app.run_polling()


if __name__ == "__main__":
    main()
