from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.agents.parsing import ParsingAgent
from app.agents.decision import DecisionAgent
from app.policies.trade_policy import DefaultTradePolicyEngine
from app.schemas.domain import ParsedSignal, ResolvedAsset
from app.schemas.strategy import UserStrategyProfile
from app.services.asset_lanes import AssetLaneClassifier
from app.services.strategy_profiles import StrategyProfileService
from app.tools.ta import TAInput, TATool


@dataclass
class SignalIntakeRequest:
    user_id: str
    source_id: str
    message_id: str
    message_text: str


class SignalIntakeGraphService:
    """Phase 3.2 orchestration scaffold for signal intake.

    This service mirrors the graph-level flow from the architecture docs using
    deterministic Python nodes. Later phases can replace the linear execution
    with a compiled LangGraph workflow without changing the contract.
    """

    def __init__(
        self,
        *,
        parsing_agent: ParsingAgent,
        strategy_profiles: StrategyProfileService,
        decision_agent: DecisionAgent | None = None,
        policy_engine: DefaultTradePolicyEngine | None = None,
    ) -> None:
        self.parsing_agent = parsing_agent
        self.strategy_profiles = strategy_profiles
        self.asset_lane_classifier = AssetLaneClassifier()
        self.ta_tool = TATool()
        self.decision_agent = decision_agent or DecisionAgent()
        self.policy_engine = policy_engine or DefaultTradePolicyEngine()

    def run(self, request: SignalIntakeRequest) -> dict[str, Any]:
        state: dict[str, Any] = {
            "action_type": "signal-intake",
            "source_id": request.source_id,
            "signal_id": request.message_id,
            "position_id": None,
            "messages": [],
            "parsed_signal": None,
            "resolved_asset": None,
            "wallet_snapshot": None,
            "market_snapshot": None,
            "risk_snapshot": None,
            "ta_snapshot": None,
            "strategy_profile": None,
            "trade_decision": None,
            "policy_gate_result": None,
            "execution_request": None,
            "execution_result": None,
            "telegram_summary": None,
            "signal_overlay": None,
        }

        self._ingest_signal(state, request)
        self._parse_signal(state, request)
        if self._validate_parse(state) is False:
            return state

        self._classify_asset_lane(state)
        self._resolve_target_asset(state)
        self._load_strategy_profile(state, request.user_id)
        self._load_wallet_context(state)
        self._fetch_market_context(state)
        self._compute_ta(state)
        self._fetch_optional_signal_overlay(state)
        self._run_conditional_security_checks(state)
        self._decision_node(state)
        self._apply_policy_gate(state)
        return state

    def _ingest_signal(self, state: dict[str, Any], request: SignalIntakeRequest) -> None:
        state["messages"] = [{"role": "user", "content": request.message_text}]

    def _parse_signal(self, state: dict[str, Any], request: SignalIntakeRequest) -> None:
        state["parsed_signal"] = self.parsing_agent.parse(
            source_id=request.source_id,
            message_id=request.message_id,
            message_text=request.message_text,
        )

    def _validate_parse(self, state: dict[str, Any]) -> bool:
        parsed: ParsedSignal = state["parsed_signal"]
        if not parsed["is_actionable"]:
            state["trade_decision"] = {
                "asset_lane": "regular",
                "decision": "skip",
                "decision_reason_code": "NON_ACTIONABLE_SIGNAL",
                "confidence": parsed["confidence"],
                "recommended_amount_usd": 0,
                "capped_amount_usd": 0,
                "rationale_summary": "Message classified as non-actionable.",
                "telegram_summary": "Signal ignored because it is not a tradeable call.",
            }
            return False
        return True

    def _classify_asset_lane(self, state: dict[str, Any]) -> None:
        parsed: ParsedSignal = state["parsed_signal"]
        asset_lane, target_chain = self.asset_lane_classifier.classify(parsed)
        state["resolved_asset"] = ResolvedAsset(
            asset_lane=asset_lane,
            normalized_symbol=(parsed["raw_symbol"] or "UNKNOWN").upper(),
            target_execution_chain=target_chain or "unknown",
            resolved_signal_chain=parsed["raw_chain_hint"],
            token_contract_address=parsed["raw_contract_address"],
            token_name=None,
            decimals=None,
            is_native=asset_lane == "major",
            approved_major_mapping=(parsed["raw_symbol"] or "").upper() if asset_lane == "major" else None,
            resolution_confidence=parsed["confidence"],
        )

    def _resolve_target_asset(self, state: dict[str, Any]) -> None:
        resolved: ResolvedAsset = state["resolved_asset"]
        if resolved["asset_lane"] == "major":
            return

        if resolved["token_contract_address"] is None and resolved["normalized_symbol"] == "UNKNOWN":
            state["trade_decision"] = {
                "asset_lane": "regular",
                "decision": "block",
                "decision_reason_code": "TOKEN_UNRESOLVED",
                "confidence": 0.0,
                "recommended_amount_usd": 0,
                "capped_amount_usd": 0,
                "rationale_summary": "Regular-token signal could not be resolved.",
                "telegram_summary": "Trade blocked because token identity could not be resolved.",
            }

    def _load_strategy_profile(self, state: dict[str, Any], user_id: str) -> None:
        profile: UserStrategyProfile = self.strategy_profiles.get_or_create(user_id)
        state["strategy_profile"] = profile.model_dump()

    def _load_wallet_context(self, state: dict[str, Any]) -> None:
        resolved: ResolvedAsset = state["resolved_asset"]
        state["wallet_snapshot"] = {
            "logged_in": True,
            "account_id": "stub-account",
            "account_name": "Stub Wallet",
            "target_chain": resolved["target_execution_chain"],
            "wallet_address": "stub-wallet-address",
            "available_balance_usd": 1000.0,
            "available_balance_token": None,
            "policy_single_tx_limit_usd": None,
            "policy_daily_trade_limit_usd": None,
            "policy_daily_trade_used_usd": None,
        }

    def _fetch_market_context(self, state: dict[str, Any]) -> None:
        resolved: ResolvedAsset = state["resolved_asset"]
        state["market_snapshot"] = {
            "asset_lane": resolved["asset_lane"],
            "chain": resolved["target_execution_chain"],
            "spot_price_usd": 100.0 if resolved["asset_lane"] == "regular" else 3200.0,
            "market_cap_usd": 1000000.0 if resolved["asset_lane"] == "regular" else None,
            "liquidity_usd": 200000.0 if resolved["asset_lane"] == "regular" else None,
            "volume_24h_usd": 500000.0,
            "price_change_24h_pct": 4.2,
            "kline_window": [{"close": 100}, {"close": 105}],
            "quote_available": True,
            "quote_price_impact_pct": 0.5,
        }

    def _compute_ta(self, state: dict[str, Any]) -> None:
        resolved: ResolvedAsset = state["resolved_asset"]
        market = state["market_snapshot"]
        strategy = state["strategy_profile"]
        result = self.ta_tool.compute(
            TAInput(
                asset_lane=resolved["asset_lane"],
                current_price_usd=market["spot_price_usd"],
                call_reference_price_usd=None,
                kline_window=market["kline_window"],
                liquidity_usd=market["liquidity_usd"],
                min_liquidity_usd_regular=strategy["min_liquidity_usd_regular"],
                max_price_deviation_pct_major=strategy["max_price_deviation_pct_major"],
                max_price_deviation_pct_regular=strategy["max_price_deviation_pct_regular"],
            )
        )
        state["ta_snapshot"] = {
            "asset_lane": result.asset_lane,
            "call_reference_price_usd": result.call_reference_price_usd,
            "current_price_usd": result.current_price_usd,
            "price_deviation_pct": result.price_deviation_pct,
            "momentum_score": result.momentum_score,
            "volatility_score": result.volatility_score,
            "liquidity_gate_passed": result.liquidity_gate_passed,
            "ta_score": result.ta_score,
            "ta_summary": result.ta_summary,
        }

    def _fetch_optional_signal_overlay(self, state: dict[str, Any]) -> None:
        resolved: ResolvedAsset = state["resolved_asset"]
        state["signal_overlay"] = {
            "supported": resolved["asset_lane"] == "regular",
            "smart_money_count": 2 if resolved["asset_lane"] == "regular" else None,
            "kol_count": 1 if resolved["asset_lane"] == "regular" else None,
            "whale_count": 0 if resolved["asset_lane"] == "regular" else None,
            "overlay_summary": "Stub overlay context.",
        }

    def _run_conditional_security_checks(self, state: dict[str, Any]) -> None:
        resolved: ResolvedAsset = state["resolved_asset"]
        if resolved["asset_lane"] == "major":
            state["risk_snapshot"] = {
                "asset_lane": "major",
                "risk_scan_required": False,
                "risk_scan_supported": False,
                "is_risk_token": None,
                "buy_tax_pct": None,
                "sell_tax_pct": None,
                "risk_control_level": None,
                "token_tags": [],
                "dev_rug_pull_token_count": None,
                "dev_create_token_count": None,
                "top10_hold_percent": None,
                "lp_burned_percent": None,
                "creator_address": None,
                "risk_summary": "Major-asset lane skips regular-token risk scan.",
            }
            return

        state["risk_snapshot"] = {
            "asset_lane": "regular",
            "risk_scan_required": True,
            "risk_scan_supported": True,
            "is_risk_token": False,
            "buy_tax_pct": 0.0,
            "sell_tax_pct": 0.0,
            "risk_control_level": "1",
            "token_tags": ["communityRecognized"],
            "dev_rug_pull_token_count": 0,
            "dev_create_token_count": 2,
            "top10_hold_percent": 15.0,
            "lp_burned_percent": 80.0,
            "creator_address": "stub-creator",
            "risk_summary": "Stub regular-token risk context.",
        }

    def _decision_node(self, state: dict[str, Any]) -> None:
        if state.get("trade_decision") and state["trade_decision"]["decision"] == "block":
            return
        state["trade_decision"] = self.decision_agent.decide(
            parsed_signal=state["parsed_signal"],
            resolved_asset=state["resolved_asset"],
            wallet_snapshot=state["wallet_snapshot"],
            market_snapshot=state["market_snapshot"],
            risk_snapshot=state["risk_snapshot"],
            ta_snapshot=state["ta_snapshot"],
            strategy_profile=state["strategy_profile"],
            signal_overlay=state["signal_overlay"],
        )

    def _apply_policy_gate(self, state: dict[str, Any]) -> None:
        evaluation = self.policy_engine.evaluate(
            {
                "trade_decision": state["trade_decision"],
                "resolved_asset": state["resolved_asset"],
                "wallet_snapshot": state["wallet_snapshot"],
                "market_snapshot": state["market_snapshot"],
                "risk_snapshot": state["risk_snapshot"],
                "ta_snapshot": state["ta_snapshot"],
                "strategy_profile": state["strategy_profile"],
            }
        )
        state["policy_gate_result"] = {
            "passed": evaluation.passed,
            "action": evaluation.action,
            "failure_codes": evaluation.failure_codes,
            "gate_summary": evaluation.summary,
        }
