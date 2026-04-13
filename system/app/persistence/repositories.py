from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.persistence.models import (
    AuditEvent,
    FollowedSource,
    Position,
    PositionEvent,
    PositionExitEvaluation,
    SourceMessage,
    TelegramNotification,
    TradeExecution,
    User,
    UserStrategyProfileModel,
    WorkflowRun,
)
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


@dataclass
class PositionRecord:
    position_id: str
    user_id: str
    source_id: str
    asset_lane: str
    chain: str
    symbol: str
    token_contract_address: str | None
    wallet_address: str
    entry_price_usd: float | None
    entry_amount_usd: float
    entry_token_amount: float | None = None
    current_price_usd: float | None = None
    peak_price_since_open_usd: float | None = None
    trailing_state: dict | None = None
    status: str = "open"
    opened_at: str | None = None
    closed_at: str | None = None
    last_exit_evaluated_at: str | None = None


@dataclass
class PositionExitEvaluationRecord:
    position_id: str
    cycle_id: str
    decision: str
    decision_reason_code: str
    evaluation: dict
    trailing_state: dict | None = None
    market_snapshot: dict | None = None
    ta_snapshot: dict | None = None
    created_at: str = ""


@dataclass
class TradeExecutionRecord:
    execution_id: str
    signal_id: str | None
    position_id: str | None
    asset_lane: str
    side: str
    chain: str
    wallet_address: str
    from_token: str
    to_token: str
    requested_amount: str
    approve_tx_hash: str | None
    swap_tx_hash: str | None
    success: bool
    error_code: str | None
    error_message: str | None
    idempotency_key: str
    execution: dict
    created_at: str = ""


@dataclass
class PositionEventRecord:
    position_id: str
    event_type: str
    event_reason_code: str | None
    event: dict
    created_at: str = ""


@dataclass
class TelegramNotificationRecord:
    user_id: str
    chat_id: str
    related_signal_id: str | None
    related_position_id: str | None
    notification_type: str
    message_text: str
    send_status: str
    sent_at: str | None = None
    created_at: str = ""


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


class PositionRepository(Protocol):
    def get_by_position_id(self, position_id: str) -> PositionRecord | None: ...

    def list_open_positions(self) -> list[PositionRecord]: ...

    def save(self, record: PositionRecord) -> PositionRecord: ...


class PositionExitEvaluationRepository(Protocol):
    def save(self, record: PositionExitEvaluationRecord) -> PositionExitEvaluationRecord: ...


class TradeExecutionRepository(Protocol):
    def save(self, record: TradeExecutionRecord) -> TradeExecutionRecord: ...


class PositionEventRepository(Protocol):
    def save(self, record: PositionEventRecord) -> PositionEventRecord: ...


class TelegramNotificationRepository(Protocol):
    def save(self, record: TelegramNotificationRecord) -> TelegramNotificationRecord: ...


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


class InMemoryPositionRepository:
    def __init__(self) -> None:
        self._records: dict[str, PositionRecord] = {}

    def get_by_position_id(self, position_id: str) -> PositionRecord | None:
        return self._records.get(position_id)

    def list_open_positions(self) -> list[PositionRecord]:
        return [record for record in self._records.values() if record.status == "open"]

    def save(self, record: PositionRecord) -> PositionRecord:
        self._records[record.position_id] = record
        return record


class InMemoryPositionExitEvaluationRepository:
    def __init__(self) -> None:
        self._records: dict[tuple[str, str], PositionExitEvaluationRecord] = {}

    def save(self, record: PositionExitEvaluationRecord) -> PositionExitEvaluationRecord:
        created_at = record.created_at or utc_now_iso()
        stored = PositionExitEvaluationRecord(
            position_id=record.position_id,
            cycle_id=record.cycle_id,
            decision=record.decision,
            decision_reason_code=record.decision_reason_code,
            evaluation=record.evaluation,
            trailing_state=record.trailing_state,
            market_snapshot=record.market_snapshot,
            ta_snapshot=record.ta_snapshot,
            created_at=created_at,
        )
        self._records[(record.position_id, record.cycle_id)] = stored
        return stored


