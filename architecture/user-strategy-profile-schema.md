# User Strategy Profile Schema

## 1. Purpose

This document defines the normalized schema for the user's global trading settings.

This schema should be used consistently across:

- onboarding,
- chat-based settings updates,
- LangGraph store,
- application persistence,
- decision-engine inputs.

## 2. Design Intent

The schema has two layers:

- `base_style`: high-level preset chosen by the user
- `resolved_parameters`: explicit numeric and boolean controls used by the decision engine

The base style is not enough by itself. The decision engine must consume the resolved parameters.

## 3. Allowed Base Styles

```text
degen
normal
safe
```

## 4. Recommended Typed Schema

```python
from typing import Literal, TypedDict


TradingStyle = Literal["degen", "normal", "safe"]


class UserStrategyProfile(TypedDict):
    user_id: str
    base_style: TradingStyle
    major_asset_lane_enabled: bool
    regular_token_lane_enabled: bool
    max_amount_per_trade_usd: float
    max_portfolio_risk_pct_per_trade: float
    max_active_positions: int
    major_asset_max_amount_usd: float
    regular_token_max_amount_usd: float
    max_slippage_pct_major: float
    max_slippage_pct_regular: float
    max_price_deviation_pct_major: float
    max_price_deviation_pct_regular: float
    min_liquidity_usd_regular: float
    default_stop_loss_pct: float
    default_take_profit_pct: float
    max_holding_time_hours: int
    updated_at: str
    updated_by: str
    version: int
```

## 5. Field Definitions

### Identity and control

- `user_id`: owner of the strategy profile
- `base_style`: selected preset
- `updated_at`: ISO timestamp
- `updated_by`: `system` or `user`
- `version`: optimistic version number for updates

### Lane toggles

- `major_asset_lane_enabled`: whether `BTC/ETH/SOL` calls may be auto-traded
- `regular_token_lane_enabled`: whether non-major tokens may be auto-traded

### Global risk controls

- `max_amount_per_trade_usd`: hard notional cap for any trade
- `max_portfolio_risk_pct_per_trade`: percentage-based cap used in sizing logic
- `max_active_positions`: max simultaneously open positions

### Lane-specific amount controls

- `major_asset_max_amount_usd`: cap for the major-asset lane
- `regular_token_max_amount_usd`: cap for the regular-token lane

### Entry tolerance

- `max_slippage_pct_major`: allowed slippage on major-asset entries/exits
- `max_slippage_pct_regular`: allowed slippage on regular-token entries/exits
- `max_price_deviation_pct_major`: anti-FOMO gate for majors vs call reference
- `max_price_deviation_pct_regular`: anti-FOMO gate for regular tokens vs call reference

### Quality / liquidity controls

- `min_liquidity_usd_regular`: minimum liquidity for regular-token execution

### Exit defaults

- `default_stop_loss_pct`: fallback stop-loss if signal has no stop
- `default_take_profit_pct`: fallback take-profit if signal has no target
- `max_holding_time_hours`: fallback time-based exit

## 6. Recommended Preset Defaults

These are starting recommendations for v1. They are product defaults, not hard protocol rules.

## 6.1 Safe

```json
{
  "base_style": "safe",
  "major_asset_lane_enabled": true,
  "regular_token_lane_enabled": true,
  "max_amount_per_trade_usd": 300,
  "max_portfolio_risk_pct_per_trade": 0.02,
  "max_active_positions": 3,
  "major_asset_max_amount_usd": 300,
  "regular_token_max_amount_usd": 100,
  "max_slippage_pct_major": 0.5,
  "max_slippage_pct_regular": 2.0,
  "max_price_deviation_pct_major": 2.0,
  "max_price_deviation_pct_regular": 3.0,
  "min_liquidity_usd_regular": 100000,
  "default_stop_loss_pct": 5.0,
  "default_take_profit_pct": 12.0,
  "max_holding_time_hours": 72
}
```

## 6.2 Normal

```json
{
  "base_style": "normal",
  "major_asset_lane_enabled": true,
  "regular_token_lane_enabled": true,
  "max_amount_per_trade_usd": 500,
  "max_portfolio_risk_pct_per_trade": 0.05,
  "max_active_positions": 5,
  "major_asset_max_amount_usd": 500,
  "regular_token_max_amount_usd": 200,
  "max_slippage_pct_major": 1.0,
  "max_slippage_pct_regular": 4.0,
  "max_price_deviation_pct_major": 3.0,
  "max_price_deviation_pct_regular": 5.0,
  "min_liquidity_usd_regular": 50000,
  "default_stop_loss_pct": 7.0,
  "default_take_profit_pct": 20.0,
  "max_holding_time_hours": 96
}
```

## 6.3 Degen

```json
{
  "base_style": "degen",
  "major_asset_lane_enabled": true,
  "regular_token_lane_enabled": true,
  "max_amount_per_trade_usd": 1000,
  "max_portfolio_risk_pct_per_trade": 0.1,
  "max_active_positions": 8,
  "major_asset_max_amount_usd": 1000,
  "regular_token_max_amount_usd": 400,
  "max_slippage_pct_major": 1.5,
  "max_slippage_pct_regular": 8.0,
  "max_price_deviation_pct_major": 5.0,
  "max_price_deviation_pct_regular": 8.0,
  "min_liquidity_usd_regular": 20000,
  "default_stop_loss_pct": 10.0,
  "default_take_profit_pct": 30.0,
  "max_holding_time_hours": 120
}
```

## 7. Chat Update Contract

The user should be able to modify the profile through natural-language messages.

The primary Telegram UX for this is a dedicated command:

- `/trade-style`

Examples:

- `/trade-style`
- `/trade-style safe`
- `/trade-style set max amount per trade to 250`
- `/trade-style disable regular token trades`
- "switch me to safe mode"
- "set max amount per trade to 250"
- "disable regular token trades"
- "set regular token slippage to 3 percent"
- "set holding time to 48 hours"

The application should translate those into structured update commands, validate them, persist them, and return the resolved final profile.

## 8. Validation Rules

Recommended validation:

- `max_amount_per_trade_usd > 0`
- `0 < max_portfolio_risk_pct_per_trade <= 1`
- `max_active_positions >= 1`
- `major_asset_max_amount_usd <= max_amount_per_trade_usd`
- `regular_token_max_amount_usd <= max_amount_per_trade_usd`
- `max_slippage_pct_major >= 0`
- `max_slippage_pct_regular >= 0`
- `max_price_deviation_pct_major >= 0`
- `max_price_deviation_pct_regular >= 0`
- `min_liquidity_usd_regular >= 0`
- `default_stop_loss_pct > 0`
- `default_take_profit_pct > 0`
- `max_holding_time_hours > 0`

## 9. Decision Engine Consumption

Every trade decision must receive this profile as part of its input.

At minimum, the decision engine should use it to:

- enable or disable the relevant asset lane,
- cap trade size,
- set slippage constraints,
- set anti-FOMO thresholds,
- enforce regular-token liquidity minimums,
- provide fallback exit assumptions,
- enforce active-position limits.

## 10. Storage Recommendation

Recommended storage pattern:

- LangGraph store namespace for recall:
  - `("users", "strategy_profile")`
- PostgreSQL source of truth table:
  - `user_strategy_profiles`

The DB remains the authoritative record.
The store is the fast recall layer for agent/runtime use.
