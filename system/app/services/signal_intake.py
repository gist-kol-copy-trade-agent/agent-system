from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.agents.decision import DecisionAgent
from app.agents.parsing import ParsingAgent
from app.graphs.runtime import build_checkpointer
from app.graphs.state import TradingGraphState
from app.policies.trade_policy import DefaultTradePolicyEngine
from app.schemas.domain import ParsedSignal, ResolvedAsset
from app.schemas.strategy import UserStrategyProfile
from app.services.asset_lanes import AssetLaneClassifier
from app.services.strategy_profiles import StrategyProfileService
from app.tools.ta import TAInput, TATool

try:
    from langgraph.graph import END, START, StateGraph
except ModuleNotFoundError:  # pragma: no cover - local scaffold fallback
    END = "__end__"
    START = "__start__"
    StateGraph = None  # type: ignore[assignment]


@dataclass
class SignalIntakeRequest:
    user_id: str
    source_id: str
    message_id: str
    message_text: str


class _SequentialCompiledGraph:
    """Fallback used only when langgraph is not installed in the environment."""

    def __init__(self, service: SignalIntakeGraphService) -> None:
        self.service = service

    def invoke(self, state: TradingGraphState, config: dict[str, Any] | None = None) -> TradingGraphState:
        current = dict(state)
        current.update(self.service._node_ingest_signal(current))
        current.update(self.service._node_parse_signal(current))
        if self.service._route_after_validate_parse(current) == END:
            return current
        current.update(self.service._node_classify_asset_lane(current))
        current.update(self.service._node_resolve_target_asset(current))
        if self.service._route_after_resolve_target_asset(current) == END:
            return current
        current.update(self.service._node_load_strategy_profile(current))
        current.update(self.service._node_load_wallet_context(current))
        current.update(self.service._node_fetch_market_context(current))
        current.update(self.service._node_compute_ta(current))
        current.update(self.service._node_fetch_optional_signal_overlay(current))
        current.update(self.service._node_run_conditional_security_checks(current))
        current.update(self.service._node_decision(current))
        current.update(self.service._node_apply_policy_gate(current))
        return current  # type: ignore[return-value]