class InMemoryTradeExecutionRepository:
    def __init__(self) -> None:
        self._records: dict[str, TradeExecutionRecord] = {}

    def save(self, record: TradeExecutionRecord) -> TradeExecutionRecord:
        created_at = record.created_at or utc_now_iso()
        stored = TradeExecutionRecord(
            execution_id=record.execution_id,
            signal_id=record.signal_id,
            position_id=record.position_id,
            asset_lane=record.asset_lane,
            side=record.side,
            chain=record.chain,
            wallet_address=record.wallet_address,
            from_token=record.from_token,
            to_token=record.to_token,
            requested_amount=record.requested_amount,
            approve_tx_hash=record.approve_tx_hash,
            swap_tx_hash=record.swap_tx_hash,
            success=record.success,
            error_code=record.error_code,
            error_message=record.error_message,
            idempotency_key=record.idempotency_key,
            execution=record.execution,
            created_at=created_at,
        )
        self._records[record.execution_id] = stored
        return stored


class InMemoryPositionEventRepository:
    def __init__(self) -> None:
        self._records: list[PositionEventRecord] = []

    def save(self, record: PositionEventRecord) -> PositionEventRecord:
        created_at = record.created_at or utc_now_iso()
        stored = PositionEventRecord(
            position_id=record.position_id,
            event_type=record.event_type,
            event_reason_code=record.event_reason_code,
            event=record.event,
            created_at=created_at,
        )
        self._records.append(stored)
        return stored


class InMemoryTelegramNotificationRepository:
    def __init__(self) -> None:
        self._records: list[TelegramNotificationRecord] = []

    def save(self, record: TelegramNotificationRecord) -> TelegramNotificationRecord:
        created_at = record.created_at or utc_now_iso()
        stored = TelegramNotificationRecord(
            user_id=record.user_id,
            chat_id=record.chat_id,
            related_signal_id=record.related_signal_id,
            related_position_id=record.related_position_id,
            notification_type=record.notification_type,
            message_text=record.message_text,
            send_status=record.send_status,
            sent_at=record.sent_at,
            created_at=created_at,
        )
        self._records.append(stored)
        return stored


class _SQLAlchemyRepositoryBase:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self.session_factory = session_factory

    def _ensure_user(self, session: Session, telegram_user_id: str) -> User:
        user = session.execute(select(User).where(User.telegram_user_id == telegram_user_id)).scalar_one_or_none()
        if user is None:
            user = User(telegram_user_id=telegram_user_id)
            session.add(user)
            session.flush()
        return user


class SQLAlchemyStrategyProfileRepository(_SQLAlchemyRepositoryBase):
    def get(self, user_id: str) -> UserStrategyProfile | None:
        with self.session_factory() as session:
            user = session.execute(select(User).where(User.telegram_user_id == user_id)).scalar_one_or_none()
            if user is None:
                return None
            model = (
                session.execute(select(UserStrategyProfileModel).where(UserStrategyProfileModel.user_id == user.id))
                .scalar_one_or_none()
            )
            if model is None:
                return None
            payload = dict(model.profile_json)
            payload.setdefault("user_id", user_id)
            payload.setdefault("base_style", model.base_style)
            payload.setdefault("version", model.version)
            payload.setdefault("updated_by", model.updated_by)
            return UserStrategyProfile(**payload)

    def save(self, profile: UserStrategyProfile) -> UserStrategyProfile:
        with self.session_factory() as session:
            user = self._ensure_user(session, profile.user_id)
            model = (
                session.execute(select(UserStrategyProfileModel).where(UserStrategyProfileModel.user_id == user.id))
                .scalar_one_or_none()
            )
            payload = profile.model_dump()
            if model is None:
                model = UserStrategyProfileModel(
                    user_id=user.id,
                    base_style=profile.base_style,
                    profile_json=payload,
                    version=profile.version,
                    updated_by=profile.updated_by,
                )
                session.add(model)
            else:
                model.base_style = profile.base_style
                model.profile_json = payload
                model.version = profile.version
                model.updated_by = profile.updated_by
            session.commit()
            return profile


