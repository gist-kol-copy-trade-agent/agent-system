"""Application entrypoints for local bootstrap, HTTP webhook app, and Telegram bot."""

from app.http_app import create_http_app
from app.services.app_runtime import build_application_runtime
from app.services.bootstrap import bootstrap_application
from app.telegram_bot import build_polling_bot


def main() -> None:
    bootstrap_application()


def build_http_app():
    runtime = build_application_runtime(
        callback_url="http://localhost:8000/webhooks/scraper/messages",
        callback_secret="dev-secret",
    )
    return create_http_app(runtime, webhook_secret="dev-secret")


def build_telegram_polling_app(*, bot_token: str):
    runtime = build_application_runtime(
        callback_url="http://localhost:8000/webhooks/scraper/messages",
        callback_secret="dev-secret",
    )
    return build_polling_bot(runtime.telegram_router, bot_token=bot_token)


if __name__ == "__main__":
    main()
