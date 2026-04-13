from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from app.schemas.strategy import UserStrategyProfile
from app.schemas.webhook import ScraperWebhookPayload


@dataclass
class FollowedSourceRecord:
    source_id: str
    user_id: str
    channel_name: str
    channel_url: str | None
    status: str = "pending"
    scraper_subscription_id: str | None = None
    registered_at: str | None = None
    unsubscribed_at: str | None = None


@dataclass
class SourceMessageRecord:
    event_id: str
    source_id: str
    message_id: str
    message_timestamp: str
    message_text: str
    message_url: str | None
    raw_payload: dict
    received_at: str


@dataclass
class WorkflowRunRecord:
    thread_id: str
    workflow_type: str
    related_signal_id: str | None
    related_position_id: str | None
    status: str
    last_node: str | None = None


class StrategyProfileRepository(Protocol):
    def get(self, user_id: str) -> UserStrategyProfile | None: ...

    def save(self, profile: UserStrategyProfile) -> UserStrategyProfile: ...


class FollowedSourceRepository(Protocol):
    def get_by_source_id(self, source_id: str) -> FollowedSourceRecord | None: ...

    def get_by_channel_name(self, user_id: str, channel_name: str) -> FollowedSourceRecord | None: ...

    def save(self, record: FollowedSourceRecord) -> FollowedSourceRecord: ...


class SourceMessageRepository(Protocol):
    def has_event(self, event_id: str) -> bool: ...

    def save(self, record: SourceMessageRecord) -> SourceMessageRecord: ...


class WorkflowRunRepository(Protocol):
    def save(self, record: WorkflowRunRecord) -> WorkflowRunRecord: ...


class InMemoryStrategyProfileRepository:
    def __init__(self) -> None:
        self._profiles: dict[str, UserStrategyProfile] = {}

    def get(self, user_id: str) -> UserStrategyProfile | None:
        return self._profiles.get(user_id)

    def save(self, profile: UserStrategyProfile) -> UserStrategyProfile:
        self._profiles[profile.user_id] = profile
        return profile


class InMemoryFollowedSourceRepository:
    def __init__(self) -> None:
        self._records: dict[str, FollowedSourceRecord] = {}

    def get_by_source_id(self, source_id: str) -> FollowedSourceRecord | None:
        return self._records.get(source_id)

    def get_by_channel_name(self, user_id: str, channel_name: str) -> FollowedSourceRecord | None:
        for record in self._records.values():
            if record.user_id == user_id and record.channel_name == channel_name:
                return record
        return None

    def save(self, record: FollowedSourceRecord) -> FollowedSourceRecord:
        self._records[record.source_id] = record
        return record


class InMemorySourceMessageRepository:
    def __init__(self) -> None:
        self._records: dict[str, SourceMessageRecord] = {}

    def has_event(self, event_id: str) -> bool:
        return event_id in self._records

    def save(self, record: SourceMessageRecord) -> SourceMessageRecord:
        self._records[record.event_id] = record
        return record


class InMemoryWorkflowRunRepository:
    def __init__(self) -> None:
        self._records: dict[str, WorkflowRunRecord] = {}

    def save(self, record: WorkflowRunRecord) -> WorkflowRunRecord:
        self._records[record.thread_id] = record
        return record


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()
