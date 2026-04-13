from dataclasses import dataclass


@dataclass
class ScraperRegistrationRequest:
    source_id: str
    channel_name: str
    channel_url: str | None
    callback_url: str
    callback_secret: str
    user_id: str


class ScraperClient:
    def register_channel(self, request: ScraperRegistrationRequest) -> dict:
        raise NotImplementedError("Scraper registration is implemented in a later phase.")

    def unregister_channel(self, *, source_id: str, channel_name: str) -> dict:
        raise NotImplementedError("Scraper unregistration is implemented in a later phase.")
