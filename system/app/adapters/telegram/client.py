from abc import ABC, abstractmethod


class TelegramClient(ABC):
    @abstractmethod
    def send_message(self, *, chat_id: str, text: str) -> None:
        """Deliver a Telegram message to the resolved chat."""
