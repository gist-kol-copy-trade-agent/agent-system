from __future__ import annotations

from dataclasses import dataclass

from app.adapters.telegram.client import TelegramClient
from app.schemas.commands import CommandEnvelope
from app.services.telegram_commands import TelegramCommandRouter


@dataclass(frozen=True)
class TelegramCommandHandlingResult:
    ok: bool
    text: str
    payload: dict


class TelegramCommandService:
    def __init__(self, router: TelegramCommandRouter) -> None:
        self.router = router

    def handle_text(self, *, user_id: str, chat_id: str, raw_text: str) -> TelegramCommandHandlingResult:
        response = self.router.handle(CommandEnvelope(user_id=user_id, chat_id=chat_id, raw_text=raw_text))
        return TelegramCommandHandlingResult(ok=response.ok, text=response.message, payload=response.payload)


class PythonTelegramBotClient(TelegramClient):
    def __init__(self, bot_token: str) -> None:
        self.bot_token = bot_token

    def send_message(self, *, chat_id: str, text: str) -> None:
        try:
            from telegram import Bot
        except ModuleNotFoundError as exc:  # pragma: no cover
            raise RuntimeError("python-telegram-bot is not installed.") from exc
        bot = Bot(token=self.bot_token)
        import asyncio

        asyncio.run(bot.send_message(chat_id=chat_id, text=text))


def build_polling_bot(router: TelegramCommandRouter, *, bot_token: str):
    try:
        from telegram import Update
        from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
    except ModuleNotFoundError as exc:  # pragma: no cover
        raise RuntimeError("python-telegram-bot is not installed.") from exc

    command_service = TelegramCommandService(router)
    application = Application.builder().token(bot_token).build()

    async def _handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_user is None or update.effective_chat is None or update.message is None:
            return
        result = command_service.handle_text(
            user_id=str(update.effective_user.id),
            chat_id=str(update.effective_chat.id),
            raw_text=update.message.text or "",
        )
        await update.message.reply_text(result.text)

    for command in ("start", "status", "portfolio", "history", "follow", "stop", "trade-style"):
        application.add_handler(CommandHandler(command, _handle_text))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _handle_text))
    return application