class SQLAlchemyFollowedSourceRepository(_SQLAlchemyRepositoryBase):
    def get_by_source_id(self, source_id: str) -> FollowedSourceRecord | None:
        with self.session_factory() as session:
            model = session.execute(select(FollowedSource).where(FollowedSource.source_id == source_id)).scalar_one_or_none()
            if model is None:
                return None
            user = session.get(User, model.user_id)
            return FollowedSourceRecord(
                source_id=model.source_id,
                user_id=user.telegram_user_id if user else "",
                channel_name=model.channel_name,
                channel_url=model.channel_url,
                status=model.status,
                scraper_subscription_id=model.scraper_subscription_id,
                registered_at=model.registered_at.isoformat() if model.registered_at else None,
                unsubscribed_at=model.unsubscribed_at.isoformat() if model.unsubscribed_at else None,
            )

    def get_by_channel_name(self, user_id: str, channel_name: str) -> FollowedSourceRecord | None:
        with self.session_factory() as session:
            user = session.execute(select(User).where(User.telegram_user_id == user_id)).scalar_one_or_none()
            if user is None:
                return None
            model = (
                session.execute(
                    select(FollowedSource).where(FollowedSource.user_id == user.id, FollowedSource.channel_name == channel_name)
                ).scalar_one_or_none()
            )
            if model is None:
                return None
            return FollowedSourceRecord(
                source_id=model.source_id,
                user_id=user_id,
                channel_name=model.channel_name,
                channel_url=model.channel_url,
                status=model.status,
                scraper_subscription_id=model.scraper_subscription_id,
                registered_at=model.registered_at.isoformat() if model.registered_at else None,
                unsubscribed_at=model.unsubscribed_at.isoformat() if model.unsubscribed_at else None,
            )

    def save(self, record: FollowedSourceRecord) -> FollowedSourceRecord:
        with self.session_factory() as session:
            user = self._ensure_user(session, record.user_id)
            model = session.execute(select(FollowedSource).where(FollowedSource.source_id == record.source_id)).scalar_one_or_none()
            if model is None:
                model = FollowedSource(
                    user_id=user.id,
                    source_id=record.source_id,
                    channel_name=record.channel_name,
                    channel_url=record.channel_url,
                )
                session.add(model)
            model.user_id = user.id
            model.channel_name = record.channel_name
            model.channel_url = record.channel_url
            model.status = record.status
            model.scraper_subscription_id = record.scraper_subscription_id
            model.registered_at = _parse_datetime(record.registered_at)
            model.unsubscribed_at = _parse_datetime(record.unsubscribed_at)
            session.commit()
            return record


class SQLAlchemySourceMessageRepository(_SQLAlchemyRepositoryBase):
    def has_event(self, event_id: str) -> bool:
        with self.session_factory() as session:
            return session.execute(select(SourceMessage).where(SourceMessage.event_id == event_id)).scalar_one_or_none() is not None

    def save(self, record: SourceMessageRecord) -> SourceMessageRecord:
        with self.session_factory() as session:
            model = session.execute(select(SourceMessage).where(SourceMessage.event_id == record.event_id)).scalar_one_or_none()
            if model is None:
                model = SourceMessage(
                    event_id=record.event_id,
                    source_id=record.source_id,
                    message_id=record.message_id,
                    message_timestamp=record.message_timestamp,
                    message_text=record.message_text,
                    message_url=record.message_url,
                    raw_payload_json=record.raw_payload,
                    received_at=_parse_datetime(record.received_at) or datetime.now(UTC),
                )
                session.add(model)
            else:
                model.source_id = record.source_id
                model.message_id = record.message_id
                model.message_timestamp = record.message_timestamp
                model.message_text = record.message_text
                model.message_url = record.message_url
                model.raw_payload_json = record.raw_payload
                model.received_at = _parse_datetime(record.received_at) or model.received_at
            session.commit()
            return record


