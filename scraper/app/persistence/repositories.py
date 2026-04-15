from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.persistence.models import ChannelSubscription, DeliveryAttempt, HistoricalFetchJob


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class ChannelSubscriptionRecord:
    source_id: str
    scraper_subscription_id: str
    user_id: str
    channel_name: str
    channel_url: str | None
    callback_url: str
    callback_secret: str
    enabled: bool
    status: str
    last_seen_message_id: str | None = None
    last_seen_message_timestamp: str | None = None
    last_error: str | None = None


@dataclass
class HistoricalFetchJobRecord:
    request_id: str
    profile_job_id: str
    source_id: str
    user_id: str
    channel_name: str
    channel_url: str | None
    lookback_days: int
    limit: int
    delivery_mode: str
    callback_url: str
    callback_secret: str
    status: str
    message_count: int | None = None
    last_error: str | None = None


class ChannelSubscriptionRepository:
    def __init__(self, session_factory: sessionmaker) -> None:
        self.session_factory = session_factory

    def get_by_source_id(self, source_id: str) -> ChannelSubscriptionRecord | None:
        with self.session_factory() as session:
            model = session.scalar(select(ChannelSubscription).where(ChannelSubscription.source_id == source_id))
            return self._to_record(model) if model is not None else None

    def list_enabled(self) -> list[ChannelSubscriptionRecord]:
        with self.session_factory() as session:
            models = session.scalars(
                select(ChannelSubscription).where(ChannelSubscription.enabled.is_(True)).order_by(ChannelSubscription.id.asc())
            ).all()
            return [self._to_record(model) for model in models]

    def save(self, record: ChannelSubscriptionRecord) -> ChannelSubscriptionRecord:
        with self.session_factory() as session:
            model = session.scalar(select(ChannelSubscription).where(ChannelSubscription.source_id == record.source_id))
            if model is None:
                model = ChannelSubscription(
                    source_id=record.source_id,
                    scraper_subscription_id=record.scraper_subscription_id,
                    user_id=record.user_id,
                    channel_name=record.channel_name,
                    channel_url=record.channel_url,
                    callback_url=record.callback_url,
                    callback_secret=record.callback_secret,
                    enabled=record.enabled,
                    status=record.status,
                )
                session.add(model)
            else:
                model.scraper_subscription_id = record.scraper_subscription_id
                model.user_id = record.user_id
                model.channel_name = record.channel_name
                model.channel_url = record.channel_url
                model.callback_url = record.callback_url
                model.callback_secret = record.callback_secret
                model.enabled = record.enabled
                model.status = record.status
                model.last_seen_message_id = record.last_seen_message_id
                model.last_seen_message_timestamp = record.last_seen_message_timestamp
                model.last_error = record.last_error
                if not record.enabled:
                    model.unsubscribed_at = datetime.now(UTC)
            session.commit()
            session.refresh(model)
            return self._to_record(model)

    @staticmethod
    def _to_record(model: ChannelSubscription) -> ChannelSubscriptionRecord:
        return ChannelSubscriptionRecord(
            source_id=model.source_id,
            scraper_subscription_id=model.scraper_subscription_id,
            user_id=model.user_id,
            channel_name=model.channel_name,
            channel_url=model.channel_url,
            callback_url=model.callback_url,
            callback_secret=model.callback_secret,
            enabled=model.enabled,
            status=model.status,
            last_seen_message_id=model.last_seen_message_id,
            last_seen_message_timestamp=model.last_seen_message_timestamp,
            last_error=model.last_error,
        )


class HistoricalFetchJobRepository:
    def __init__(self, session_factory: sessionmaker) -> None:
        self.session_factory = session_factory

    def get_by_request_id(self, request_id: str) -> HistoricalFetchJobRecord | None:
        with self.session_factory() as session:
            model = session.scalar(select(HistoricalFetchJob).where(HistoricalFetchJob.request_id == request_id))
            return self._to_record(model) if model is not None else None

    def list_pending(self, *, limit: int) -> list[HistoricalFetchJobRecord]:
        with self.session_factory() as session:
            models = session.scalars(
                select(HistoricalFetchJob)
                .where(HistoricalFetchJob.status.in_(("accepted", "pending")))
                .order_by(HistoricalFetchJob.id.asc())
                .limit(limit)
            ).all()
            return [self._to_record(model) for model in models]

    def save(self, record: HistoricalFetchJobRecord) -> HistoricalFetchJobRecord:
        with self.session_factory() as session:
            model = session.scalar(select(HistoricalFetchJob).where(HistoricalFetchJob.request_id == record.request_id))
            if model is None:
                model = HistoricalFetchJob(
                    request_id=record.request_id,
                    profile_job_id=record.profile_job_id,
                    source_id=record.source_id,
                    user_id=record.user_id,
                    channel_name=record.channel_name,
                    channel_url=record.channel_url,
                    lookback_days=record.lookback_days,
                    limit=record.limit,
                    delivery_mode=record.delivery_mode,
                    callback_url=record.callback_url,
                    callback_secret=record.callback_secret,
                    status=record.status,
                    message_count=record.message_count,
                    last_error=record.last_error,
                )
                session.add(model)
            else:
                model.status = record.status
                model.message_count = record.message_count
                model.last_error = record.last_error
                if record.status in {"completed", "failed"}:
                    model.completed_at = datetime.now(UTC)
            session.commit()
            session.refresh(model)
            return self._to_record(model)

    @staticmethod
    def _to_record(model: HistoricalFetchJob) -> HistoricalFetchJobRecord:
        return HistoricalFetchJobRecord(
            request_id=model.request_id,
            profile_job_id=model.profile_job_id,
            source_id=model.source_id,
            user_id=model.user_id,
            channel_name=model.channel_name,
            channel_url=model.channel_url,
            lookback_days=model.lookback_days,
            limit=model.limit,
            delivery_mode=model.delivery_mode,
            callback_url=model.callback_url,
            callback_secret=model.callback_secret,
            status=model.status,
            message_count=model.message_count,
            last_error=model.last_error,
        )


class DeliveryAttemptRepository:
    def __init__(self, session_factory: sessionmaker) -> None:
        self.session_factory = session_factory

    def save(
        self,
        *,
        delivery_key: str,
        callback_url: str,
        event_type: str,
        status_code: int | None,
        success: bool,
        request_headers: dict,
        request_payload: dict,
        response_body: str | None,
        error_message: str | None,
    ) -> None:
        with self.session_factory() as session:
            model = DeliveryAttempt(
                delivery_key=delivery_key,
                callback_url=callback_url,
                event_type=event_type,
                status_code=status_code,
                success=success,
                request_headers_json=request_headers,
                request_payload_json=request_payload,
                response_body=response_body,
                error_message=error_message,
            )
            session.add(model)
            session.commit()
