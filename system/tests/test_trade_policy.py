from app.agents.decision import DecisionAgentConfig
from app.policies.trade_policy import DefaultTradePolicyEngine


def build_context(lane: str = "major") -> dict:
    return {
        "trade_decision": {
            "decision": "execute",
            "decision_reason_code": "READY_FOR_POLICY_GATE",
            "capped_amount_usd": 100,
        },
        "resolved_asset": {
            "asset_lane": lane,
            "approved_major_mapping": "ETH" if lane == "major" else None,
            "token_contract_address": "0xtoken" if lane == "regular" else None,
        },
        "wallet_snapshot": {
            "logged_in": True,
            "wallet_address": "0xwallet",
            "available_balance_usd": 1000,
        },
        "market_snapshot": {
            "quote_available": True,
            "liquidity_usd": 100000 if lane == "regular" else None,
            "quote_price_impact_pct": 0.2,
        },
        "risk_snapshot": {
            "risk_scan_required": lane == "regular",
            "risk_scan_supported": True,
            "is_risk_token": False,
            "dev_rug_pull_token_count": 0,
            "top10_hold_percent": 10,
            "buy_tax_pct": 0,
            "sell_tax_pct": 0,
        },
        "ta_snapshot": {
            "ta_score": 0.8 if lane == "major" else 0.8,
            "price_deviation_pct": 1.0,
        },
        "strategy_profile": {
            "major_asset_lane_enabled": True,
            "regular_token_lane_enabled": True,
            "min_liquidity_usd_regular": 50000,
            "max_active_positions": 3,
            "max_slippage_pct_major": 0.5,
            "max_slippage_pct_regular": 2.0,
            "max_price_deviation_pct_major": 3.0,
            "max_price_deviation_pct_regular": 5.0,
        },
        "active_position_count": 0,
    }


def test_policy_engine_allows_major_execution() -> None:
    engine = DefaultTradePolicyEngine(DecisionAgentConfig())
    result = engine.evaluate(build_context("major"))
    assert result.passed is True
    assert result.action == "execute"


def test_policy_engine_blocks_regular_risk_token() -> None:
    engine = DefaultTradePolicyEngine(DecisionAgentConfig())
    context = build_context("regular")
    context["risk_snapshot"]["is_risk_token"] = True
    result = engine.evaluate(context)
    assert result.passed is False
    assert result.action == "block"
    assert "TOKEN_RISK_BLOCKED" in result.failure_codes


def test_policy_engine_skips_major_when_ta_weak() -> None:
    engine = DefaultTradePolicyEngine(DecisionAgentConfig())
    context = build_context("major")
    context["ta_snapshot"]["ta_score"] = 0.1
    result = engine.evaluate(context)
    assert result.passed is False
    assert result.action == "skip"
    assert "MAJOR_TA_WEAK" in result.failure_codes


def test_policy_engine_blocks_regular_when_liquidity_too_low() -> None:
    engine = DefaultTradePolicyEngine(DecisionAgentConfig())
    context = build_context("regular")
    context["market_snapshot"]["liquidity_usd"] = 1000
    result = engine.evaluate(context)
    assert result.passed is False
    assert result.action == "block"
    assert "REGULAR_LIQUIDITY_TOO_LOW" in result.failure_codes


def test_policy_engine_skips_when_max_active_positions_reached() -> None:
    engine = DefaultTradePolicyEngine(DecisionAgentConfig())
    context = build_context("major")
    context["active_position_count"] = 3
    result = engine.evaluate(context)
    assert result.passed is False
    assert result.action == "skip"
    assert "MAX_ACTIVE_POSITIONS_REACHED" in result.failure_codes


def test_policy_engine_blocks_when_price_impact_too_high() -> None:
    engine = DefaultTradePolicyEngine(DecisionAgentConfig())
    context = build_context("regular")
    context["market_snapshot"]["quote_price_impact_pct"] = 5.0
    result = engine.evaluate(context)
    assert result.passed is False
    assert result.action == "block"
    assert "PRICE_IMPACT_TOO_HIGH" in result.failure_codes


def test_policy_engine_skips_when_deviation_too_high() -> None:
    engine = DefaultTradePolicyEngine(DecisionAgentConfig())
    context = build_context("major")
    context["ta_snapshot"]["price_deviation_pct"] = 8.0
    result = engine.evaluate(context)
    assert result.passed is False
    assert result.action == "skip"
    assert "MAJOR_FOMO_TOO_HIGH" in result.failure_codes
