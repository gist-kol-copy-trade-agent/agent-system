from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class RegisterChannelRequest(BaseModel):
    source_id: str
    channel_name: str
    channel_url: str | None = None
    callback_url: str
    callback_secret: str
    user_id: str
    bot_id: str | None = None
    enabled: bool = True


class RegisterChannelResponse(BaseModel):
    ok: bool
    scraper_subscription_id: str | None = None
    channel_name: str
    status: str
    error_code: str | None = None
    message: str | None = None


class UnregisterChannelRequest(BaseModel):
    source_id: str
    channel_name: str
    scraper_subscription_id: str | None = None
    user_id: str


class UnregisterChannelResponse(BaseModel):
    ok: bool
    status: str
    source_id: str
    error_code: str | None = None
    message: str | None = None


class FetchChannelMessagesRequest(BaseModel):
    request_id: str
    source_id: str
    channel_name: str
    channel_url: str | None = None
    lookback_days: int = 7
    limit: int = 500
    delivery_mode: Literal["async_webhook"] = "async_webhook"
    callback_url: str
    callback_secret: str
    user_id: str


class FetchChannelMessagesResponse(BaseModel):
    ok: bool
    request_id: str
    status: str
    delivery_mode: str
    error_code: str | None = None
    message: str | None = None


class ScrapedMediaBlob(BaseModel):
    kind: Literal["image"]
    mime_type: str
    telegram_file_id: str | None = None
    telegram_unique_file_id: str | None = None
    base64_data: str
    file_size_bytes: int | None = None
    width: int | None = None
    height: int | None = None
    caption: str | None = None


class ScrapedMessage(BaseModel):
    message_id: str
    message_text: str
    message_timestamp: str
    message_url: str | None = None
    media_blobs: list[ScrapedMediaBlob] = Field(default_factory=list)


class MessageWebhookPayload(BaseModel):
    event_id: str
    event_type: Literal["telegram.message.new"] = "telegram.message.new"
    scraper_subscription_id: str | None = None
    source_id: str
    channel_name: str
    channel_url: str | None = None
    message_id: str
    message_text: str
    message_timestamp: str
    message_url: str | None = None
    media_blobs: list[ScrapedMediaBlob] = Field(default_factory=list)
    raw_payload: dict[str, Any] = Field(default_factory=dict)


class HistoricalFollowProfileWebhookPayload(BaseModel):
    event_id: str
    event_type: Literal["telegram.follow_profile.ready"] = "telegram.follow_profile.ready"
    request_id: str
    source_id: str
    user_id: str
    channel_name: str
    channel_url: str | None = None
    lookback_days: int = 7
    message_count: int
    profile_job_id: str
    messages: list[ScrapedMessage]
    raw_payload: dict[str, Any] = Field(default_factory=dict)
