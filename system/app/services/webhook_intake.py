from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass

from app.graphs.runtime import build_thread_id
from app.persistence.repositories import SourceMessageRecord, SourceMessageRepository, utc_now_iso
from app.schemas.webhook import ScraperWebhookPayload


class WebhookAuthError(Exception):
    pass


@dataclass(frozen=True)
class AcceptedWebhookEvent:
    payload: ScraperWebhookPayload
    thread_id: str
    deduplicated: bool


class WebhookIntakeService:
    def __init__(self, message_repository: SourceMessageRepository) -> None:
        self.message_repository = message_repository

    @staticmethod
    def build_signature(*, body: bytes, timestamp: str, secret: str) -> str:
        payload = timestamp.encode() + b"." + body
        return hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()

    def verify_signature(self, *, body: bytes, timestamp: str, secret: str, provided_signature: str) -> None:
        expected = self.build_signature(body=body, timestamp=timestamp, secret=secret)
        if not hmac.compare_digest(expected, provided_signature):
            raise WebhookAuthError("Invalid scraper signature.")

    def accept_event(self, payload: ScraperWebhookPayload) -> AcceptedWebhookEvent | None:
        if self.message_repository.has_event(payload.event_id):
            return None

        self.message_repository.save(
            SourceMessageRecord(
                event_id=payload.event_id,
                source_id=payload.source_id,
                message_id=payload.message_id,
                message_timestamp=payload.message_timestamp,
                message_text=payload.message_text,
                message_url=payload.message_url,
                raw_payload=payload.model_dump(),
                received_at=utc_now_iso(),
            )
        )
        return AcceptedWebhookEvent(
            payload=payload,
            thread_id=build_thread_id("signal", payload.event_id),
            deduplicated=False,
        )