class SQLAlchemyWorkflowRunRepository(_SQLAlchemyRepositoryBase):
    def save(self, record: WorkflowRunRecord) -> WorkflowRunRecord:
        with self.session_factory() as session:
            model = session.execute(select(WorkflowRun).where(WorkflowRun.thread_id == record.thread_id)).scalar_one_or_none()
            if model is None:
                model = WorkflowRun(
                    thread_id=record.thread_id,
                    workflow_type=record.workflow_type,
                    related_signal_id=record.related_signal_id,
                    related_position_id=record.related_position_id,
                    status=record.status,
                    last_node=record.last_node,
                )
                session.add(model)
            else:
                model.workflow_type = record.workflow_type
                model.related_signal_id = record.related_signal_id
                model.related_position_id = record.related_position_id
                model.status = record.status
                model.last_node = record.last_node
            session.commit()
            return record


class SQLAlchemyPositionRepository(_SQLAlchemyRepositoryBase):
    def get_by_position_id(self, position_id: str) -> PositionRecord | None:
        with self.session_factory() as session:
            model = session.execute(select(Position).where(Position.position_id == position_id)).scalar_one_or_none()
            if model is None:
                return None
            user = session.get(User, model.user_id)
            return PositionRecord(
                position_id=model.position_id,
                user_id=user.telegram_user_id if user else "",
                source_id=model.source_id,
                asset_lane=model.asset_lane,
                chain=model.chain,
                symbol=model.symbol,
                token_contract_address=model.token_contract_address,
                wallet_address=model.wallet_address,
                entry_price_usd=model.entry_price_usd,
                entry_amount_usd=model.entry_amount_usd,
                entry_token_amount=model.entry_token_amount,
                current_price_usd=model.current_price_usd,
                peak_price_since_open_usd=model.peak_price_since_open_usd,
                trailing_state=model.trailing_state_json,
                status=model.status,
                opened_at=model.opened_at.isoformat() if model.opened_at else None,
                closed_at=model.closed_at.isoformat() if model.closed_at else None,
                last_exit_evaluated_at=model.last_exit_evaluated_at.isoformat() if model.last_exit_evaluated_at else None,
            )

    def list_open_positions(self) -> list[PositionRecord]:
        with self.session_factory() as session:
            rows = session.execute(select(Position).where(Position.status == "open")).scalars().all()
            result: list[PositionRecord] = []
            for model in rows:
                user = session.get(User, model.user_id)
                result.append(
                    PositionRecord(
                        position_id=model.position_id,
                        user_id=user.telegram_user_id if user else "",
                        source_id=model.source_id,
                        asset_lane=model.asset_lane,
                        chain=model.chain,
                        symbol=model.symbol,
                        token_contract_address=model.token_contract_address,
                        wallet_address=model.wallet_address,
                        entry_price_usd=model.entry_price_usd,
                        entry_amount_usd=model.entry_amount_usd,
                        entry_token_amount=model.entry_token_amount,
                        current_price_usd=model.current_price_usd,
                        peak_price_since_open_usd=model.peak_price_since_open_usd,
                        trailing_state=model.trailing_state_json,
                        status=model.status,
                        opened_at=model.opened_at.isoformat() if model.opened_at else None,
                        closed_at=model.closed_at.isoformat() if model.closed_at else None,
                        last_exit_evaluated_at=model.last_exit_evaluated_at.isoformat() if model.last_exit_evaluated_at else None,
                    )
                )
            return result

    def save(self, record: PositionRecord) -> PositionRecord:
        with self.session_factory() as session:
            user = self._ensure_user(session, record.user_id)
            model = session.execute(select(Position).where(Position.position_id == record.position_id)).scalar_one_or_none()
            if model is None:
                model = Position(
                    position_id=record.position_id,
                    user_id=user.id,
                    source_id=record.source_id,
                    asset_lane=record.asset_lane,
                    chain=record.chain,
                    symbol=record.symbol,
                    token_contract_address=record.token_contract_address,
                    wallet_address=record.wallet_address,
                    entry_amount_usd=record.entry_amount_usd,
                )
                session.add(model)
            model.user_id = user.id
            model.source_id = record.source_id
            model.asset_lane = record.asset_lane
            model.chain = record.chain
            model.symbol = record.symbol
            model.token_contract_address = record.token_contract_address
            model.wallet_address = record.wallet_address
            model.entry_price_usd = record.entry_price_usd
            model.entry_amount_usd = record.entry_amount_usd
            model.entry_token_amount = record.entry_token_amount
            model.current_price_usd = record.current_price_usd
            model.peak_price_since_open_usd = record.peak_price_since_open_usd
            model.trailing_state_json = record.trailing_state
            model.status = record.status
            model.opened_at = _parse_datetime(record.opened_at)
            model.closed_at = _parse_datetime(record.closed_at)
            model.last_exit_evaluated_at = _parse_datetime(record.last_exit_evaluated_at)
            session.commit()
            return record


