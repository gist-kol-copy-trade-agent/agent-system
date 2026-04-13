from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class TAInput:
    asset_lane: str
    current_price_usd: float | None
    call_reference_price_usd: float | None
    kline_window: list[dict[str, Any]]
    liquidity_usd: float | None
    min_liquidity_usd_regular: float
    max_price_deviation_pct_major: float
    max_price_deviation_pct_regular: float


@dataclass
class TAResult:
    asset_lane: str
    call_reference_price_usd: float | None
    current_price_usd: float | None
    price_deviation_pct: float | None
    momentum_score: float | None
    volatility_score: float | None
    liquidity_gate_passed: bool | None
    ta_score: float
    ta_summary: str


class TATool:
    """Deterministic TA helper for PoC/V1.

    This is intentionally simple and rule-based:
    - price deviation gate
    - simple momentum from recent closes
    - simple volatility estimate
    - regular-token liquidity gate
    """

    def compute(self, ta_input: TAInput) -> TAResult:
        deviation = self._price_deviation_pct(
            current_price_usd=ta_input.current_price_usd,
            call_reference_price_usd=ta_input.call_reference_price_usd,
        )
        momentum = self._momentum_score(ta_input.kline_window)
        volatility = self._volatility_score(ta_input.kline_window)
        liquidity_gate = self._liquidity_gate(
            asset_lane=ta_input.asset_lane,
            liquidity_usd=ta_input.liquidity_usd,
            min_liquidity_usd_regular=ta_input.min_liquidity_usd_regular,
        )
        deviation_gate = self._deviation_gate(
            asset_lane=ta_input.asset_lane,
            deviation_pct=deviation,
            max_price_deviation_pct_major=ta_input.max_price_deviation_pct_major,
            max_price_deviation_pct_regular=ta_input.max_price_deviation_pct_regular,
        )
        ta_score = self._compose_score(
            asset_lane=ta_input.asset_lane,
            momentum=momentum,
            volatility=volatility,
            liquidity_gate=liquidity_gate,
            deviation_gate=deviation_gate,
        )

        summary_parts = []
        if deviation is not None:
            summary_parts.append(f"deviation={deviation:.2f}%")
        if momentum is not None:
            summary_parts.append(f"momentum={momentum:.2f}")
        if volatility is not None:
            summary_parts.append(f"volatility={volatility:.2f}")
        if liquidity_gate is not None:
            summary_parts.append(f"liquidity_gate={liquidity_gate}")
        summary_parts.append(f"ta_score={ta_score:.2f}")

        return TAResult(
            asset_lane=ta_input.asset_lane,
            call_reference_price_usd=ta_input.call_reference_price_usd,
            current_price_usd=ta_input.current_price_usd,
            price_deviation_pct=deviation,
            momentum_score=momentum,
            volatility_score=volatility,
            liquidity_gate_passed=liquidity_gate,
            ta_score=ta_score,
            ta_summary=", ".join(summary_parts),
        )

    def _price_deviation_pct(self, *, current_price_usd: float | None, call_reference_price_usd: float | None) -> float | None:
        if not current_price_usd or not call_reference_price_usd:
            return None
        if call_reference_price_usd == 0:
            return None
        return ((current_price_usd - call_reference_price_usd) / call_reference_price_usd) * 100

    def _momentum_score(self, kline_window: list[dict[str, Any]]) -> float | None:
        closes = self._extract_closes(kline_window)
        if len(closes) < 2:
            return 0.5 if closes else None
        first, last = closes[0], closes[-1]
        if first == 0:
            return None
        change_pct = ((last - first) / first) * 100
        if change_pct <= -5:
            return 0.1
        if change_pct <= 0:
            return 0.35
        if change_pct <= 5:
            return 0.7
        return 0.9

    def _volatility_score(self, kline_window: list[dict[str, Any]]) -> float | None:
        closes = self._extract_closes(kline_window)
        if len(closes) < 2:
            return 0.5 if closes else None
        spread = max(closes) - min(closes)
        mean_price = sum(closes) / len(closes)
        if mean_price == 0:
            return None
        volatility_pct = (spread / mean_price) * 100
        if volatility_pct <= 2:
            return 0.9
        if volatility_pct <= 5:
            return 0.75
        if volatility_pct <= 10:
            return 0.55
        return 0.3

    def _liquidity_gate(self, *, asset_lane: str, liquidity_usd: float | None, min_liquidity_usd_regular: float) -> bool | None:
        if asset_lane == "major":
            return None
        if liquidity_usd is None:
            return False
        return liquidity_usd >= min_liquidity_usd_regular

    def _deviation_gate(
        self,
        *,
        asset_lane: str,
        deviation_pct: float | None,
        max_price_deviation_pct_major: float,
        max_price_deviation_pct_regular: float,
    ) -> bool:
        if deviation_pct is None:
            return True
        threshold = max_price_deviation_pct_major if asset_lane == "major" else max_price_deviation_pct_regular
        return deviation_pct <= threshold

    def _compose_score(
        self,
        *,
        asset_lane: str,
        momentum: float | None,
        volatility: float | None,
        liquidity_gate: bool | None,
        deviation_gate: bool,
    ) -> float:
        base = 0.5
        if momentum is not None:
            base = 0.6 * momentum + 0.4 * (volatility if volatility is not None else 0.5)
        if not deviation_gate:
            base *= 0.3
        if asset_lane == "regular" and liquidity_gate is False:
            base *= 0.2
        return max(0.0, min(base, 1.0))

    def _extract_closes(self, kline_window: list[dict[str, Any]]) -> list[float]:
        closes: list[float] = []
        for candle in kline_window:
            raw_close = candle.get("close", candle.get("c"))
            try:
                closes.append(float(raw_close))
            except (TypeError, ValueError):
                continue
        return closes
