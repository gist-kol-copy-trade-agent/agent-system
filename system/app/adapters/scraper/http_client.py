from __future__ import annotations

from dataclasses import asdict

import httpx

from app.adapters.scraper.client import ScraperClient, ScraperHistoricalProfileRequest, ScraperRegistrationRequest


class HTTPScraperClient(ScraperClient):
    def __init__(self, *, base_url: str, timeout_seconds: int = 15) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def request_channel_profile(self, request: ScraperHistoricalProfileRequest) -> dict:
        body = {
            "request_id": f"follow_profile_req:{request.source_id}",
            **asdict(request),
            "delivery_mode": "async_webhook",
        }
        return self._post("/fetch/channel_name/messages", body)

    def register_channel(self, request: ScraperRegistrationRequest) -> dict:
        body = {
            **asdict(request),
            "bot_id": "bot_main",
            "enabled": True,
        }
        return self._post("/register/channel_name", body)

    def unregister_channel(self, *, source_id: str, channel_name: str) -> dict:
        return self._post(
            "/unregister/channel_name",
            {
                "source_id": source_id,
                "channel_name": channel_name,
                "scraper_subscription_id": None,
                "user_id": source_id.split(":", 1)[0] if ":" in source_id else source_id,
            },
        )

    def _post(self, path: str, body: dict) -> dict:
        with httpx.Client(base_url=self.base_url, timeout=self.timeout_seconds) as client:
            response = client.post(path, json=body)
            response.raise_for_status()
            return response.json()
