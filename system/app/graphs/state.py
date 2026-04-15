from typing import Any, TypedDict

from app.schemas.domain import (
    DecisionExplanation,
    ExitDecision,
    ExitExplanation,
    ExitExecutionRequest,
    ExitExecutionResult,
    ExitTAExplanation,
    ExitMarketSnapshot,
    ExitTASnapshot,
    ExecutionReceiptExplanation,
    EnrichmentExplanation,
    MarketSnapshot,
    ParsedSignal,
    ParseExplanation,
    PolicyExplanation,
    PositionTrackingSnapshot,
    PositionSnapshot,
    ResolvedAsset,
    RiskSnapshot,
    TAExplanation,
    TASnapshot,
    TrailingState,
    WalletSnapshot,
)
from app.schemas.strategy import UserStrategyProfile


class TradingGraphState(TypedDict):
    messages: list[Any]
    action_type: str
    source_id: str | None
    signal_id: str | None
    position_id: str | None
    request_user_id: str | None
    raw_message_text: str
    media_blobs: list[dict[str, Any]]
    parsed_signal: ParsedSignal | None
    resolved_asset: ResolvedAsset | None
    parse_explanation: ParseExplanation | None
    wallet_snapshot: WalletSnapshot | None
    market_snapshot: MarketSnapshot | None
    risk_snapshot: RiskSnapshot | None
    enrichment_explanation: EnrichmentExplanation | None
    ta_snapshot: TASnapshot | None
    ta_explanation: TAExplanation | None
    strategy_profile: UserStrategyProfile | None
    trade_decision: dict[str, Any] | None
    decision_explanation: DecisionExplanation | None
    policy_gate_result: dict[str, Any] | None
    policy_explanation: PolicyExplanation | None
    execution_request: dict[str, Any] | None
    execution_result: dict[str, Any] | None
    execution_receipt_explanation: ExecutionReceiptExplanation | None
    telegram_summary: str | None
    signal_overlay: dict[str, Any] | None
    execution_trace: list[dict[str, Any]]


class WalletCommandGraphState(TypedDict):
    messages: list[Any]
    action_type: str
    user_id: str
    chat_id: str
    raw_text: str
    command_name: str | None
    supported_command: bool
    response_message: str | None
    response_payload: dict[str, Any] | None


class ExitGraphState(TypedDict):
    messages: list[Any]
    action_type: str
    user_id: str | None
    position_id: str
    cycle_id: str | None
    position_record: Any
    position_snapshot: PositionSnapshot | None
    trailing_state: TrailingState | None
    exit_market_snapshot: ExitMarketSnapshot | None
    position_tracking_snapshot: PositionTrackingSnapshot | None
    position_tracking_explanation: EnrichmentExplanation | None
    exit_ta_snapshot: ExitTASnapshot | None
    exit_ta_explanation: ExitTAExplanation | None
    strategy_profile: UserStrategyProfile | None
    exit_decision: ExitDecision | None
    exit_decision_explanation: ExitExplanation | None
    policy_gate_result: dict[str, Any] | None
    exit_policy_explanation: PolicyExplanation | None
    execution_request: ExitExecutionRequest | None
    execution_result: ExitExecutionResult | None
    exit_execution_receipt_explanation: ExecutionReceiptExplanation | None
    telegram_summary: str | None
    execution_trace: list[dict[str, Any]]
