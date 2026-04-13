from __future__ import annotations

from app.adapters.telegram.client import TelegramClient
from app.persistence.repositories import TelegramNotificationRecord, TelegramNotificationRepository, utc_now_iso


class NotificationService:
    def __init__(
        self,
        *,
        telegram_client: TelegramClient,
        notification_repository: TelegramNotificationRepository | None = None,
    ) -> None:
        self.telegram_client = telegram_client
        self.notification_repository = notification_repository

    def send_exit_notification(
        self,
        *,
        user_id: str,
        chat_id: str,
        position_id: str,
        message_text: str,
    ) -> None:
        send_status = "sent"
        sent_at = utc_now_iso()
        try:
            self.telegram_client.send_message(chat_id=chat_id, text=message_text)
        except Exception:
            send_status = "failed"
            sent_at = None

        if self.notification_repository is not None:
            self.notification_repository.save(
                TelegramNotificationRecord(
                    user_id=user_id,
                    chat_id=chat_id,
                    related_signal_id=None,
                    related_position_id=position_id,
                    notification_type="exit_evaluation",
                    message_text=message_text,
                    send_status=send_status,
                    sent_at=sent_at,
                )
            )


class RecordingTelegramClient(TelegramClient):
    def __init__(self) -> None:
        self.messages: list[dict[str, str]] = []

    def send_message(self, *, chat_id: str, text: str) -> None:
        self.messages.append({"chat_id": chat_id, "text": text})
