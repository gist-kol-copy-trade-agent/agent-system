from pydantic import BaseModel


class ScraperRegistrationPayload(BaseModel):
    source_id: str
    channel_name: str
    channel_url: str | None = None
    callback_url: str
    callback_secret: str
    user_id: str
    bot_id: str
    enabled: bool = True


class ScraperUnregisterPayload(BaseModel):
    source_id: str
    channel_name: str
    scraper_subscription_id: str | None = None
    user_id: str
