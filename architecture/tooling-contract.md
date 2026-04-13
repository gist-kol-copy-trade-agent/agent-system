# Tooling Contract

## 1. Purpose

This document defines the tool surface the LangChain agents should see.

The agents should not call raw CLI commands directly.
They should call application-owned Python tools that wrap:

- OKX OnchainOS skill invocations,
- TA calculations,
- persistence lookups,
- internal policy helpers.

The tool layer must support two product lanes:

- `major asset lane` for `BTC/ETH/SOL` on `X Layer`
- `regular token lane` for all other tradable assets on the resolved signal chain

## 2. Tool Categories

## 2.1 Read Tools

Safe tools that fetch state or market data.

Examples:

- `search_token_candidates`
- `resolve_token_identity`
- `get_wallet_context`
- `get_token_market_snapshot`
- `get_major_asset_execution_context`
- `get_signal_overlay`
- `get_position_snapshot`
- `get_portfolio_analytics`

## 2.2 Scoring Tools

Pure functions or read-heavy helpers.

Examples:

- `compute_ta_score`
- `compute_exit_ta_score`
- `build_trade_sizing_inputs`
- `summarize_risk_signals`

## 2.3 Policy Tools

Deterministic business-rule evaluation.

Examples:

- `evaluate_trade_policy_gate`
- `evaluate_exit_policy_gate`

These usually should not be model-facing unless the model needs to inspect the result only.

## 2.4 Execution Tools

Sensitive side-effect tools.

Examples:

- `execute_swap_buy`
- `execute_swap_sell`
- `wallet_login`
- `wallet_verify`

These should not be generally exposed to decision agents.

## 3. Recommended Tool List

## 3.1 Parsing Agent Tools

### `search_token_candidates`
Purpose:

- search token candidates from symbol / name / address

Wraps:

- `onchainos token search`

Inputs:

- `query`
- `chain_hint`

Outputs:

- candidate list with chain, CA, symbol, name, price, change

### `get_token_metadata`
Purpose:

- fetch token info when parse agent needs confirmation

Wraps:

- `onchainos token info`

## 3.2 Decision Agent Tools

### `get_wallet_context`
Wraps:

- `onchainos wallet status`
- `onchainos wallet balance --chain <chain>`
- `onchainos wallet addresses --chain <chain>`

Returns:

- login state
- policy limits
- available balances
- usable wallet address

This tool should accept the target execution chain rather than assuming the resolved signal chain.

### `get_token_market_snapshot`
Wraps:

- `onchainos token price-info`
- `onchainos market price`
- `onchainos market kline`

Returns:

- spot price
- recent candles
- market cap
- liquidity
- volume

For the major-asset lane, this tool may omit regular-token metadata that is not needed by the strategy.

### `get_token_risk`
Wraps:

- `onchainos security token-scan`
- `onchainos token advanced-info`

Returns:

- risk verdict
- taxes
- support flags
- risk control level
- token tags
- dev rug history
- holder concentration summary
- LP burn signal when available

This tool is required for the regular-token lane and optional / normally skipped for the major-asset lane.

### `get_major_asset_execution_context`
Purpose:

- provide the decision-ready context for `BTC/ETH/SOL` execution on `X Layer`

Wraps:

- `onchainos wallet balance --chain xlayer`
- `onchainos wallet addresses --chain xlayer`
- `onchainos market price`
- `onchainos market kline`
- `onchainos swap quote`

Returns:

- approved X Layer asset mapping
- X Layer executable balance
- current price
- recent candles
- quote readiness
- price impact snapshot

### `get_signal_overlay`
Wraps:

- `onchainos signal list`
- optional `onchainos tracker activities`

Returns:

- smart-money/KOL/whale overlay summary

### `compute_ta_score`
Pure application tool.

Inputs:

- recent OHLCV
- call reference price
- current price
- liquidity / volume thresholds

Returns:

- TA score
- rule breakdown
- anti-FOMO result

### `build_trade_sizing_inputs`
Pure application tool.

Inputs:

- wallet balance
- source score
- token risk score
- TA score
- policy limits
- asset lane

Returns:

- proposed amount
- capped amount
- sizing explanation

## 3.3 Exit Agent Tools

### `get_position_snapshot`
Reads from application DB.

Returns:

- current position state
- cost basis
- size
- chain
- token

### `compute_exit_ta_score`
Pure application tool.

Inputs:

- current OHLCV
- position basis
- stop / TP configuration

Returns:

- exit signal breakdown

### `get_kol_followup_messages`
Reads from application DB.

Returns:

- recent follow-up messages for the same source and token

## 3.4 Deterministic Execution Tools

### `execute_swap_buy`
Wraps:

- `onchainos swap execute`

Inputs:

- `from_token`
- `to_token`
- `readable_amount`
- `chain`
- `wallet_address`
- `slippage_policy`
- `gas_policy`

Returns:

- tx hashes
- output amount
- gas used

### `execute_swap_sell`
Wraps:

- `onchainos swap execute`

Inputs:

- held token
- exit token
- amount
- chain
- wallet address

Returns:

- tx hashes
- realized proceeds

## 4. Tool Implementation Guidance

## 4.1 Use typed schemas

Every tool should have:

- a strict input schema,
- a strict output schema,
- normalized field names,
- explicit error shape.

Tool outputs should also include `asset_lane` when lane-specific behavior affects interpretation.

## 4.2 Normalize OKX responses

Do not leak raw CLI fields upward if they are inconsistent.

Normalize inside adapters.

Example:

- `priceImpactPercent` -> `price_impact_pct`
- `swapTxHash` -> `swap_tx_hash`

## 4.3 Separate adapter layer from tool layer

Suggested structure:

```text
app/adapters/okx/*.py
app/tools/*.py
app/policies/*.py
app/ta/*.py
```

Where:

- adapters talk to OKX skills / CLI,
- tools expose LangChain-compatible interfaces,
- policies enforce deterministic rules,
- TA computes indicator outputs.

## 4.4 Prefer composite tools over many tiny tools

Do not force the model to stitch together five low-level wallet calls if a single bounded tool can do it safely.

Good model-facing tools:

- `get_wallet_context`
- `get_token_market_snapshot`
- `get_major_asset_execution_context`
- `get_trade_candidate_context`

Bad model-facing tools:

- `wallet_status_raw`
- `wallet_addresses_raw`
- `wallet_balance_raw`

The model should consume compact, decision-ready objects.

## 5. Suggested LangChain Registration

Register all possible tools once, then filter them dynamically by agent role and graph stage using middleware.

This matches the LangChain docs pattern for dynamic tool filtering.

## 6. Critical Restriction

For this product:

- parsing agent never gets execution tools,
- decision agent never gets execution tools,
- exit agent never gets execution tools,
- only deterministic graph nodes call execution adapters.

That is the main safety boundary.
