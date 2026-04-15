from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

from app.config import get_settings


@dataclass
class TelethonMessage:
    message_id: str
    message_text: str
    message_timestamp: str
    message_url: str | None
    media_blobs: list[dict]
    raw_payload: dict


class TelegramGateway(Protocol):
    async def resolve_public_channel(self, channel_name: str, channel_url: str | None = None) -> tuple[str, str | None]: ...

    async def fetch_recent_messages(self, *, channel_name: str, limit: int) -> list[TelethonMessage]: ...

    async def fetch_historical_messages(self, *, channel_name: str, lookback_days: int, limit: int) -> list[TelethonMessage]: ...

    async def check_readiness(self) -> tuple[bool, str]: ...


class TelethonGatewayError(Exception):
    pass


class TelethonPublicChannelGateway:
    def __init__(self) -> None:
        self._client = None

    async def resolve_public_channel(self, channel_name: str, channel_url: str | None = None) -> tuple[str, str | None]:
        client = await self._get_client()
        entity = await client.get_entity(channel_name)
        username = getattr(entity, "username", None) or channel_name.lstrip("@")
        return username, (channel_url or f"https://t.me/{username}")

    async def fetch_recent_messages(self, *, channel_name: str, limit: int) -> list[TelethonMessage]:
        client = await self._get_client()
        entity = await client.get_entity(channel_name)
        messages = await client.get_messages(entity, limit=limit)
        result: list[TelethonMessage] = []
        for item in messages:
            if not getattr(item, "message", None) and not getattr(item, "media", None):
                continue
            result.append(await self._normalize(channel_name, item))
        return result

    async def fetch_historical_messages(self, *, channel_name: str, lookback_days: int, limit: int) -> list[TelethonMessage]:
        client = await self._get_client()
        entity = await client.get_entity(channel_name)
        cutoff = datetime.now(UTC) - timedelta(days=lookback_days)
        messages = await client.get_messages(entity, limit=limit)
        result: list[TelethonMessage] = []
        for item in messages:
            when = getattr(item, "date", None)
            if when is None or when < cutoff:
                continue
            if not getattr(item, "message", None) and not getattr(item, "media", None):
                continue
            result.append(await self._normalize(channel_name, item))
        return result

    async def _get_client(self):
        if self._client is not None:
            return self._client
        settings = get_settings()
        if settings.scraper_telegram_api_id is None or not settings.scraper_telegram_api_hash:
            raise TelethonGatewayError("Telethon credentials are not configured.")
        try:
            from telethon import TelegramClient
        except ModuleNotFoundError as exc:  # pragma: no cover
            raise TelethonGatewayError("Telethon is not installed.") from exc
        self._client = TelegramClient(
            settings.scraper_telegram_session_name,
            settings.scraper_telegram_api_id,
            settings.scraper_telegram_api_hash,
        )
        await self._client.start()
        return self._client

    async def check_readiness(self) -> tuple[bool, str]:
        settings = get_settings()
        if settings.scraper_telegram_api_id is None or not settings.scraper_telegram_api_hash:
            return False, "Telethon credentials are not configured."
        try:
            await self._get_client()
        except Exception as exc:  # pragma: no cover - integration path
            return False, str(exc)
        return True, "ok"

    async def _extract_media_blobs(self, client, item) -> list[dict]:
        media = getattr(item, "media", None)
        if media is None:
            return []
        photo = getattr(item, "photo", None)
        document = getattr(item, "document", None)
        mime_type = getattr(document, "mime_type", None)
        is_image_document = isinstance(mime_type, str) and mime_type.startswith("image/")
        if photo is None and not is_image_document:
            return []

        settings = get_settings()
        file_bytes = await client.download_media(item, file=bytes)
        if not file_bytes or len(file_bytes) > settings.scraper_media_blob_max_bytes:
            return []

        caption = getattr(item, "message", None)
        width = None
        height = None
        telegram_file_id = None
        telegram_unique_file_id = None
        resolved_mime_type = "image/jpeg" if photo is not None else (mime_type or "image/*")

        if photo is not None:
            sizes = getattr(photo, "sizes", None) or []
            if sizes:
                last_size = sizes[-1]
                width = getattr(last_size, "w", None)
                height = getattr(last_size, "h", None)
            telegram_file_id = str(getattr(photo, "id", "")) or None
        elif document is not None:
            telegram_file_id = str(getattr(document, "id", "")) or None
            for attr in getattr(document, "attributes", []) or []:
                if hasattr(attr, "w") and hasattr(attr, "h"):
                    width = getattr(attr, "w", None)
                    height = getattr(attr, "h", None)
                    break

        return [
            {
                "kind": "image",
                "mime_type": resolved_mime_type,
                "telegram_file_id": telegram_file_id,
                "telegram_unique_file_id": telegram_unique_file_id,
                "base64_data": base64.b64encode(file_bytes).decode("ascii"),
                "file_size_bytes": len(file_bytes),
                "width": width,
                "height": height,
                "caption": str(caption) if caption else None,
            }
        ]

    async def _normalize(self, channel_name: str, item) -> TelethonMessage:
        username = channel_name.lstrip("@")
        client = await self._get_client()
        media_blobs = await self._extract_media_blobs(client, item)
        return TelethonMessage(
            message_id=str(item.id),
            message_text=str(item.message),
            message_timestamp=item.date.astimezone(UTC).isoformat().replace("+00:00", "Z"),
            message_url=f"https://t.me/{username}/{item.id}",
            media_blobs=media_blobs,
            raw_payload={
                "id": item.id,
                "date": item.date.astimezone(UTC).isoformat(),
                "peer_id": str(getattr(item, "peer_id", "")),
                "has_media": bool(getattr(item, "media", None)),
            },
        )
