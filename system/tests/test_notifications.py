from app.persistence.repositories import InMemoryTelegramNotificationRepository
from app.services.notifications import NotificationService, RecordingTelegramClient


def test_progress_notification_renders_structured_explanation() -> None:
    repo = InMemoryTelegramNotificationRepository()
    service = NotificationService(
        telegram_client=RecordingTelegramClient(),
        notification_repository=repo,
    )

    service.send_progress_notification(
        user_id="u1",
        chat_id="c1",
        related_signal_id="sig-1",
        related_position_id=None,
        stage="decision",
        message_text="Decision formed.",
        details={
            "action": "execute",
            "reason": "READY_FOR_POLICY_GATE",
            "amount_usd": 100,
            "confidence": 0.91,
        },
        explanation={
            "summary": "The setup is constructive with acceptable TA and bounded sizing.",
            "evidence_points": [
                "Momentum remains positive across the recent kline window.",
                "Risk scan does not show a blocker.",
                "Sizing is capped by the user profile.",
            ],
        },
    )

    record = repo._records[0]
    assert record.notification_type == "progress:decision"
    assert record.explanation_payload is not None
    assert record.explanation_payload["summary"] == "The setup is constructive with acceptable TA and bounded sizing."
    assert "🧠 Decision Drafted" in record.message_text
    assert "Summary" in record.message_text
    assert "Reasoning" in record.message_text
    assert "Momentum remains positive" in record.message_text


def test_progress_notification_demo_mode_renders_analyst_note() -> None:
    repo = InMemoryTelegramNotificationRepository()
    service = NotificationService(
        telegram_client=RecordingTelegramClient(),
        notification_repository=repo,
        mode="demo_longform",
    )

    service.send_progress_notification(
        user_id="u1",
        chat_id="c1",
        related_signal_id="sig-1",
        related_position_id=None,
        stage="enrichment",
        message_text="Context ready.",
        details={"lane": "major", "chain": "xlayer", "price": 3200.0},
        explanation={
            "summary": "Context is ready with market, wallet, and risk inputs.",
            "evidence_points": ["Wallet is authenticated.", "Kline window is non-empty."],
            "long_form_message": "The market looks orderly and the wallet is ready, so the system can move into TA and decisioning.",
        },
    )

    record = repo._records[0]
    assert "Analyst Note" in record.message_text
    assert "The market looks orderly" in record.message_text


def test_progress_notification_compact_mode_omits_reasoning_sections() -> None:
    repo = InMemoryTelegramNotificationRepository()
    service = NotificationService(
        telegram_client=RecordingTelegramClient(),
        notification_repository=repo,
        mode="compact",
    )

    service.send_progress_notification(
        user_id="u1",
        chat_id="c1",
        related_signal_id="sig-1",
        related_position_id=None,
        stage="decision",
        message_text="Decision formed.",
        details={"action": "execute", "reason": "READY_FOR_POLICY_GATE", "amount_usd": 100},
        explanation={
            "summary": "Trade is ready for policy validation.",
            "evidence_points": ["Momentum remains positive."],
            "long_form_message": "This should not appear in compact mode.",
        },
    )

    record = repo._records[0]
    assert "Reasoning" not in record.message_text
    assert "Analyst Note" not in record.message_text
    assert "Trade is ready for policy validation." in record.message_text
