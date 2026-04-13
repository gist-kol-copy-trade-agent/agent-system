from typing import Literal

from pydantic import BaseModel, Field


TradingStyle = Literal["degen", "normal", "safe"]


class UserStrategyProfile(BaseModel):
    user_id: str
    base_style: TradingStyle
    major_asset_lane_enabled: bool = True
    regular_token_lane_enabled: bool = True
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
    updated_at: str | None = None
    updated_by: str = "system"
    version: int = 1


class StrategyProfilePatch(BaseModel):
    base_style: TradingStyle | None = None
    major_asset_lane_enabled: bool | None = None
    regular_token_lane_enabled: bool | None = None
    max_amount_per_trade_usd: float | None = None
    max_portfolio_risk_pct_per_trade: float | None = None
    max_active_positions: int | None = None
    major_asset_max_amount_usd: float | None = None
    regular_token_max_amount_usd: float | None = None
    max_slippage_pct_major: float | None = None
    max_slippage_pct_regular: float | None = None
    max_price_deviation_pct_major: float | None = None
    max_price_deviation_pct_regular: float | None = None
    min_liquidity_usd_regular: float | None = None
    default_stop_loss_pct: float | None = None
    default_take_profit_pct: float | None = None
    max_holding_time_hours: int | None = None