class SQLAlchemyPositionExitEvaluationRepository(_SQLAlchemyRepositoryBase):
    def save(self, record: PositionExitEvaluationRecord) -> PositionExitEvaluationRecord:
        with self.session_factory() as session:
            model = session.execute(
                select(PositionExitEvaluation).where(
                    PositionExitEvaluation.position_id == record.position_id,
                    PositionExitEvaluation.cycle_id == record.cycle_id,
                )
            ).scalar_one_or_none()
            if model is None:
                model = PositionExitEvaluation(
                    position_id=record.position_id,
                    cycle_id=record.cycle_id,
                    decision=record.decision,
                    decision_reason_code=record.decision_reason_code,
                    evaluation_json=record.evaluation,
                )
                session.add(model)
            model.decision = record.decision
            model.decision_reason_code = record.decision_reason_code
            model.evaluation_json = record.evaluation
            model.trailing_state_json = record.trailing_state
            model.market_snapshot_json = record.market_snapshot
            model.ta_snapshot_json = record.ta_snapshot
            session.commit()
            return record


class SQLAlchemyTradeExecutionRepository(_SQLAlchemyRepositoryBase):
    def save(self, record: TradeExecutionRecord) -> TradeExecutionRecord:
        with self.session_factory() as session:
            model = session.execute(select(TradeExecution).where(TradeExecution.execution_id == record.execution_id)).scalar_one_or_none()
            if model is None:
                model = TradeExecution(
                    execution_id=record.execution_id,
                    signal_id=record.signal_id,
                    position_id=record.position_id,
                    asset_lane=record.asset_lane,
                    side=record.side,
                    chain=record.chain,
                    wallet_address=record.wallet_address,
                    from_token=record.from_token,
                    to_token=record.to_token,
                    requested_amount=record.requested_amount,
                    success=record.success,
                    idempotency_key=record.idempotency_key,
                    execution_json=record.execution,
                )
                session.add(model)
            model.signal_id = record.signal_id
            model.position_id = record.position_id
            model.asset_lane = record.asset_lane
            model.side = record.side
            model.chain = record.chain
            model.wallet_address = record.wallet_address
            model.from_token = record.from_token
            model.to_token = record.to_token
            model.requested_amount = record.requested_amount
            model.approve_tx_hash = record.approve_tx_hash
            model.swap_tx_hash = record.swap_tx_hash
            model.success = record.success
            model.error_code = record.error_code
            model.error_message = record.error_message
            model.idempotency_key = record.idempotency_key
            model.execution_json = record.execution
            session.commit()
            return record


class SQLAlchemyPositionEventRepository(_SQLAlchemyRepositoryBase):
    def save(self, record: PositionEventRecord) -> PositionEventRecord:
        with self.session_factory() as session:
            model = PositionEvent(
                position_id=record.position_id,
                event_type=record.event_type,
                event_reason_code=record.event_reason_code,
                event_json=record.event,
            )
            session.add(model)
            session.commit()
            return record


class SQLAlchemyTelegramNotificationRepository(_SQLAlchemyRepositoryBase):
    def save(self, record: TelegramNotificationRecord) -> TelegramNotificationRecord:
        with self.session_factory() as session:
            user = self._ensure_user(session, record.user_id)
            model = TelegramNotification(
                user_id=user.id,
                chat_id=record.chat_id,
                related_signal_id=record.related_signal_id,
                related_position_id=record.related_position_id,
                notification_type=record.notification_type,
                message_text=record.message_text,
                send_status=record.send_status,
                sent_at=_parse_datetime(record.sent_at),
            )
            session.add(model)
            session.commit()
            return record


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()
