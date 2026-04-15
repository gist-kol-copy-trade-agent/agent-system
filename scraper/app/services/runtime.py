from __future__ import annotations

import asyncio
import uuid

from app.config import get_settings
from app.persistence.repositories import ChannelSubscriptionRecord, ChannelSubscriptionRepository, HistoricalFetchJobRecord, HistoricalFetchJobRepository
from app.schemas import HistoricalFollowProfileWebhookPayload, MessageWebhookPayload, ScrapedMessage
from app.services.telethon_gateway import TelegramGateway
from app.services.webhook_delivery import WebhookDeliveryService


class ScraperRuntime:
    def __init__(
        self,
        *,
        subscription_repository: ChannelSubscriptionRepository,
        history_repository: HistoricalFetchJobRepository,
        telegram_gateway: TelegramGateway,
        delivery_service: WebhookDeliveryService,
    ) -> None:
        self.subscription_repository = subscription_repository
        self.history_repository = history_repository
        self.telegram_gateway = telegram_gateway
        self.delivery_service = delivery_service
        self._tasks: list[asyncio.Task] = []
        self._running = False

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._tasks = [
            asyncio.create_task(self._subscription_loop(), name="subscription_loop"),
            asyncio.create_task(self._history_loop(), name="history_loop"),
        ]

    async def stop(self) -> None:
        self._running = False
        for task in self._tasks:
            task.cancel()
        self._tasks.clear()

    async def _subscription_loop(self) -> None:
        while self._running:
            records = self.subscription_repository.list_enabled()
            for record in records:
                await self._process_subscription(record)
            await asyncio.sleep(get_settings().scraper_poll_interval_seconds)

    async def _history_loop(self) -> None:
        while self._running:
            jobs = self.history_repository.list_pending(limit=get_settings().scraper_history_fetch_batch_size)
            for job in jobs:
                await self._process_history_job(job)
            await asyncio.sleep(get_settings().scraper_poll_interval_seconds)

    async def _process_subscription(self, record: ChannelSubscriptionRecord) -> None:
        try:
            messages = await self.telegram_gateway.fetch_recent_messages(
                channel_name=record.channel_name,
                limit=get_settings().scraper_live_fetch_limit,
            )
            messages = sorted(messages, key=lambda item: int(item.message_id))
            for item in messages:
                if record.last_seen_message_id is not None and int(item.message_id) <= int(record.last_seen_message_id):
                    continue
                payload = MessageWebhookPayload(
                    event_id=f"evt_{uuid.uuid4().hex[:20]}",
                    scraper_subscription_id=record.scraper_subscription_id,
                    source_id=record.source_id,
                    channel_name=record.channel_name,
                    channel_url=record.channel_url,
                    message_id=item.message_id,
                    message_text=item.message_text,
                    message_timestamp=item.message_timestamp,
                    message_url=item.message_url,
                    media_blobs=item.media_blobs,
                    raw_payload=item.raw_payload,
                )
                success, _, error = await self.delivery_service.post_json(
                    delivery_key=f"{record.scraper_subscription_id}:{item.message_id}",
                    callback_url=record.callback_url,
                    callback_secret=record.callback_secret,
                    payload=payload.model_dump(),
                    extra_headers={"X-Event-Id": payload.event_id},
                )
                if success:
                    record.last_seen_message_id = item.message_id
                    record.last_seen_message_timestamp = item.message_timestamp
                    record.last_error = None
                else:
                    record.last_error = error or "delivery_failed"
                self.subscription_repository.save(record)
        except Exception as exc:  # pragma: no cover - runtime integration path
            record.last_error = str(exc)
            self.subscription_repository.save(record)

    async def _process_history_job(self, job: HistoricalFetchJobRecord) -> None:
        try:
            messages = await self.telegram_gateway.fetch_historical_messages(
                channel_name=job.channel_name,
                lookback_days=job.lookback_days,
                limit=job.limit,
            )
            payload = HistoricalFollowProfileWebhookPayload(
                event_id=f"evt_profile_{uuid.uuid4().hex[:20]}",
                request_id=job.request_id,
                source_id=job.source_id,
                user_id=job.user_id,
                channel_name=job.channel_name,
                channel_url=job.channel_url,
                lookback_days=job.lookback_days,
                message_count=len(messages),
                profile_job_id=job.profile_job_id,
                messages=[
                    ScrapedMessage(
                        message_id=item.message_id,
                        message_text=item.message_text,
                        message_timestamp=item.message_timestamp,
                        message_url=item.message_url,
                        media_blobs=item.media_blobs,
                    )
                    for item in messages
                ],
                raw_payload={"source": "telethon"},
            )
            success, _, error = await self.delivery_service.post_json(
                delivery_key=job.request_id,
                callback_url=job.callback_url,
                callback_secret=job.callback_secret,
                payload=payload.model_dump(),
                extra_headers={"X-Request-Id": job.request_id},
            )
            job.status = "completed" if success else "failed"
            job.message_count = len(messages)
            job.last_error = None if success else (error or "delivery_failed")
            self.history_repository.save(job)
        except Exception as exc:  # pragma: no cover - runtime integration path
            job.status = "failed"
            job.last_error = str(exc)
            self.history_repository.save(job)
