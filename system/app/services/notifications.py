from __future__ import annotations

from typing import Any

from app.adapters.telegram.client import TelegramClient
from app.config.settings import get_settings
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
        mode: str | None = None,
    ) -> None:
        self.telegram_client = telegram_client
        self.notification_repository = notification_repository
        self.mode = mode or get_settings().notifications.mode

    def send_exit_notification(
        self,
        *,
        user_id: str,
        chat_id: str,
        position_id: str,
        message_text: str,
        explanation_payload: dict[str, Any] | None = None,
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
                    explanation_payload=explanation_payload,
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
        explanation_payload: dict[str, Any] | None = None,
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
                    explanation_payload=explanation_payload,
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
        explanation: dict[str, Any] | None = None,
    ) -> None:
        formatted_text = self._format_progress_message(
            stage=stage,
            raw_summary=message_text,
            details=details or {},
            explanation=explanation or {},
            mode=self.mode,
        )
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
                    explanation_payload=explanation or None,
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
        explanation_payload: dict[str, Any] | None = None,
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
                    explanation_payload=explanation_payload,
                    send_status=send_status,
                    sent_at=sent_at,
                )
            )

    @staticmethod
    def _format_progress_message(
        *,
        stage: str,
        raw_summary: str,
        details: dict,
        explanation: dict[str, Any],
        mode: str,
    ) -> str:
        stage_titles = {
            "parse": "🔎 Signal Parsed",
            "enrichment": "🧩 Context Ready",
            "decision": "🧠 Decision Drafted",
            "policy_gate": "🛡️ Policy Gate",
            "exit_ta": "📉 Exit Monitoring",
            "exit_decision": "🚪 Exit Decision Drafted",
            "exit_policy_gate": "🛡️ Exit Policy Gate",
        }
        next_steps = {
            "parse": "Lane classification and context gathering.",
            "enrichment": "TA scoring and trade decision.",
            "decision": "Policy gate validation.",
            "policy_gate": "Execute only if all hard checks pass.",
            "exit_ta": "Exit decision evaluation.",
            "exit_decision": "Exit policy gate validation.",
            "exit_policy_gate": "Persist hold/trailing state or execute sell.",
        }
        detail_labels = {
            "asset": "Asset",
            "message_type": "Type",
            "actionable": "Actionable",
            "confidence": "Confidence",
            "chain": "Chain Hint",
            "lane": "Lane",
            "price": "Spot Price",
            "wallet_ready": "Wallet Ready",
            "risk_scan": "Risk Scan",
            "kline_points": "Kline Points",
            "action": "Action",
            "reason": "Reason",
            "amount_usd": "Amount USD",
            "passed": "Passed",
            "failures": "Failures",
            "symbol": "Symbol",
            "pnl_pct": "PnL %",
            "drawdown_pct": "Drawdown %",
            "triggers": "Triggers",
        }

        lines = [stage_titles.get(stage, "📡 Strategy Update"), ""]
        summary = explanation.get("summary") or raw_summary
        if summary:
            lines.extend(["Summary", str(summary)])

        fact_lines = []
        for key, value in details.items():
            if value in (None, "", []):
                continue
            label = detail_labels.get(key, key.replace("_", " ").title())
            fact_lines.append(f"- {label}: {value}")
        if fact_lines:
            lines.extend(["", "Facts"] + fact_lines)

        evidence_points = [str(point) for point in (explanation.get("evidence_points") or []) if point]
        if mode in {"standard", "longform"} and evidence_points:
            max_points = 2 if mode == "standard" else 4
            lines.extend(["", "Reasoning"] + [f"- {point}" for point in evidence_points[:max_points]])

        long_form_message = explanation.get("long_form_message")
        if mode == "longform" and long_form_message:
            lines.extend(["", "Analyst Note", str(long_form_message)])

        next_step = next_steps.get(stage)
        if next_step:
            lines.extend(["", f"Next: {next_step}"])
        if mode == "compact":
            compact_lines = [stage_titles.get(stage, "📡 Strategy Update")]
            if summary:
                compact_lines.append(str(summary))
            if fact_lines[:3]:
                compact_lines.extend(fact_lines[:3])
            if next_step:
                compact_lines.append(f"Next: {next_step}")
            return "\n".join(compact_lines)
        return "\n".join(lines)


class RecordingTelegramClient(TelegramClient):
    def __init__(self) -> None:
        self.messages: list[dict[str, str]] = []

    def send_message(self, *, chat_id: str, text: str) -> None:
        self.messages.append({"chat_id": chat_id, "text": text})
