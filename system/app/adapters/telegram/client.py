class TelegramClient:
    def send_message(self, *, chat_id: str, text: str) -> None:
        raise NotImplementedError("Telegram delivery is implemented in a later phase.")
