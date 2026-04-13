from __future__ import annotations

from app.adapters.telegram.client import TelegramClient
from app.persistence.repositories import TelegramNotificationRecord, TelegramNotificationRepository, utc_now_iso

try:
    from langgraph.func import task
except ModuleNotFoundError:  # pragma: no cover
    def task(func):
        return func


def _resolve_task_result(value):
    return value.result() if hasattr(value, "result") else value


@task
def _send_exit_notification_task(
    telegram_client: TelegramClient,
    *,
    chat_id: str,
    text: str,
) -> None:
    telegram_client.send_message(chat_id=chat_id, text=text)


@task
def _send_trade_notification_task(
    telegram_client: TelegramClient,
    *,
    chat_id: str,
    text: str,
) -> None:
    telegram_client.send_message(chat_id=chat_id, text=text)


@task
def _send_generic_notification_task(
    telegram_client: TelegramClient,
    *,
    chat_id: str,
    text: str,
) -> None:
    telegram_client.send_message(chat_id=chat_id, text=text)


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
            _resolve_task_result(_send_exit_notification_task(self.telegram_client, chat_id=chat_id, text=message_text))
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

    def send_trade_notification(
        self,
        *,
        user_id: str,
        chat_id: str,
        signal_id: str,
        position_id: str | None,
        message_text: str,
    ) -> None:
        send_status = "sent"
        sent_at = utc_now_iso()
        try:
            _resolve_task_result(_send_trade_notification_task(self.telegram_client, chat_id=chat_id, text=message_text))
        except Exception:
            send_status = "failed"
            sent_at = None

        if self.notification_repository is not None:
            self.notification_repository.save(
                TelegramNotificationRecord(
                    user_id=user_id,
                    chat_id=chat_id,
                    related_signal_id=signal_id,
                    related_position_id=position_id,
                    notification_type="trade_execution",
                    message_text=message_text,
                    send_status=send_status,
                    sent_at=sent_at,
                )
            )

    def send_progress_notification(
        self,
        *,
        user_id: str,
        chat_id: str,
        message_text: str,
        related_signal_id: str | None = None,
        related_position_id: str | None = None,
        stage: str,
        details: dict | None = None,
    ) -> None:
        formatted_text = self._format_progress_message(stage=stage, raw_summary=message_text, details=details or {})
        send_status = "sent"
        sent_at = utc_now_iso()
        try:
            _resolve_task_result(_send_trade_notification_task(self.telegram_client, chat_id=chat_id, text=formatted_text))
        except Exception:
            send_status = "failed"
            sent_at = None

        if self.notification_repository is not None:
            self.notification_repository.save(
                TelegramNotificationRecord(
                    user_id=user_id,
                    chat_id=chat_id,
                    related_signal_id=related_signal_id,
                    related_position_id=related_position_id,
                    notification_type=f"progress:{stage}",
                    message_text=formatted_text,
                    send_status=send_status,
                    sent_at=sent_at,
                )
            )

    def send_generic_notification(
        self,
        *,
        user_id: str,
        chat_id: str,
        notification_type: str,
        message_text: str,
        related_signal_id: str | None = None,
        related_position_id: str | None = None,
    ) -> None:
        send_status = "sent"
        sent_at = utc_now_iso()
        try:
            _resolve_task_result(_send_generic_notification_task(self.telegram_client, chat_id=chat_id, text=message_text))
        except Exception:
            send_status = "failed"
            sent_at = None

        if self.notification_repository is not None:
            self.notification_repository.save(
                TelegramNotificationRecord(
                    user_id=user_id,
                    chat_id=chat_id,
                    related_signal_id=related_signal_id,
                    related_position_id=related_position_id,
                    notification_type=notification_type,
                    message_text=message_text,
                    send_status=send_status,
                    sent_at=sent_at,
                )
            )

    @staticmethod
    def _format_progress_message(*, stage: str, raw_summary: str, details: dict) -> str:
        def block(title: str, value) -> str:
            return f"{title}: {value}"

        templates = {
            "parse": (
                "🔎 Signal Parsed\n"
                f"{block('Asset', details.get('asset', 'unknown'))}\n"
                f"{block('Type', details.get('message_type', 'unknown'))}\n"
                f"{block('Actionable', details.get('actionable', 'unknown'))}\n"
                f"{block('Confidence', details.get('confidence', 'n/a'))}\n"
                f"{block('Chain Hint', details.get('chain', 'unknown'))}\n"
                "Next: Lane classification and context gathering."
            ),
            "enrichment": (
                "🧩 Context Ready\n"
                f"{block('Lane', details.get('lane', 'unknown'))}\n"
                f"{block('Execution Chain', details.get('chain', 'unknown'))}\n"
                f"{block('Spot Price', details.get('price', 'n/a'))}\n"
                f"{block('Wallet Ready', details.get('wallet_ready', 'unknown'))}\n"
                f"{block('Risk Scan', details.get('risk_scan', 'n/a'))}\n"
                f"{block('Kline Points', details.get('kline_points', 'n/a'))}\n"
                "Next: TA scoring and trade decision."
            ),
            "decision": (
                "🧠 Decision Drafted\n"
                f"{block('Action', details.get('action', 'unknown'))}\n"
                f"{block('Reason', details.get('reason', 'unknown'))}\n"
                f"{block('Amount USD', details.get('amount_usd', 'n/a'))}\n"
                f"{block('Confidence', details.get('confidence', 'n/a'))}\n"
                "Next: Policy gate validation."
            ),
            "policy_gate": (
                "🛡️ Policy Gate\n"
                f"{block('Passed', details.get('passed', 'unknown'))}\n"
                f"{block('Action', details.get('action', 'unknown'))}\n"
                f"{block('Failures', details.get('failures', []))}\n"
                "Next: Execute only if all hard checks pass."
            ),
            "exit_ta": (
                "📉 Exit Monitoring\n"
                f"{block('Symbol', details.get('symbol', 'unknown'))}\n"
                f"{block('PnL %', details.get('pnl_pct', 'n/a'))}\n"
                f"{block('Drawdown %', details.get('drawdown_pct', 'n/a'))}\n"
                f"{block('Triggers', details.get('triggers', 'n/a'))}\n"
                "Next: Exit decision evaluation."
            ),
            "exit_decision": (
                "🚪 Exit Decision Drafted\n"
                f"{block('Action', details.get('action', 'unknown'))}\n"
                f"{block('Reason', details.get('reason', 'unknown'))}\n"
                f"{block('Confidence', details.get('confidence', 'n/a'))}\n"
                "Next: Exit policy gate validation."
            ),
            "exit_policy_gate": (
                "🛡️ Exit Policy Gate\n"
                f"{block('Passed', details.get('passed', 'unknown'))}\n"
                f"{block('Action', details.get('action', 'unknown'))}\n"
                f"{block('Failures', details.get('failures', []))}\n"
                "Next: Persist hold/trailing state or execute sell."
            ),
        }
        return templates.get(
            stage,
            (
                "📡 Strategy Update\n"
                f"{block('Stage', stage)}\n"
                f"{block('Details', raw_summary)}"
            ),
        )


class RecordingTelegramClient(TelegramClient):
    def __init__(self) -> None:
        self.messages: list[dict[str, str]] = []

    def send_message(self, *, chat_id: str, text: str) -> None:
        self.messages.append({"chat_id": chat_id, "text": text})
