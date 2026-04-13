from typing import Any, TypedDict

from app.schemas.domain import (
    MarketSnapshot,
    ParsedSignal,
    ResolvedAsset,
    RiskSnapshot,
    TASnapshot,
    WalletSnapshot,
)
from app.schemas.strategy import UserStrategyProfile


class TradingGraphState(TypedDict):
    messages: list[Any]
    action_type: str
    source_id: str | None
    signal_id: str | None
    position_id: str | None
    parsed_signal: ParsedSignal | None
    resolved_asset: ResolvedAsset | None
    wallet_snapshot: WalletSnapshot | None
    market_snapshot: MarketSnapshot | None
    risk_snapshot: RiskSnapshot | None
    ta_snapshot: TASnapshot | None
    strategy_profile: UserStrategyProfile | None
    telegram_summary: str | None
