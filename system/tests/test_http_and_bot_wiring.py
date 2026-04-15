from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from app.http_app import ScraperFollowProfileWebhookHandler, ScraperWebhookHandler
from app.schemas.commands import CommandResponse
from app.telegram_bot import TelegramCommandService
from app.services.webhook_intake import AcceptedWebhookEvent, WebhookIntakeService
from app.persistence.repositories import InMemorySourceMessageRepository
from app.schemas.webhook import ScraperFollowProfileWebhookPayload, ScraperWebhookPayload


@dataclass
class _FakeWorkflow:
    thread_id: str
    workflow_type: str


class _FakeSignalQueue:
    def enqueue_signal(self, accepted: AcceptedWebhookEvent) -> _FakeWorkflow:
        return _FakeWorkflow(thread_id=accepted.thread_id, workflow_type="signal-intake")


class _FakeSignalRuntime:
    def invoke(self, workflow: _FakeWorkflow) -> dict:
        return {"policy_gate_result": {"action": "execute"}}


class _FakeReadiness:
    def run(self):
        return type("Result", (), {"ok": True, "checks": {"onchainos_binary": {"ok": True, "detail": "/usr/bin/onchainos"}}})()


class _FakeFollowCommandService:
    def accept_profile_callback(self, payload: ScraperFollowProfileWebhookPayload):
        return type(
            "Accepted",
            (),
            {
                "source_id": payload.source_id,
                "channel_name": payload.channel_name,
                "suggested_conviction": "medium",
                "status": "awaiting_confirmation",
            },
        )()


class _FakeRuntime:
    def __init__(self) -> None:
        self.webhook_intake = WebhookIntakeService(InMemorySourceMessageRepository())
        self.signal_queue = _FakeSignalQueue()
        self.signal_runtime = _FakeSignalRuntime()
        self.readiness = _FakeReadiness()
        self.follow_command_service = _FakeFollowCommandService()


class _FakeRouter:
    def handle(self, envelope) -> CommandResponse:
        return CommandResponse(ok=True, command="status", message=f"echo:{envelope.raw_text}", payload={})


def test_scraper_webhook_handler_accepts_signed_payload() -> None:
    runtime = _FakeRuntime()
    handler = ScraperWebhookHandler(runtime, webhook_secret="secret")
    timestamp = datetime.now(UTC).isoformat()
    payload = ScraperWebhookPayload(
        event_id="evt-1",
        event_type="telegram.message.new",
        source_id="u1:alpha",
        channel_name="alpha",
        message_id="m1",
        message_text="buy eth",
        message_timestamp="2026-01-01T00:00:00Z",
        media_blobs=[],
        raw_payload={},
    )
    body = payload.model_dump_json().encode()
    signature = runtime.webhook_intake.build_signature(body=body, timestamp=timestamp, secret="secret")

    result = handler.handle(body=body, timestamp=timestamp, signature=signature)

    assert result.status_code == 202
    assert result.body["ok"] is True
    assert result.body["thread_id"] == "signal:evt-1"
    assert result.body["workflow_type"] == "signal-intake"
    assert result.body["status"] == "accepted"


def test_telegram_command_service_routes_text_to_router() -> None:
    service = TelegramCommandService(_FakeRouter())
    result = service.handle_text(user_id="u1", chat_id="c1", raw_text="/status")
    assert result.ok is True
    assert result.text == "echo:/status"


def test_follow_profile_webhook_handler_accepts_signed_payload() -> None:
    runtime = _FakeRuntime()
    follow_handler = ScraperFollowProfileWebhookHandler(runtime, webhook_secret="secret")
    timestamp = datetime.now(UTC).isoformat()
    payload = ScraperFollowProfileWebhookPayload(
        event_id="evt-follow-1",
        event_type="telegram.follow_profile.ready",
        source_id="u1:alpha",
        user_id="u1",
        channel_name="alpha",
        channel_url="https://t.me/alpha",
        profile_job_id="profile:u1:alpha",
        messages=[
            {
                "message_id": "m1",
                "message_text": "BUY ETH",
                "message_timestamp": "2026-01-01T00:00:00Z",
                "message_url": "https://t.me/alpha/1",
                "media_blobs": [],
            }
        ],
        raw_payload={},
    )
    body = payload.model_dump_json().encode()
    signature = runtime.webhook_intake.build_signature(body=body, timestamp=timestamp, secret="secret")

    result = follow_handler.handle(body=body, timestamp=timestamp, signature=signature)

    assert result.status_code == 202
    assert result.body["ok"] is True
    assert result.body["status"] == "awaiting_confirmation"
