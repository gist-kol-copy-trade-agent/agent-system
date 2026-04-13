from app.adapters.scraper.client import ScraperClient, ScraperRegistrationRequest
from app.persistence.repositories import (
    InMemoryFollowedSourceRepository,
    InMemorySourceMessageRepository,
    InMemoryStrategyProfileRepository,
    InMemoryWorkflowRunRepository,
)
from app.schemas.commands import CommandEnvelope
from app.schemas.webhook import ScraperWebhookPayload
from app.services.source_registry import SourceRegistryService
from app.services.strategy_profiles import StrategyProfileService
from app.services.telegram_commands import TelegramCommandRouter
from app.services.webhook_intake import WebhookAuthError, WebhookIntakeService


class FakeScraperClient(ScraperClient):
    def register_channel(self, request: ScraperRegistrationRequest) -> dict:
        return {
            "ok": True,
            "scraper_subscription_id": f"sub:{request.source_id}",
            "channel_name": request.channel_name,
            "status": "registered",
        }

    def unregister_channel(self, *, source_id: str, channel_name: str) -> dict:
        return {"ok": True, "status": "unregistered", "source_id": source_id}


def build_router() -> TelegramCommandRouter:
    strategy_repo = InMemoryStrategyProfileRepository()
    source_repo = InMemoryFollowedSourceRepository()
    strategy_service = StrategyProfileService(strategy_repo)
    source_service = SourceRegistryService(source_repo, FakeScraperClient())
    return TelegramCommandRouter(
        strategy_profiles=strategy_service,
        source_registry=source_service,
        callback_url="https://bot.example.com/webhooks/scraper/messages",
        callback_secret="secret",
    )


def test_trade_style_preset_update() -> None:
    router = build_router()
    response = router.handle(CommandEnvelope(user_id="u1", chat_id="c1", raw_text="/trade-style safe"))
    assert response.ok is True
    assert response.command == "trade-style"
    assert response.payload["base_style"] == "safe"
    assert response.payload["max_amount_per_trade_usd"] == 300


def test_trade_style_override_update() -> None:
    router = build_router()
    response = router.handle(
        CommandEnvelope(user_id="u1", chat_id="c1", raw_text="/trade-style set max amount per trade to 250")
    )
    assert response.ok is True
    assert response.payload["max_amount_per_trade_usd"] == 250


def test_follow_and_stop_commands() -> None:
    router = build_router()
    follow = router.handle(CommandEnvelope(user_id="u1", chat_id="c1", raw_text="/follow alpha_kol"))
    assert follow.ok is True
    assert follow.payload["status"] == "active"
    assert follow.payload["scraper_subscription_id"] == "sub:u1:alpha_kol"

    stop = router.handle(CommandEnvelope(user_id="u1", chat_id="c1", raw_text="/stop alpha_kol"))
    assert stop.ok is True
    assert stop.payload["status"] == "inactive"


def test_webhook_signature_and_dedupe() -> None:
    intake = WebhookIntakeService(InMemorySourceMessageRepository(), InMemoryWorkflowRunRepository())
    body = b'{"event":"x"}'
    sig = intake.build_signature(body=body, timestamp="123", secret="secret")
    intake.verify_signature(body=body, timestamp="123", secret="secret", provided_signature=sig)

    payload = ScraperWebhookPayload(
        event_id="evt1",
        event_type="telegram.message.new",
        source_id="src1",
        channel_name="alpha_kol",
        message_id="m1",
        message_text="buy eth",
        message_timestamp="2026-01-01T00:00:00Z",
        raw_payload={},
    )
    assert intake.accept_event(payload) == "accepted"
    assert intake.accept_event(payload) == "duplicate_ignored"


def test_webhook_bad_signature_raises() -> None:
    intake = WebhookIntakeService(InMemorySourceMessageRepository(), InMemoryWorkflowRunRepository())
    try:
        intake.verify_signature(body=b"x", timestamp="1", secret="secret", provided_signature="bad")
    except WebhookAuthError:
        assert True
        return
    assert False, "expected WebhookAuthError"
