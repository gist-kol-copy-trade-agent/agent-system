from __future__ import annotations

from app.adapters.scraper.client import ScraperClient, ScraperRegistrationRequest
from app.persistence.repositories import FollowedSourceRecord, FollowedSourceRepository, utc_now_iso


class SourceRegistryService:
    def __init__(self, repository: FollowedSourceRepository, scraper_client: ScraperClient) -> None:
        self.repository = repository
        self.scraper_client = scraper_client

    def follow(self, *, user_id: str, channel_name: str, channel_url: str | None, callback_url: str, callback_secret: str) -> FollowedSourceRecord:
        source_id = f"{user_id}:{channel_name}"
        record = self.repository.get_by_source_id(source_id) or FollowedSourceRecord(
            source_id=source_id,
            user_id=user_id,
            channel_name=channel_name,
            channel_url=channel_url,
            status="pending",
        )
        registration = self.scraper_client.register_channel(
            ScraperRegistrationRequest(
                source_id=source_id,
                channel_name=channel_name,
                channel_url=channel_url,
                callback_url=callback_url,
                callback_secret=callback_secret,
                user_id=user_id,
            )
        )
        if registration.get("ok"):
            record.status = "active"
            record.scraper_subscription_id = registration.get("scraper_subscription_id")
            record.registered_at = utc_now_iso()
        else:
            record.status = "error"
        return self.repository.save(record)

    def register_existing(
        self,
        *,
        record: FollowedSourceRecord,
        callback_url: str,
        callback_secret: str,
    ) -> FollowedSourceRecord:
        registration = self.scraper_client.register_channel(
            ScraperRegistrationRequest(
                source_id=record.source_id,
                channel_name=record.channel_name,
                channel_url=record.channel_url,
                callback_url=callback_url,
                callback_secret=callback_secret,
                user_id=record.user_id,
            )
        )
        if registration.get("ok"):
            record.status = "active"
            record.scraper_subscription_id = registration.get("scraper_subscription_id")
            record.registered_at = utc_now_iso()
        else:
            record.status = "error"
        return self.repository.save(record)

    def stop(self, *, user_id: str, channel_name: str) -> FollowedSourceRecord:
        source_id = f"{user_id}:{channel_name}"
        record = self.repository.get_by_source_id(source_id)
        if not record:
            record = FollowedSourceRecord(
                source_id=source_id,
                user_id=user_id,
                channel_name=channel_name,
                channel_url=None,
                status="inactive",
            )
        else:
            response = self.scraper_client.unregister_channel(source_id=record.source_id, channel_name=record.channel_name)
            if response.get("ok"):
                record.status = "inactive"
                record.unsubscribed_at = utc_now_iso()
            else:
                record.status = "error"
        return self.repository.save(record)
