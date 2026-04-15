from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.persistence.base import Base


def now_utc() -> datetime:
    return datetime.now(UTC)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc, onupdate=now_utc)


class ChannelSubscription(Base, TimestampMixin):
    __tablename__ = "channel_subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    source_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    scraper_subscription_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    user_id: Mapped[str] = mapped_column(String(255), index=True)
    channel_name: Mapped[str] = mapped_column(String(255), index=True)
    channel_url: Mapped[str | None] = mapped_column(String(1024))
    callback_url: Mapped[str] = mapped_column(String(1024))
    callback_secret: Mapped[str] = mapped_column(String(255))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    status: Mapped[str] = mapped_column(String(64), default="registered", index=True)
    last_seen_message_id: Mapped[str | None] = mapped_column(String(255))
    last_seen_message_timestamp: Mapped[str | None] = mapped_column(String(64))
    last_delivery_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_error: Mapped[str | None] = mapped_column(Text)
    registered_at: Mapped[datetime | None] = mapped_column(DateTime, default=now_utc)
    unsubscribed_at: Mapped[datetime | None] = mapped_column(DateTime)


class HistoricalFetchJob(Base, TimestampMixin):
    __tablename__ = "historical_fetch_jobs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    profile_job_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    source_id: Mapped[str] = mapped_column(String(255), index=True)
    user_id: Mapped[str] = mapped_column(String(255), index=True)
    channel_name: Mapped[str] = mapped_column(String(255), index=True)
    channel_url: Mapped[str | None] = mapped_column(String(1024))
    lookback_days: Mapped[int] = mapped_column(Integer, default=7)
    limit: Mapped[int] = mapped_column(Integer, default=500)
    delivery_mode: Mapped[str] = mapped_column(String(64), default="async_webhook")
    callback_url: Mapped[str] = mapped_column(String(1024))
    callback_secret: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(64), default="accepted", index=True)
    message_count: Mapped[int | None] = mapped_column(Integer)
    last_error: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)


class DeliveryAttempt(Base, TimestampMixin):
    __tablename__ = "delivery_attempts"
    __table_args__ = (
        UniqueConstraint("delivery_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    delivery_key: Mapped[str] = mapped_column(String(255))
    callback_url: Mapped[str] = mapped_column(String(1024))
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    status_code: Mapped[int | None] = mapped_column(Integer)
    success: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    request_headers_json: Mapped[dict] = mapped_column(JSON)
    request_payload_json: Mapped[dict] = mapped_column(JSON)
    response_body: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
