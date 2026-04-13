from dataclasses import dataclass


@dataclass
class ScraperRegistrationRequest:
    source_id: str
    channel_name: str
    channel_url: str | None
    callback_url: str
    callback_secret: str
    user_id: str


@dataclass
class ScraperHistoricalProfileRequest:
    source_id: str
    channel_name: str
    channel_url: str | None
    callback_url: str
    callback_secret: str
    user_id: str
    lookback_days: int = 7


class ScraperClient:
    def request_channel_profile(self, request: ScraperHistoricalProfileRequest) -> dict:
        raise NotImplementedError("Scraper historical profiling is implemented in a later phase.")

    def register_channel(self, request: ScraperRegistrationRequest) -> dict:
        raise NotImplementedError("Scraper registration is implemented in a later phase.")

    def unregister_channel(self, *, source_id: str, channel_name: str) -> dict:
        raise NotImplementedError("Scraper unregistration is implemented in a later phase.")
