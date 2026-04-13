from typing import Literal, TypedDict


AssetLane = Literal["major", "regular"]


class ParsedSignal(TypedDict):
    source_id: str
    message_id: str
    message_type: Literal["trade_call", "trade_update", "exit_signal", "noise"]
    is_actionable: bool
    raw_symbol: str | None
    raw_contract_address: str | None
    raw_chain_hint: str | None
    entry_reference_text: str | None
    target_reference_text: str | None
    stop_reference_text: str | None
    urgency: Literal["low", "normal", "high"] | None
    confidence: float
    reasoning_summary: str


class ResolvedAsset(TypedDict):
    asset_lane: AssetLane
    normalized_symbol: str
    target_execution_chain: str
    resolved_signal_chain: str | None
    token_contract_address: str | None
    token_name: str | None
    decimals: int | None
    is_native: bool
    approved_major_mapping: str | None
    resolution_confidence: float


class WalletSnapshot(TypedDict):
    logged_in: bool
    account_id: str | None
    account_name: str | None
    target_chain: str
    wallet_address: str | None
    available_balance_usd: float
    available_balance_token: float | None
    policy_single_tx_limit_usd: float | None
    policy_daily_trade_limit_usd: float | None
    policy_daily_trade_used_usd: float | None


class MarketSnapshot(TypedDict):
    asset_lane: AssetLane
    chain: str
    spot_price_usd: float | None
    market_cap_usd: float | None
    liquidity_usd: float | None
    volume_24h_usd: float | None
    price_change_24h_pct: float | None
    kline_window: list[dict]
    quote_available: bool
    quote_price_impact_pct: float | None


class RiskSnapshot(TypedDict):
    asset_lane: AssetLane
    risk_scan_required: bool
    risk_scan_supported: bool
    is_risk_token: bool | None
    buy_tax_pct: float | None
    sell_tax_pct: float | None
    risk_control_level: str | None
    token_tags: list[str]
    dev_rug_pull_token_count: int | None
    dev_create_token_count: int | None
    top10_hold_percent: float | None
    lp_burned_percent: float | None
    creator_address: str | None
    risk_summary: str


class TASnapshot(TypedDict):
    asset_lane: AssetLane
    call_reference_price_usd: float | None
    current_price_usd: float | None
    price_deviation_pct: float | None
    momentum_score: float | None
    volatility_score: float | None
    liquidity_gate_passed: bool | None
    ta_score: float
    ta_summary: str
