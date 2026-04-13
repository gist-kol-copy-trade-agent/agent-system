from app.tools.ta import TAInput, TATool


def test_major_lane_ta_scoring_positive_momentum() -> None:
    tool = TATool()
    result = tool.compute(
        TAInput(
            asset_lane="major",
            current_price_usd=3200,
            call_reference_price_usd=3150,
            kline_window=[{"close": 3000}, {"close": 3100}, {"close": 3200}],
            liquidity_usd=None,
            min_liquidity_usd_regular=50000,
            max_price_deviation_pct_major=3.0,
            max_price_deviation_pct_regular=5.0,
        )
    )
    assert result.asset_lane == "major"
    assert result.momentum_score is not None and result.momentum_score >= 0.7
    assert result.ta_score > 0.5


def test_regular_lane_liquidity_gate_penalizes_score() -> None:
    tool = TATool()
    result = tool.compute(
        TAInput(
            asset_lane="regular",
            current_price_usd=1.2,
            call_reference_price_usd=1.1,
            kline_window=[{"close": 1.0}, {"close": 1.1}, {"close": 1.2}],
            liquidity_usd=10000,
            min_liquidity_usd_regular=50000,
            max_price_deviation_pct_major=3.0,
            max_price_deviation_pct_regular=5.0,
        )
    )
    assert result.liquidity_gate_passed is False
    assert result.ta_score < 0.3


def test_deviation_gate_penalizes_score() -> None:
    tool = TATool()
    result = tool.compute(
        TAInput(
            asset_lane="regular",
            current_price_usd=1.5,
            call_reference_price_usd=1.0,
            kline_window=[{"close": 1.0}, {"close": 1.2}, {"close": 1.5}],
            liquidity_usd=100000,
            min_liquidity_usd_regular=50000,
            max_price_deviation_pct_major=3.0,
            max_price_deviation_pct_regular=5.0,
        )
    )
    assert result.price_deviation_pct is not None and result.price_deviation_pct > 5.0
    assert result.ta_score < 0.3
