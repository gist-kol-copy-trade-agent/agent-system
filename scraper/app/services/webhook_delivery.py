from __future__ import annotations

from datetime import UTC, datetime

import httpx

from app.config import get_settings
from app.persistence.repositories import DeliveryAttemptRepository
from app.services.security import build_signature


class WebhookDeliveryService:
    def __init__(self, repository: DeliveryAttemptRepository) -> None:
        self.repository = repository

    async def post_json(
        self,
        *,
        delivery_key: str,
        callback_url: str,
        callback_secret: str,
        payload: dict,
        extra_headers: dict[str, str] | None = None,
    ) -> tuple[bool, int | None, str | None]:
        body = __import__("json").dumps(payload, separators=(",", ":"), ensure_ascii=True).encode()
        timestamp = str(int(datetime.now(UTC).timestamp()))
        headers = {
            "Content-Type": "application/json",
            "X-Scraper-Timestamp": timestamp,
            "X-Scraper-Signature": build_signature(body=body, timestamp=timestamp, secret=callback_secret),
        }
        if extra_headers:
            headers.update(extra_headers)
        timeout = get_settings().scraper_webhook_timeout_seconds
        success = False
        status_code = None
        response_body = None
        error_message = None
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(callback_url, content=body, headers=headers)
                status_code = response.status_code
                response_body = response.text
                success = 200 <= response.status_code < 300
        except Exception as exc:  # pragma: no cover - network runtime path
            error_message = str(exc)
        self.repository.save(
            delivery_key=delivery_key,
            callback_url=callback_url,
            event_type=str(payload.get("event_type") or "unknown"),
            status_code=status_code,
            success=success,
            request_headers=headers,
            request_payload=payload,
            response_body=response_body,
            error_message=error_message,
        )
        return success, status_code, error_message
