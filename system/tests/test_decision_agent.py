from app.agents.decision import DecisionAgent


class FakeDecisionBackend:
    def decide(
        self,
        *,
        parsed_signal,
        resolved_asset,
        wallet_snapshot,
        market_snapshot,
        risk_snapshot,
        ta_snapshot,
        strategy_profile,
        signal_overlay,
    ):
        if resolved_asset["asset_lane"] == "major" and not strategy_profile["major_asset_lane_enabled"]:
            return {
                "asset_lane": "major",
                "decision": "skip",
                "decision_reason_code": "MAJOR_LANE_DISABLED",
                "confidence": parsed_signal["confidence"],
                "recommended_amount_usd": 0,
                "capped_amount_usd": 0,
                "rationale_summary": "Lane disabled",
                "telegram_summary": "skip",
            }
        if resolved_asset["asset_lane"] == "regular" and risk_snapshot["is_risk_token"] is True:
            return {
                "asset_lane": "regular",
                "decision": "block",
                "decision_reason_code": "TOKEN_RISK_BLOCKED",
                "confidence": parsed_signal["confidence"],
                "recommended_amount_usd": 0,
                "capped_amount_usd": 0,
                "rationale_summary": "Risk token",
                "telegram_summary": "block",
            }
        if resolved_asset["asset_lane"] == "regular" and (risk_snapshot["dev_rug_pull_token_count"] or 0) > 0:
            return {
                "asset_lane": "regular",
                "decision": "skip",
                "decision_reason_code": "DEV_RUG_HISTORY_PRESENT",
                "confidence": parsed_signal["confidence"],
                "recommended_amount_usd": 0,
                "capped_amount_usd": 0,
                "rationale_summary": "Rug history",
                "telegram_summary": "skip",
            }
        amount = 500 if resolved_asset["asset_lane"] == "major" else 200
        return {
            "asset_lane": resolved_asset["asset_lane"],
            "decision": "execute",
            "decision_reason_code": "READY_FOR_POLICY_GATE",
            "confidence": parsed_signal["confidence"],
            "recommended_amount_usd": amount,
            "capped_amount_usd": amount,
            "rationale_summary": "Ready",
            "telegram_summary": "execute",
        }


def build_common_major_inputs():
    return {
        "parsed_signal": {
            "message_type": "trade_call",
            "confidence": 0.8,
        },
        "resolved_asset": {
            "asset_lane": "major",
            "token_contract_address": None,
        },
        "wallet_snapshot": {
            "logged_in": True,
            "available_balance_usd": 1000,
        },
        "market_snapshot": {
            "liquidity_usd": None,
        },
        "risk_snapshot": {
            "is_risk_token": None,
            "dev_rug_pull_token_count": None,
        },
        "ta_snapshot": {
            "ta_score": 0.8,
        },
        "strategy_profile": {
            "major_asset_lane_enabled": True,
            "regular_token_lane_enabled": True,
            "major_asset_max_amount_usd": 500,
            "regular_token_max_amount_usd": 200,
            "max_amount_per_trade_usd": 1000,
            "min_liquidity_usd_regular": 50000,
        },
        "signal_overlay": None,
    }


def build_common_regular_inputs():
    return {
        "parsed_signal": {
            "message_type": "trade_call",
            "confidence": 0.75,
        },
        "resolved_asset": {
            "asset_lane": "regular",
            "token_contract_address": "0xtoken",
        },
        "wallet_snapshot": {
            "logged_in": True,
            "available_balance_usd": 1000,
        },
        "market_snapshot": {
            "liquidity_usd": 100000,
        },
        "risk_snapshot": {
            "is_risk_token": False,
            "dev_rug_pull_token_count": 0,
        },
        "ta_snapshot": {
            "ta_score": 0.8,
        },
        "strategy_profile": {
            "major_asset_lane_enabled": True,
            "regular_token_lane_enabled": True,
            "major_asset_max_amount_usd": 500,
            "regular_token_max_amount_usd": 200,
            "max_amount_per_trade_usd": 1000,
            "min_liquidity_usd_regular": 50000,
        },
        "signal_overlay": {"smart_money_count": 2},
    }


def test_major_lane_execute_decision() -> None:
    agent = DecisionAgent(backend=FakeDecisionBackend())
    inputs = build_common_major_inputs()
    result = agent.decide(**inputs)
    assert result["decision"] == "execute"
    assert result["asset_lane"] == "major"
    assert result["recommended_amount_usd"] == 500


def test_regular_lane_blocks_on_risk_token() -> None:
    agent = DecisionAgent(backend=FakeDecisionBackend())
    inputs = build_common_regular_inputs()
    inputs["risk_snapshot"]["is_risk_token"] = True
    result = agent.decide(**inputs)
    assert result["decision"] == "block"
    assert result["decision_reason_code"] == "TOKEN_RISK_BLOCKED"


def test_regular_lane_skips_on_dev_rug_history() -> None:
    agent = DecisionAgent(backend=FakeDecisionBackend())
    inputs = build_common_regular_inputs()
    inputs["risk_snapshot"]["dev_rug_pull_token_count"] = 3
    result = agent.decide(**inputs)
    assert result["decision"] == "skip"
    assert result["decision_reason_code"] == "DEV_RUG_HISTORY_PRESENT"


def test_lane_disabled_skips() -> None:
    agent = DecisionAgent(backend=FakeDecisionBackend())
    inputs = build_common_major_inputs()
    inputs["strategy_profile"]["major_asset_lane_enabled"] = False
    result = agent.decide(**inputs)
    assert result["decision"] == "skip"
    assert result["decision_reason_code"] == "MAJOR_LANE_DISABLED"
