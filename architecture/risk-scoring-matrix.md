# Risk Scoring Matrix

## 1. Purpose

This document defines a concrete risk interpretation matrix for the `regular token lane`.

It translates risk inputs from:

- `okx-security token-scan`
- `okx-dex-token advanced-info`

into deterministic policy outcomes.

For v1, this matrix should be treated as the default implementation baseline.

## 2. Scope

This matrix applies to:

- regular tokens only

It does not apply to:

- major assets in the `BTC/ETH/SOL` lane

## 3. Output Vocabulary

- `allow`: no direct negative effect on execution
- `warn`: negative evidence, but not enough to block alone
- `skip`: bot should decline the trade under normal automation
- `block`: bot must not execute

## 4. Primary Risk Inputs

### 4.1 Security Layer

Inputs from `okx-security token-scan`:

- `is_risk_token`
- `buy_tax_pct`
- `sell_tax_pct`
- scan support / availability

### 4.2 Token Intelligence Layer

Inputs from `okx-dex-token advanced-info`:

- `riskControlLevel`
- `tokenTags`
- `devRugPullTokenCount`
- `devCreateTokenCount`
- `top10HoldPercent`
- `lpBurnedPercent`
- `creatorAddress`

## 5. Hard Block Rules

Any one of the following should produce:

- `action = block`

### Security Rules

- `is_risk_token = true`
- token risk scan unavailable in a path where scan is required and policy is fail-closed

### Token Intelligence Rules

- `devRugPullTokenCount >= 10`
- `top10HoldPercent >= 60`
- `riskControlLevel` indicates highest-risk bucket, if the API/provider semantics confirm that mapping in implementation

## 6. Default Skip Rules

Any one of the following should produce at least:

- `action = skip`

unless a stronger `block` rule already applies.

### Security Layer

- `buy_tax_pct > 10`
- `sell_tax_pct > 10`

### Token Intelligence Layer

- `devRugPullTokenCount` between `1` and `9`
- `top10HoldPercent` between `35` and `60`
- `lpBurnedPercent < 50`
- `tokenTags` contains a known adverse quality tag from the local denylist

## 7. Warning Rules

These do not force a skip by themselves, but they should reduce the effective token-risk score.

- `devCreateTokenCount` is very high, e.g. `>= 100`
- `top10HoldPercent` between `20` and `35`
- `lpBurnedPercent` between `50` and `70`
- `tokenTags` contains highly promotional or hype-only markers without strong quality confirmation

## 8. Suggested Token Tag Handling

Token tags should be split into three buckets in local config:

### Positive / informative

Examples:

- `communityRecognized`
- `smartMoneyBuy`

These should not override stronger negative evidence.

### Neutral

Examples:

- `dexBoost`

These may be informative but should not materially improve risk score alone.

### Negative / adverse

Project-specific local denylist should be configurable.

If any tag appears in the adverse denylist:

- at least `skip`
- possibly `block` if also combined with concentration or dev-history red flags

## 9. Recommended Composite Interpretation

## 9.1 Block Outcome

Return `block` if any block rule is triggered.

Example reasons:

- `TOKEN_RISK_BLOCKED`
- `DEV_RUG_HISTORY_SEVERE`
- `HOLDER_CONCENTRATION_EXTREME`

## 9.2 Skip Outcome

Return `skip` if:

- no block rule triggered
- but one or more skip rules are triggered

Example reasons:

- `HIGH_TOKEN_TAX`
- `DEV_RUG_HISTORY_PRESENT`
- `LOW_LP_BURN`
- `HOLDER_CONCENTRATION_HIGH`

## 9.3 Allow Outcome

Allow only if:

- no block rule triggered
- no skip rule triggered
- and all other policy gates also pass

## 10. Suggested Risk Score Mapping

If the implementation wants a numeric score in addition to action:

### Start Value

```text
token_risk_score = 1.0
```

### Deductions

- `devRugPullTokenCount >= 1 and < 10` -> `-0.3`
- `devCreateTokenCount >= 100` -> `-0.1`
- `top10HoldPercent >= 20 and < 35` -> `-0.1`
- `top10HoldPercent >= 35 and < 60` -> `-0.3`
- `lpBurnedPercent < 70 and >= 50` -> `-0.1`
- `lpBurnedPercent < 50` -> `-0.3`
- `buy_tax_pct > 5` or `sell_tax_pct > 5` -> `-0.2`
- adverse tag hit -> `-0.3`

### Floors

- if any `block` rule hits -> score forced to `0`
- clamp final numeric score to `[0, 1]`

## 11. Recommended V1 Thresholds

### Block

- `is_risk_token = true`
- `devRugPullTokenCount >= 10`
- `top10HoldPercent >= 60`

### Skip

- `buy_tax_pct > 10`
- `sell_tax_pct > 10`
- `devRugPullTokenCount >= 1`
- `top10HoldPercent >= 35`
- `lpBurnedPercent < 50`

### Warn only

- `devCreateTokenCount >= 100`
- `top10HoldPercent >= 20`
- `lpBurnedPercent < 70`

## 12. Implementation Notes

- Thresholds should live in config, not in prompts.
- `riskControlLevel` semantics may depend on provider interpretation; implementation should confirm whether higher or lower values are riskier before binding block logic to that field.
- Positive tags like `communityRecognized` should not erase hard negatives.
- The final action still flows through the broader policy gate with:
  - TA checks
  - liquidity checks
  - wallet readiness
  - sizing limits
