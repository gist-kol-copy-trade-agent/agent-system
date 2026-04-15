# Domain Schemas

## 1. Purpose

This document defines the core domain objects that the application should standardize before implementation.

These schemas are intended to become:

- `TypedDict` or Pydantic models in code,
- shared payload contracts between graph nodes,
- persistence DTOs for business logic,
- structured outputs for agent steps.

## 2. Schema Principles

- Keep schemas normalized and explicit.
- Separate raw external payloads from normalized internal objects.
- Prefer enum-like constrained fields over free text.
- Distinguish between:
  - parsed signal intent,
  - resolved tradable asset,
  - enrichment context,
  - decision output,
  - execution output.
- Also distinguish machine-consumed business state from user-facing explanation artifacts.

## 2A. Explanation Artifact Base

Explanation artifacts are first-class structured outputs that summarize why the system reached a state.

They are:

- renderer-friendly,
- persistable for audit or demo replay,
- not execution authority,
- not raw chain-of-thought.

```python
class ExplanationArtifact(TypedDict):
    title: str
    summary: str
    evidence_points: list[str]
    key_metrics: dict[str, str | float | int | bool | None]
    long_form_message: str | None
```

Specialized variants can inherit from this base shape, such as:

- `ParseExplanation`
- `EnrichmentExplanation`
- `TAExplanation`
- `DecisionExplanation`
- `PolicyExplanation`
- `ExecutionReceiptExplanation`
- `ExitExplanation`
- `FollowProfileExplanation`

## 3. Parsed Signal

```python
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
```

Companion explanation artifact:

```python
class ParseExplanation(ExplanationArtifact): ...
```

## 4. Asset Lane

```python
AssetLane = Literal["major", "regular"]
```

## 5. Resolved Asset

```python
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
```

Rules:

- `token_contract_address` may be null for the major lane if the product uses a canonical internal asset mapping.
- `resolved_signal_chain` may differ from `target_execution_chain` only for the major lane.
- in the current MVP runtime:
  - `approved_major_mapping` is a product-owned canonical execution token id such as `xlayer:WETH`
  - `regular lane` is considered resolved only after deterministic confirmation of `contract + chain`
  - parser-provided symbol-only clues are not enough by themselves to mark a regular token as resolved

## 6. Wallet Snapshot

```python
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
```

Companion explanation fields produced by the enrichment agent:

- `wallet_summary`

## 7. Market Snapshot

```python
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
```

Companion explanation fields produced by the enrichment agent:

- `market_summary`
- `evidence_points`

## 8. Risk Snapshot

```python
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
```

Interpretation:

- `is_risk_token`, `buy_tax_pct`, and `sell_tax_pct` come from `okx-security`
- the remaining token-quality fields come from `okx-dex-token advanced-info`
- for the major lane, most of these fields will normally be null or empty because the full token-risk path is skipped

Companion explanation fields produced by the enrichment agent:

- `risk_summary_long`

## 9. Signal Overlay Snapshot

```python
class SignalOverlaySnapshot(TypedDict):
    supported: bool
    smart_money_count: int | None
    kol_count: int | None
    whale_count: int | None
    overlay_summary: str
```

Companion explanation fields produced by the enrichment agent:

- `overlay_summary_long`

The normalized enrichment output may also carry a separate explanation artifact:

```python
class EnrichmentExplanation(ExplanationArtifact): ...
```

## 10. TA Snapshot

```python
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
```

Companion explanation artifact:

```python
class TAExplanation(ExplanationArtifact): ...
```

## 11. Strategy Profile Ref

The full schema is defined in:

- `user-strategy-profile-schema.md`

Graph nodes should consume it as:

```python
class StrategyProfileRef(TypedDict):
    user_id: str
    base_style: Literal["degen", "normal", "safe"]
    version: int
    major_asset_lane_enabled: bool
    regular_token_lane_enabled: bool
    max_amount_per_trade_usd: float
    major_asset_max_amount_usd: float
    regular_token_max_amount_usd: float
    max_slippage_pct_major: float
    max_slippage_pct_regular: float
    max_price_deviation_pct_major: float
    max_price_deviation_pct_regular: float
    min_liquidity_usd_regular: float
    max_active_positions: int
    default_stop_loss_pct: float
    default_take_profit_pct: float
    max_holding_time_hours: int
```

## 12. Sizing Input

