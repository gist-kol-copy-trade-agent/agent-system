from __future__ import annotations

import re
from copy import deepcopy

from app.persistence.repositories import StrategyProfileRepository, utc_now_iso
from app.schemas.strategy import StrategyProfilePatch, TradingStyle, UserStrategyProfile


PRESET_PROFILES: dict[TradingStyle, dict] = {
    "safe": {
        "major_asset_lane_enabled": True,
        "regular_token_lane_enabled": True,
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
        "max_holding_time_hours": 72,
        "trailing_enabled": True,
        "trailing_activation_profit_pct": 8.0,
        "trailing_drawdown_pct": 4.0,
    },
    "normal": {
        "major_asset_lane_enabled": True,
        "regular_token_lane_enabled": True,
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
        "max_holding_time_hours": 96,
        "trailing_enabled": True,
        "trailing_activation_profit_pct": 12.0,
        "trailing_drawdown_pct": 6.0,
    },
    "degen": {
        "major_asset_lane_enabled": True,
        "regular_token_lane_enabled": True,
        "max_amount_per_trade_usd": 1000,
        "max_portfolio_risk_pct_per_trade": 0.10,
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
        "max_holding_time_hours": 120,
        "trailing_enabled": True,
        "trailing_activation_profit_pct": 18.0,
        "trailing_drawdown_pct": 8.0,
    },
}


class StrategyProfileService:
    def __init__(self, repository: StrategyProfileRepository) -> None:
        self.repository = repository

    def get_or_create(self, user_id: str, base_style: TradingStyle = "normal") -> UserStrategyProfile:
        existing = self.repository.get(user_id)
        if existing:
            return existing
        return self.apply_preset(user_id=user_id, base_style=base_style, updated_by="system")

    def apply_preset(self, *, user_id: str, base_style: TradingStyle, updated_by: str) -> UserStrategyProfile:
        payload = deepcopy(PRESET_PROFILES[base_style])
        profile = UserStrategyProfile(
            user_id=user_id,
            base_style=base_style,
            updated_at=utc_now_iso(),
            updated_by=updated_by,
            version=(self.repository.get(user_id).version + 1) if self.repository.get(user_id) else 1,
            **payload,
        )
        return self.repository.save(profile)

    def apply_patch(self, *, user_id: str, patch: StrategyProfilePatch, updated_by: str) -> UserStrategyProfile:
        current = self.get_or_create(user_id)
        merged = current.model_dump()
        for key, value in patch.model_dump(exclude_none=True).items():
            merged[key] = value
        merged["updated_at"] = utc_now_iso()
        merged["updated_by"] = updated_by
        merged["version"] = current.version + 1
        profile = UserStrategyProfile(**merged)
        return self.repository.save(profile)

    def parse_trade_style_text(self, raw_text: str) -> tuple[TradingStyle | None, StrategyProfilePatch | None]:
        text = raw_text.strip().lower()
        if text in {"/trade-style", "trade-style"}:
            return None, None

        for preset in ("safe", "normal", "degen"):
            if text in {f"/trade-style {preset}", preset, f"trade-style {preset}"}:
                return preset, None

        patch: dict = {}
        if "disable regular token" in text:
            patch["regular_token_lane_enabled"] = False
        if "enable regular token" in text:
            patch["regular_token_lane_enabled"] = True
        if "disable major" in text:
            patch["major_asset_lane_enabled"] = False
        if "enable major" in text:
            patch["major_asset_lane_enabled"] = True

        numeric_patterns = {
            "max_amount_per_trade_usd": r"max amount per trade to (\d+(?:\.\d+)?)",
            "major_asset_max_amount_usd": r"major trades? to max (\d+(?:\.\d+)?)",
            "regular_token_max_amount_usd": r"regular token max amount to (\d+(?:\.\d+)?)",
            "max_slippage_pct_regular": r"regular token slippage to (\d+(?:\.\d+)?)",
            "max_holding_time_hours": r"holding time to (\d+)",
            "trailing_activation_profit_pct": r"trailing activation(?: profit)? to (\d+(?:\.\d+)?)",
            "trailing_drawdown_pct": r"trailing drawdown to (\d+(?:\.\d+)?)",
        }
        for field, pattern in numeric_patterns.items():
            match = re.search(pattern, text)
            if match:
                value = float(match.group(1))
                if field == "max_holding_time_hours":
                    value = int(value)
                patch[field] = value

        if not patch:
            return None, None
        return None, StrategyProfilePatch(**patch)
