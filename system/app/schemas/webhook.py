from typing import Literal

from pydantic import BaseModel, Field


class ScraperMediaBlob(BaseModel):
    kind: Literal["image"]
    mime_type: str
    telegram_file_id: str | None = None
    telegram_unique_file_id: str | None = None
    base64_data: str
    file_size_bytes: int | None = None
    width: int | None = None
    height: int | None = None
    caption: str | None = None


class ScraperWebhookPayload(BaseModel):
    event_id: str
    event_type: Literal["telegram.message.new"]
    scraper_subscription_id: str | None = None
    source_id: str
    channel_name: str
    channel_url: str | None = None
    message_id: str
    message_text: str
    message_timestamp: str
    message_url: str | None = None
    media_blobs: list[ScraperMediaBlob] = Field(default_factory=list)
    raw_payload: dict


class ScraperHistoricalMessageSample(BaseModel):
    message_id: str
    message_text: str
    message_timestamp: str
    message_url: str | None = None
    media_blobs: list[ScraperMediaBlob] = Field(default_factory=list)


class ScraperFollowProfileWebhookPayload(BaseModel):
    event_id: str
    event_type: Literal["telegram.follow_profile.ready"]
    source_id: str
    user_id: str
    channel_name: str
    channel_url: str | None = None
    profile_job_id: str
    lookback_days: int = 7
    messages: list[ScraperHistoricalMessageSample]
    raw_payload: dict
