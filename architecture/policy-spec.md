# Policy Spec

## 1. Purpose

This document defines executable policy behavior for the PoC/V1 bot.

It converts product intent into deterministic rules for:

- lane selection,
- skip vs block vs execute,
- sizing,
- default exits,
- preset behavior.

## 2. Decision Vocabulary

- `execute`: the trade is allowed to proceed
- `skip`: the bot declines to trade without treating the case as unsafe
- `block`: the bot identifies a hard safety or policy violation

## 3. Lane Selection Policy

## 3.1 Major Lane

The signal is `major` if normalized asset symbol is one of:

- `BTC`
- `ETH`
- `SOL`

Everything else is `regular`.

This classification is deterministic and happens before enrichment policy selection.

PoC/V1 note:

- the major-asset allowlist is intentionally fixed to these three assets only
- this is a temporary product scope choice, not a permanent architectural limitation

Future versions may extend the major-asset allowlist to additional large-cap assets such as:

- `BNB`
- `TRX`

Implementation rule:

- the classifier logic should read the allowlist from config rather than hardcoding business assumptions deep inside the orchestration flow

## 4. Lane Enablement Policy

## 4.1 Major Lane

If `major_asset_lane_enabled = false`:

- result = `skip`
- reason code = `MAJOR_LANE_DISABLED`

## 4.2 Regular Lane

If `regular_token_lane_enabled = false`:

- result = `skip`
- reason code = `REGULAR_LANE_DISABLED`

## 5. Wallet Readiness Policy

Trade cannot execute if:

- wallet is not logged in -> `block: WALLET_NOT_READY`
- target execution chain has no usable address -> `block: CHAIN_ADDRESS_UNAVAILABLE`
- target execution chain has insufficient usable balance -> `skip: INSUFFICIENT_CHAIN_BALANCE`

## 6. Resolution Policy

## 6.1 Major Lane

The product-approved X Layer mapping must exist.

If not:

- `block: MAJOR_MAPPING_NOT_FOUND`

## 6.2 Regular Lane

If token resolution is ambiguous:

- `block: TOKEN_AMBIGUOUS`

If no token contract can be resolved:

- `block: TOKEN_UNRESOLVED`

## 7. Risk Policy

## 7.1 Major Lane

Major-lane trades do not require the full regular-token risk scan.

They still require:

- quote availability
- policy compliance
- TA compliance

## 7.2 Regular Lane

If token risk scan is required and returns risk:

- `block: TOKEN_RISK_BLOCKED`

If risk scan infrastructure fails:

- `skip: TOKEN_RISK_UNAVAILABLE`

PoC choice:

- fail closed for regular-token risk-scan failures

Regular-lane risk assessment should also consume token-intelligence metadata from `token advanced-info`.

Recommended blocking or warning examples:

- if `devRugPullTokenCount > 0` -> at least `skip`, and often `block` depending on threshold
- if `riskControlLevel` is elevated -> tighten policy outcome
- if `top10HoldPercent` is extremely concentrated -> `skip` or `block`
- if `tokenTags` contain adverse quality markers -> downgrade the setup

These thresholds should be finalized in config, but the policy layer must be designed to consume them.

Detailed default interpretation thresholds are defined in:

- `risk-scoring-matrix.md`

## 8. Quote Policy

If quote is unavailable:

- `skip: QUOTE_UNAVAILABLE`

If quote price impact exceeds lane-specific threshold:

- `block: PRICE_IMPACT_TOO_HIGH`

## 9. TA Policy

## 9.1 Major Lane

Required checks:

- price deviation vs call reference <= `max_price_deviation_pct_major`
- TA score >= minimum internal threshold

If deviation exceeds threshold:

- `skip: MAJOR_FOMO_TOO_HIGH`

If TA score too weak:

- `skip: MAJOR_TA_WEAK`

## 9.2 Regular Lane

Required checks:

- price deviation vs call reference <= `max_price_deviation_pct_regular`
- if liquidity data exists, liquidity >= `min_liquidity_usd_regular`
- TA score >= minimum internal threshold

If deviation exceeds threshold:

- `skip: REGULAR_FOMO_TOO_HIGH`

If liquidity is below threshold:

- `block: REGULAR_LIQUIDITY_TOO_LOW`

If TA score too weak:

- `skip: REGULAR_TA_WEAK`

## 10. Position Limit Policy

If open positions >= `max_active_positions`:

- `skip: MAX_ACTIVE_POSITIONS_REACHED`

## 11. Sizing Policy

## 11.1 Inputs

- `available_balance_usd`
- `max_amount_per_trade_usd`
- `lane_max_amount_usd`
- `max_portfolio_risk_pct_per_trade`
- `source_score`
- `ta_score`
- `token_risk_score` for regular lane

## 11.2 Formula

Base notional:

```text
base_notional = available_balance_usd * max_portfolio_risk_pct_per_trade
```

Lane-adjusted notional:

```text
major_lane_notional = base_notional * source_score * ta_score
regular_lane_notional = base_notional * source_score * ta_score * token_risk_score
```

Final capped notional:

```text
final_trade_amount_usd = min(
  lane_adjusted_notional,
  max_amount_per_trade_usd,
  lane_max_amount_usd,
  available_balance_usd
)
```

## 11.3 Sizing Skip Rule

If final capped notional is below the product minimum executable trade size:

- `skip: TRADE_SIZE_TOO_SMALL`

PoC recommendation:

- define product minimum per chain in config

## 12. Preset Behavior

## 12.1 Safe

Intent:

- reduce size
- reduce slippage
- tighten anti-FOMO thresholds
- require stronger liquidity for regular tokens

## 12.2 Normal

Intent:

- balanced default

## 12.3 Degen

Intent:

- larger size
- looser slippage
- looser deviation and liquidity thresholds

Still bounded by:

- system hard caps
- lane enablement
- execution availability

## 13. Exit Policy

## 13.1 Exit Trigger Priority

Recommended priority:

1. hard risk / invalid position state
2. stop-loss hit
3. take-profit hit
4. trailing stop trigger
5. max holding time trigger

## 13.2 Fallback Exit Rules

When signal lacks explicit TP/SL:

- use `default_stop_loss_pct`
- use `default_take_profit_pct`
- use `max_holding_time_hours`

## 14. Skip vs Block Guidance

Use `block` for:

- unsafe asset or unresolved identity
- hard policy violations
- critical safety failures
- critical liquidity or quote integrity failures

Use `skip` for:

- weak setup
- insufficient balance
- disabled lane
- weak TA
- size too small
- non-actionable signal

## 15. Recommended Internal Threshold Placeholders

PoC placeholders to be finalized in config:

- `MIN_TA_SCORE_MAJOR = 0.5`
- `MIN_TA_SCORE_REGULAR = 0.6`
- `MIN_SOURCE_SCORE = 0.3`

These should live in config, not hardcoded into prompts.
