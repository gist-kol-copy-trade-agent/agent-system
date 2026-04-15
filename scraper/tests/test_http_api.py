from __future__ import annotations

import asyncio
from dataclasses import dataclass

from fastapi.testclient import TestClient

from app.http_app import create_app
from app.persistence.session import build_engine, build_session_factory
from app.config import get_settings


@dataclass
class FakeMessage:
    message_id: str
    message_text: str
    message_timestamp: str
    message_url: str | None
    media_blobs: list[dict]
    raw_payload: dict


class FakeGateway:
    async def check_readiness(self):
        return True, "ok"

    async def resolve_public_channel(self, channel_name: str, channel_url: str | None = None):
        return channel_name.lstrip("@"), channel_url or f"https://t.me/{channel_name.lstrip('@')}"

    async def fetch_recent_messages(self, *, channel_name: str, limit: int):
        return []

    async def fetch_historical_messages(self, *, channel_name: str, lookback_days: int, limit: int):
        return [
            FakeMessage(
                message_id="1",
                message_text="BUY ETH",
                message_timestamp="2026-04-14T00:00:00Z",
                message_url=f"https://t.me/{channel_name}/1",
                media_blobs=[],
                raw_payload={},
            )
        ]


def setup_function():
    get_settings.cache_clear()
    build_engine.cache_clear()
    build_session_factory.cache_clear()


def test_register_unregister_and_fetch(monkeypatch) -> None:
    monkeypatch.setenv("SCRAPER_DATABASE_URL", "sqlite+pysqlite:///:memory:")
    app = create_app(telegram_gateway=FakeGateway())
    client = TestClient(app)

    register = client.post(
        "/register/channel_name",
        json={
            "source_id": "src_1",
            "channel_name": "alpha",
            "channel_url": "https://t.me/alpha",
            "callback_url": "https://bot.example.com/webhooks/scraper/messages",
            "callback_secret": "secret",
            "user_id": "u1",
            "bot_id": "bot_main",
            "enabled": True,
        },
    )
    assert register.status_code == 200
    assert register.json()["ok"] is True
    assert register.json()["status"] == "registered"

    historical = client.post(
        "/fetch/channel_name/messages",
        json={
            "request_id": "req_1",
            "source_id": "src_1",
            "channel_name": "alpha",
            "channel_url": "https://t.me/alpha",
            "lookback_days": 7,
            "limit": 100,
            "delivery_mode": "async_webhook",
            "callback_url": "https://bot.example.com/webhooks/scraper/follow-profile",
            "callback_secret": "secret",
            "user_id": "u1",
        },
    )
    assert historical.status_code == 200
    assert historical.json()["ok"] is True
    assert historical.json()["status"] == "accepted"

    unregister = client.post(
        "/unregister/channel_name",
        json={
            "source_id": "src_1",
            "channel_name": "alpha",
            "scraper_subscription_id": register.json()["scraper_subscription_id"],
            "user_id": "u1",
        },
    )
    assert unregister.status_code == 200
    assert unregister.json()["ok"] is True
    assert unregister.json()["status"] == "unregistered"


def test_readiness_reflects_database_gateway_and_runtime(monkeypatch) -> None:
    monkeypatch.setenv("SCRAPER_DATABASE_URL", "sqlite+pysqlite:///:memory:")
    app = create_app(telegram_gateway=FakeGateway())
    client = TestClient(app)

    response = client.get("/readiness")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["checks"]["database"]["ok"] is True
    assert payload["checks"]["telegram_gateway"]["ok"] is True
    assert payload["checks"]["runtime_loops"]["ok"] is True


def test_media_blob_extraction_handles_images() -> None:
    from app.services.telethon_gateway import TelethonPublicChannelGateway

    class FakeClient:
        async def download_media(self, item, file=bytes):
            return b"fake-image-bytes"

    class FakePhoto:
        id = 123
        sizes = [type("Size", (), {"w": 800, "h": 600})()]

    item = type(
        "Msg",
        (),
        {
            "media": object(),
            "photo": FakePhoto(),
            "document": None,
            "message": "chart",
        },
    )()

    blobs = asyncio.run(TelethonPublicChannelGateway()._extract_media_blobs(FakeClient(), item))

    assert len(blobs) == 1
    assert blobs[0]["kind"] == "image"
    assert blobs[0]["file_size_bytes"] == len(b"fake-image-bytes")
    assert blobs[0]["width"] == 800
    assert blobs[0]["height"] == 600