```python
class SizingInput(TypedDict):
    asset_lane: AssetLane
    source_score: float
    ta_score: float
    token_risk_score: float | None
    available_balance_usd: float
    max_amount_per_trade_usd: float
    lane_max_amount_usd: float
    max_portfolio_risk_pct_per_trade: float
```

## 13. Trade Decision

```python
class TradeDecision(TypedDict):
    asset_lane: AssetLane
    decision: Literal["execute", "skip", "block"]
    decision_reason_code: str
    confidence: float
    recommended_amount_usd: float
    capped_amount_usd: float
    rationale_summary: str
    telegram_summary: str
    analysis_thesis: str
    ta_reasoning: str
    risk_reasoning: str
    sizing_reasoning: str
    policy_expectation_summary: str
    user_message_long: str
```

Companion explanation artifact:

```python
class DecisionExplanation(ExplanationArtifact): ...
```

## 14. Policy Gate Result

```python
class PolicyGateResult(TypedDict):
    passed: bool
    action: Literal["execute", "skip", "block"]
    failure_codes: list[str]
    gate_summary: str
```

Companion explanation artifact:

```python
class PolicyExplanation(ExplanationArtifact): ...
```

## 14A. Exit Decision

```python
class ExitDecision(TypedDict):
    asset_lane: AssetLane
    decision: Literal["hold", "exit_hard", "exit_trailing_arm", "exit_trailing_fire"]
    decision_reason_code: str
    confidence: float
    rationale_summary: str
    telegram_summary: str
    trigger_reasoning: str
    trailing_plan: str
    risk_protection_summary: str
    user_message_long: str
```

Companion explanation artifact:

```python
class ExitExplanation(ExplanationArtifact): ...
```

## 15. Execution Request

```python
class ExecutionRequest(TypedDict):
    asset_lane: AssetLane
    side: Literal["buy", "sell"]
    chain: str
    wallet_address: str
    from_token: str
    to_token: str
    readable_amount: str
    slippage_pct: float | None
    gas_level: Literal["slow", "average", "fast"] | None
```

## 16. Execution Result

```python
class ExecutionResult(TypedDict):
    asset_lane: AssetLane
    side: Literal["buy", "sell"]
    success: bool
    approve_tx_hash: str | None
    swap_tx_hash: str | None
    from_amount: str | None
    to_amount: str | None
    price_impact_pct: float | None
    gas_used_usd: float | None
    explorer_url: str | None
    approval_explorer_url: str | None
    execution_price: float | None
    effective_price_impact_pct: float | None
    route_summary: str | None
    receipt_message_long: str | None
    error_code: str | None
    error_message: str | None
```

Companion explanation artifact:

```python
class ExecutionReceiptExplanation(ExplanationArtifact): ...
```

## 17. Position Record

```python
class PositionRecord(TypedDict):
    position_id: str
    source_id: str
    asset_lane: AssetLane
    chain: str
    symbol: str
    token_contract_address: str | None
    wallet_address: str
    entry_tx_hash: str
    entry_price_usd: float | None
    entry_amount_usd: float
    status: Literal["open", "closing", "closed", "failed"]
```

## 18. Webhook Payload

```python
class ScraperWebhookPayload(TypedDict):
    event_id: str
    event_type: Literal["telegram.message.new"]
    scraper_subscription_id: str | None
    source_id: str
    channel_name: str
    channel_url: str | None
    message_id: str
    message_text: str
    message_timestamp: str
    message_url: str | None
    media_blobs: list[dict]
    raw_payload: dict
```

## 19. Graph State Skeleton

```python
class TradingGraphState(TypedDict):
    messages: list
    action_type: str
    source_id: str | None
    signal_id: str | None
    position_id: str | None
    parsed_signal: ParsedSignal | None
    resolved_asset: ResolvedAsset | None
    wallet_snapshot: WalletSnapshot | None
    market_snapshot: MarketSnapshot | None
    risk_snapshot: RiskSnapshot | None
    signal_overlay: SignalOverlaySnapshot | None
    ta_snapshot: TASnapshot | None
    strategy_profile: StrategyProfileRef | None
    trade_decision: TradeDecision | None
    policy_gate_result: PolicyGateResult | None
    execution_request: ExecutionRequest | None
    execution_result: ExecutionResult | None
    telegram_summary: str | None
```
