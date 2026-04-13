from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.persistence.base import Base


def now_utc() -> datetime:
    return datetime.now(UTC)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc, onupdate=now_utc)


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    telegram_user_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)


class WalletSession(Base, TimestampMixin):
    __tablename__ = "wallet_sessions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    account_id: Mapped[str | None] = mapped_column(String(255))
    account_name: Mapped[str | None] = mapped_column(String(255))
    login_type: Mapped[str | None] = mapped_column(String(32))
    logged_in: Mapped[bool] = mapped_column(Boolean, default=False)
    wallet_evm_address: Mapped[str | None] = mapped_column(String(255))
    wallet_sol_address: Mapped[str | None] = mapped_column(String(255))
    wallet_xlayer_address: Mapped[str | None] = mapped_column(String(255))
    policy_json: Mapped[dict | None] = mapped_column(JSON)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime)


class UserStrategyProfileModel(Base, TimestampMixin):
    __tablename__ = "user_strategy_profiles"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    base_style: Mapped[str] = mapped_column(String(32))
    profile_json: Mapped[dict] = mapped_column(JSON)
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_by: Mapped[str] = mapped_column(String(64), default="system")


class FollowedSource(Base, TimestampMixin):
    __tablename__ = "followed_sources"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    source_id: Mapped[str] = mapped_column(String(255), unique=True)
    channel_name: Mapped[str] = mapped_column(String(255), index=True)
    channel_url: Mapped[str | None] = mapped_column(String(1024))
    scraper_subscription_id: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    registered_at: Mapped[datetime | None] = mapped_column(DateTime)
    unsubscribed_at: Mapped[datetime | None] = mapped_column(DateTime)


class SourceMessage(Base):
    __tablename__ = "source_messages"
    __table_args__ = (
        UniqueConstraint("event_id"),
        UniqueConstraint("source_id", "message_id", "message_timestamp"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    source_id: Mapped[str] = mapped_column(String(255), index=True)
    event_id: Mapped[str] = mapped_column(String(255))
    message_id: Mapped[str] = mapped_column(String(255))
    message_timestamp: Mapped[str] = mapped_column(String(64), index=True)
    message_text: Mapped[str] = mapped_column(Text)
    message_url: Mapped[str | None] = mapped_column(String(1024))
    raw_payload_json: Mapped[dict] = mapped_column(JSON)
    received_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)


class ParsedSignalCandidate(Base):
    __tablename__ = "parsed_signal_candidates"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    signal_id: Mapped[str] = mapped_column(String(255), unique=True)
    source_message_id: Mapped[int] = mapped_column(ForeignKey("source_messages.id"), index=True)
    source_id: Mapped[str] = mapped_column(String(255), index=True)
    message_type: Mapped[str] = mapped_column(String(64), index=True)
    is_actionable: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    parsed_json: Mapped[dict] = mapped_column(JSON)
    parse_confidence: Mapped[float | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)


class AssetResolution(Base):
    __tablename__ = "asset_resolutions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    signal_id: Mapped[str] = mapped_column(ForeignKey("parsed_signal_candidates.signal_id"), index=True)
    asset_lane: Mapped[str] = mapped_column(String(32), index=True)
    normalized_symbol: Mapped[str] = mapped_column(String(64), index=True)
    target_execution_chain: Mapped[str] = mapped_column(String(64))
    resolved_signal_chain: Mapped[str | None] = mapped_column(String(64))
    token_contract_address: Mapped[str | None] = mapped_column(String(255))
    resolution_json: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)


class EnrichmentSnapshot(Base):
    __tablename__ = "enrichment_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    signal_id: Mapped[str] = mapped_column(ForeignKey("parsed_signal_candidates.signal_id"), index=True)
    wallet_snapshot_json: Mapped[dict | None] = mapped_column(JSON)
    market_snapshot_json: Mapped[dict | None] = mapped_column(JSON)
    risk_snapshot_json: Mapped[dict | None] = mapped_column(JSON)
    signal_overlay_json: Mapped[dict | None] = mapped_column(JSON)
    ta_snapshot_json: Mapped[dict | None] = mapped_column(JSON)
    strategy_profile_version: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)


class TradeDecisionModel(Base):
    __tablename__ = "trade_decisions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    signal_id: Mapped[str] = mapped_column(ForeignKey("parsed_signal_candidates.signal_id"), index=True)
    source_id: Mapped[str] = mapped_column(String(255), index=True)
    asset_lane: Mapped[str] = mapped_column(String(32), index=True)
    decision: Mapped[str] = mapped_column(String(32), index=True)
    decision_reason_code: Mapped[str] = mapped_column(String(128))
    recommended_amount_usd: Mapped[float | None] = mapped_column()
    capped_amount_usd: Mapped[float | None] = mapped_column()
    decision_json: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)