class SignalIntakeGraphService:
    """Signal intake workflow backed by LangGraph when available.

    When the `langgraph` package is present, this service compiles a real
    `StateGraph` with explicit nodes and conditional edges. In environments
    where the dependency is not installed yet, it falls back to a sequential
    runner that preserves the same node contract for local scaffold tests.
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
        self.graph = self._build_graph()

    def run(self, request: SignalIntakeRequest, *, thread_id: str | None = None) -> TradingGraphState:
        initial_state = self._initial_state(request)
        config = {"configurable": {"thread_id": thread_id or f"signal:{request.message_id}"}}
        return self.graph.invoke(initial_state, config=config)

    def _initial_state(self, request: SignalIntakeRequest) -> TradingGraphState:
        return {
            "action_type": "signal-intake",
            "source_id": request.source_id,
            "signal_id": request.message_id,
            "position_id": None,
            "messages": [{"role": "user", "content": request.message_text}],
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
            "request_user_id": request.user_id,
        }  # type: ignore[return-value]

    def _build_graph(self):
        if StateGraph is None:
            return _SequentialCompiledGraph(self)

        builder = StateGraph(TradingGraphState)
        builder.add_node("ingest_signal", self._node_ingest_signal)
        builder.add_node("parse_signal", self._node_parse_signal)
        builder.add_node("classify_asset_lane", self._node_classify_asset_lane)
        builder.add_node("resolve_target_asset", self._node_resolve_target_asset)
        builder.add_node("load_strategy_profile", self._node_load_strategy_profile)
        builder.add_node("load_wallet_context", self._node_load_wallet_context)
        builder.add_node("fetch_market_context", self._node_fetch_market_context)
        builder.add_node("compute_ta", self._node_compute_ta)
        builder.add_node("fetch_optional_signal_overlay", self._node_fetch_optional_signal_overlay)
        builder.add_node("run_conditional_security_checks", self._node_run_conditional_security_checks)
        builder.add_node("decision", self._node_decision)
        builder.add_node("apply_policy_gate", self._node_apply_policy_gate)

        builder.add_edge(START, "ingest_signal")
        builder.add_edge("ingest_signal", "parse_signal")
        builder.add_conditional_edges(
            "parse_signal",
            self._route_after_validate_parse,
            {"classify_asset_lane": "classify_asset_lane", END: END},
        )
        builder.add_edge("classify_asset_lane", "resolve_target_asset")
        builder.add_conditional_edges(
            "resolve_target_asset",
            self._route_after_resolve_target_asset,
            {"load_strategy_profile": "load_strategy_profile", END: END},
        )
        builder.add_edge("load_strategy_profile", "load_wallet_context")
        builder.add_edge("load_wallet_context", "fetch_market_context")
        builder.add_edge("fetch_market_context", "compute_ta")
        builder.add_edge("compute_ta", "fetch_optional_signal_overlay")
        builder.add_edge("fetch_optional_signal_overlay", "run_conditional_security_checks")
        builder.add_edge("run_conditional_security_checks", "decision")
        builder.add_edge("decision", "apply_policy_gate")
        builder.add_edge("apply_policy_gate", END)
        return builder.compile(checkpointer=build_checkpointer())

    def _node_ingest_signal(self, state: TradingGraphState) -> dict[str, Any]:
        return {"messages": state["messages"]}

    def _node_parse_signal(self, state: TradingGraphState) -> dict[str, Any]:
        message_text = str(state["messages"][-1]["content"])
        parsed_signal = self.parsing_agent.parse(
            source_id=str(state["source_id"]),
            message_id=str(state["signal_id"]),
            message_text=message_text,
        )
        if parsed_signal["is_actionable"]:
            return {"parsed_signal": parsed_signal}
        return {
            "parsed_signal": parsed_signal,
            "trade_decision": {
                "asset_lane": "regular",
                "decision": "skip",
                "decision_reason_code": "NON_ACTIONABLE_SIGNAL",
                "confidence": parsed_signal["confidence"],
                "recommended_amount_usd": 0,
                "capped_amount_usd": 0,
                "rationale_summary": "Message classified as non-actionable.",
                "telegram_summary": "Signal ignored because it is not a tradeable call.",
            },
        }

    def _route_after_validate_parse(self, state: TradingGraphState) -> str:
        parsed: ParsedSignal = state["parsed_signal"]  # type: ignore[assignment]
        return "classify_asset_lane" if parsed["is_actionable"] else END

    def _node_classify_asset_lane(self, state: TradingGraphState) -> dict[str, Any]:
        parsed: ParsedSignal = state["parsed_signal"]  # type: ignore[assignment]
        asset_lane, target_chain = self.asset_lane_classifier.classify(parsed)
        resolved = ResolvedAsset(
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
        return {"resolved_asset": resolved}

    def _node_resolve_target_asset(self, state: TradingGraphState) -> dict[str, Any]:
        resolved: ResolvedAsset = state["resolved_asset"]  # type: ignore[assignment]
        if resolved["asset_lane"] == "major":
            return {}
        if resolved["token_contract_address"] is None and resolved["normalized_symbol"] == "UNKNOWN":
            return {
                "trade_decision": {
                    "asset_lane": "regular",
                    "decision": "block",
                    "decision_reason_code": "TOKEN_UNRESOLVED",
                    "confidence": 0.0,
                    "recommended_amount_usd": 0,
                    "capped_amount_usd": 0,
                    "rationale_summary": "Regular-token signal could not be resolved.",
                    "telegram_summary": "Trade blocked because token identity could not be resolved.",
                }
            }
        return {}

    def _route_after_resolve_target_asset(self, state: TradingGraphState) -> str:
        decision = state.get("trade_decision")
        if decision and decision.get("decision") == "block":
            return END
        return "load_strategy_profile"

    def _node_load_strategy_profile(self, state: TradingGraphState) -> dict[str, Any]:
        user_id = state.get("request_user_id") or "unknown"
        profile: UserStrategyProfile = self.strategy_profiles.get_or_create(str(user_id))
        return {"strategy_profile": profile.model_dump()}

    def _node_load_wallet_context(self, state: TradingGraphState) -> dict[str, Any]:
        resolved: ResolvedAsset = state["resolved_asset"]  # type: ignore[assignment]
        return {
            "wallet_snapshot": {
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
        }

    def _node_fetch_market_context(self, state: TradingGraphState) -> dict[str, Any]:
        resolved: ResolvedAsset = state["resolved_asset"]  # type: ignore[assignment]
        return {
            "market_snapshot": {
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
        }

    def _node_compute_ta(self, state: TradingGraphState) -> dict[str, Any]:
        resolved: ResolvedAsset = state["resolved_asset"]  # type: ignore[assignment]
        market = state["market_snapshot"] or {}
        strategy = state["strategy_profile"] or {}
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
        return {
            "ta_snapshot": {
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
        }

    def _node_fetch_optional_signal_overlay(self, state: TradingGraphState) -> dict[str, Any]:
        resolved: ResolvedAsset = state["resolved_asset"]  # type: ignore[assignment]
        return {
            "signal_overlay": {
                "supported": resolved["asset_lane"] == "regular",
                "smart_money_count": 2 if resolved["asset_lane"] == "regular" else None,
                "kol_count": 1 if resolved["asset_lane"] == "regular" else None,
                "whale_count": 0 if resolved["asset_lane"] == "regular" else None,
                "overlay_summary": "Stub overlay context.",
            }
        }

    def _node_run_conditional_security_checks(self, state: TradingGraphState) -> dict[str, Any]:
        resolved: ResolvedAsset = state["resolved_asset"]  # type: ignore[assignment]
        if resolved["asset_lane"] == "major":
            return {
                "risk_snapshot": {
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
            }

        return {
            "risk_snapshot": {
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
        }

    def _node_decision(self, state: TradingGraphState) -> dict[str, Any]:
        decision = state.get("trade_decision")
        if decision and decision["decision"] == "block":
            return {"trade_decision": decision}
        return {
            "trade_decision": self.decision_agent.decide(
                parsed_signal=state["parsed_signal"],
                resolved_asset=state["resolved_asset"],
                wallet_snapshot=state["wallet_snapshot"],
                market_snapshot=state["market_snapshot"],
                risk_snapshot=state["risk_snapshot"],
                ta_snapshot=state["ta_snapshot"],
                strategy_profile=state["strategy_profile"],
                signal_overlay=state["signal_overlay"],
            )
        }

    def _node_apply_policy_gate(self, state: TradingGraphState) -> dict[str, Any]:
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
        return {
            "policy_gate_result": {
                "passed": evaluation.passed,
                "action": evaluation.action,
                "failure_codes": evaluation.failure_codes,
                "gate_summary": evaluation.summary,
            }
        }
