from __future__ import annotations

import uuid

from app.persistence.repositories import ChannelSubscriptionRecord, ChannelSubscriptionRepository, HistoricalFetchJobRecord, HistoricalFetchJobRepository
from app.schemas import (
    FetchChannelMessagesRequest,
    RegisterChannelRequest,
    RegisterChannelResponse,
    UnregisterChannelRequest,
    UnregisterChannelResponse,
)
from app.services.telethon_gateway import TelegramGateway


class SubscriptionService:
    def __init__(
        self,
        *,
        subscription_repository: ChannelSubscriptionRepository,
        history_repository: HistoricalFetchJobRepository,
        telegram_gateway: TelegramGateway,
    ) -> None:
        self.subscription_repository = subscription_repository
        self.history_repository = history_repository
        self.telegram_gateway = telegram_gateway

    async def register_channel(self, request: RegisterChannelRequest) -> RegisterChannelResponse:
        existing = self.subscription_repository.get_by_source_id(request.source_id)
        if existing is not None:
            updated = self.subscription_repository.save(
                ChannelSubscriptionRecord(
                    source_id=existing.source_id,
                    scraper_subscription_id=existing.scraper_subscription_id,
                    user_id=request.user_id,
                    channel_name=existing.channel_name,
                    channel_url=request.channel_url or existing.channel_url,
                    callback_url=request.callback_url,
                    callback_secret=request.callback_secret,
                    enabled=True,
                    status="registered",
                    last_seen_message_id=existing.last_seen_message_id,
                    last_seen_message_timestamp=existing.last_seen_message_timestamp,
                )
            )
            return RegisterChannelResponse(
                ok=True,
                scraper_subscription_id=updated.scraper_subscription_id,
                channel_name=updated.channel_name,
                status="registered",
            )
        channel_name, channel_url = await self.telegram_gateway.resolve_public_channel(request.channel_name, request.channel_url)
        record = self.subscription_repository.save(
            ChannelSubscriptionRecord(
                source_id=request.source_id,
                scraper_subscription_id=f"sub_{uuid.uuid4().hex[:16]}",
                user_id=request.user_id,
                channel_name=channel_name,
                channel_url=channel_url,
                callback_url=request.callback_url,
                callback_secret=request.callback_secret,
                enabled=bool(request.enabled),
                status="registered",
            )
        )
        return RegisterChannelResponse(
            ok=True,
            scraper_subscription_id=record.scraper_subscription_id,
            channel_name=record.channel_name,
            status="registered",
        )

    def unregister_channel(self, request: UnregisterChannelRequest) -> UnregisterChannelResponse:
        existing = self.subscription_repository.get_by_source_id(request.source_id)
        if existing is not None:
            self.subscription_repository.save(
                ChannelSubscriptionRecord(
                    source_id=existing.source_id,
                    scraper_subscription_id=existing.scraper_subscription_id,
                    user_id=existing.user_id,
                    channel_name=existing.channel_name,
                    channel_url=existing.channel_url,
                    callback_url=existing.callback_url,
                    callback_secret=existing.callback_secret,
                    enabled=False,
                    status="unregistered",
                    last_seen_message_id=existing.last_seen_message_id,
                    last_seen_message_timestamp=existing.last_seen_message_timestamp,
                )
            )
        return UnregisterChannelResponse(ok=True, status="unregistered", source_id=request.source_id)

    async def create_historical_fetch_job(self, request: FetchChannelMessagesRequest) -> None:
        existing = self.history_repository.get_by_request_id(request.request_id)
        if existing is not None:
            return
        channel_name, channel_url = await self.telegram_gateway.resolve_public_channel(request.channel_name, request.channel_url)
        self.history_repository.save(
            HistoricalFetchJobRecord(
                request_id=request.request_id,
                profile_job_id=f"profile_{uuid.uuid4().hex[:16]}",
                source_id=request.source_id,
                user_id=request.user_id,
                channel_name=channel_name,
                channel_url=channel_url,
                lookback_days=request.lookback_days,
                limit=request.limit,
                delivery_mode=request.delivery_mode,
                callback_url=request.callback_url,
                callback_secret=request.callback_secret,
                status="accepted",
            )
        )
