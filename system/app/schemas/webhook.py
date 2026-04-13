from typing import Literal

from pydantic import BaseModel


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
    raw_payload: dict


class ScraperHistoricalMessageSample(BaseModel):
    message_id: str
    message_text: str
    message_timestamp: str
    message_url: str | None = None


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
