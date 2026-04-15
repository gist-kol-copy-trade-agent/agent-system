from abc import ABC, abstractmethod
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


class ScraperClient(ABC):
    @abstractmethod
    def request_channel_profile(self, request: ScraperHistoricalProfileRequest) -> dict:
        """Start historical profiling for a source."""

    @abstractmethod
    def register_channel(self, request: ScraperRegistrationRequest) -> dict:
        """Register a live channel subscription with the scraper."""

    @abstractmethod
    def unregister_channel(self, *, source_id: str, channel_name: str) -> dict:
        """Unregister a live channel subscription from the scraper."""