class TradeExecution(Base):
    __tablename__ = "trade_executions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    execution_id: Mapped[str] = mapped_column(String(255), unique=True)
    signal_id: Mapped[str | None] = mapped_column(ForeignKey("parsed_signal_candidates.signal_id"), index=True)
    position_id: Mapped[str | None] = mapped_column(String(255), index=True)
    asset_lane: Mapped[str] = mapped_column(String(32))
    side: Mapped[str] = mapped_column(String(16))
    chain: Mapped[str] = mapped_column(String(64))
    wallet_address: Mapped[str] = mapped_column(String(255))
    from_token: Mapped[str] = mapped_column(String(255))
    to_token: Mapped[str] = mapped_column(String(255))
    requested_amount: Mapped[str] = mapped_column(String(64))
    approve_tx_hash: Mapped[str | None] = mapped_column(String(255))
    swap_tx_hash: Mapped[str | None] = mapped_column(String(255), index=True)
    success: Mapped[bool] = mapped_column(Boolean, default=False)
    error_code: Mapped[str | None] = mapped_column(String(128))
    error_message: Mapped[str | None] = mapped_column(Text)
    idempotency_key: Mapped[str] = mapped_column(String(255), unique=True)
    execution_json: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)


class Position(Base, TimestampMixin):
    __tablename__ = "positions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    position_id: Mapped[str] = mapped_column(String(255), unique=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    source_id: Mapped[str] = mapped_column(String(255), index=True)
    asset_lane: Mapped[str] = mapped_column(String(32))
    chain: Mapped[str] = mapped_column(String(64), index=True)
    symbol: Mapped[str] = mapped_column(String(64))
    token_contract_address: Mapped[str | None] = mapped_column(String(255))
    wallet_address: Mapped[str] = mapped_column(String(255))
    entry_signal_id: Mapped[str | None] = mapped_column(String(255))
    entry_execution_id: Mapped[str | None] = mapped_column(String(255))
    entry_price_usd: Mapped[float | None] = mapped_column()
    entry_amount_usd: Mapped[float] = mapped_column()
    entry_token_amount: Mapped[float | None] = mapped_column()
    current_price_usd: Mapped[float | None] = mapped_column()
    peak_price_since_open_usd: Mapped[float | None] = mapped_column()
    trailing_state_json: Mapped[dict | None] = mapped_column(JSON)
    last_exit_evaluated_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    status: Mapped[str] = mapped_column(String(32), default="open", index=True)
    opened_at: Mapped[datetime | None] = mapped_column(DateTime)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime)


class PositionEvent(Base):
    __tablename__ = "position_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    position_id: Mapped[str] = mapped_column(String(255), index=True)
    event_type: Mapped[str] = mapped_column(String(64))
    event_reason_code: Mapped[str | None] = mapped_column(String(128))
    event_json: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)


class TelegramNotification(Base):
    __tablename__ = "telegram_notifications"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    chat_id: Mapped[str] = mapped_column(String(255))
    related_signal_id: Mapped[str | None] = mapped_column(String(255), index=True)
    related_position_id: Mapped[str | None] = mapped_column(String(255), index=True)
    notification_type: Mapped[str] = mapped_column(String(64))
    message_text: Mapped[str] = mapped_column(Text)
    send_status: Mapped[str] = mapped_column(String(32))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)


class WorkflowRun(Base, TimestampMixin):
    __tablename__ = "workflow_runs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    thread_id: Mapped[str] = mapped_column(String(255), unique=True)
    workflow_type: Mapped[str] = mapped_column(String(64), index=True)
    related_signal_id: Mapped[str | None] = mapped_column(String(255), index=True)
    related_position_id: Mapped[str | None] = mapped_column(String(255), index=True)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    last_node: Mapped[str | None] = mapped_column(String(255))
    checkpoint_id: Mapped[str | None] = mapped_column(String(255))
    run_metadata_json: Mapped[dict | None] = mapped_column(JSON)


class PositionExitEvaluation(Base):
    __tablename__ = "position_exit_evaluations"
    __table_args__ = (UniqueConstraint("position_id", "cycle_id"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    position_id: Mapped[str] = mapped_column(String(255), index=True)
    cycle_id: Mapped[str] = mapped_column(String(255), index=True)
    decision: Mapped[str] = mapped_column(String(64), index=True)
    decision_reason_code: Mapped[str] = mapped_column(String(128))
    trailing_state_json: Mapped[dict | None] = mapped_column(JSON)
    market_snapshot_json: Mapped[dict | None] = mapped_column(JSON)
    ta_snapshot_json: Mapped[dict | None] = mapped_column(JSON)
    evaluation_json: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(index=True)
    event_type: Mapped[str] = mapped_column(String(64))
    entity_type: Mapped[str] = mapped_column(String(64), index=True)
    entity_id: Mapped[str] = mapped_column(String(255), index=True)
    event_json: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)
