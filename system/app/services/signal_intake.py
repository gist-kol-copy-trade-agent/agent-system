from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from typing import Any

from app.agents.decision import DecisionAgent
from app.agents.enrichment import EnrichmentAgent
from app.agents.parsing import ParsingAgent
from app.agents.swap_execution import CallableSwapExecutionBackend, SwapExecutionAgent
from app.config.settings import get_settings
from app.graphs.runtime import build_checkpointer, invoke_graph
from app.graphs.state import TradingGraphState
from app.persistence.repositories import (
    PositionEventRecord,
    PositionEventRepository,
    PositionRecord,
    PositionRepository,
    TradeExecutionRecord,
    TradeExecutionRepository,
    WalletSessionRepository,
    utc_now_iso,
)
from app.policies.trade_policy import DefaultTradePolicyEngine
from app.schemas.domain import DecisionExplanation, EnrichmentExplanation, ParseExplanation, ParsedSignal, ResolvedAsset
from app.services.asset_resolution import AssetResolver, MajorAssetRegistry
from app.schemas.strategy import UserStrategyProfile
from app.services.asset_lanes import AssetLaneClassifier
from app.services.notifications import NotificationService
from app.services.onchainos_runner import OnchainOSCommandError, OnchainOSMutatingRunner
from app.services.strategy_profiles import StrategyProfileService
from app.services.wallet_resolution import WalletAddressResolver
from app.tools.ta import TAInput, TATool

try:
    from langgraph.graph import END, START, StateGraph
except ModuleNotFoundError:  # pragma: no cover - local scaffold fallback
    END = "__end__"
    START = "__start__"
    StateGraph = None  # type: ignore[assignment]

try:
    from langgraph.func import task
except ModuleNotFoundError:  # pragma: no cover
    def task(func):
        return func


def _resolve_task_result(value):
    return value.result() if hasattr(value, "result") else value


@task
def _execute_trade_task(swap_execution_agent: SwapExecutionAgent, *, intent: dict[str, Any]) -> dict[str, Any]:
    return swap_execution_agent.execute(intent=intent)


@dataclass
class SignalIntakeRequest:
    user_id: str
    source_id: str
    message_id: str
    message_text: str
    media_blobs: list[dict[str, Any]] | None = None


class TradeExecutionRunner(Protocol):
    def execute(self, request: dict[str, Any]) -> dict[str, Any]: ...


class OnchainOSSwapBuyExecutionRunner:
    def __init__(self, runner: OnchainOSMutatingRunner | None = None) -> None:
        self.runner = runner or OnchainOSMutatingRunner()

    def execute(self, request: dict[str, Any]) -> dict[str, Any]:
        command = self._build_command(request)
        try:
            result = self.runner.run(command)
        except OnchainOSCommandError as exc:
            return {
                "signal_id": request["signal_id"],
                "success": False,
                "execution_id": None,
                "approve_tx_hash": None,
                "swap_tx_hash": None,
                "received_token_amount": None,
                "received_token_symbol": request["to_token"],
                "error_code": "ONCHAINOS_EXECUTION_ERROR",
                "error_message": str(exc),
            }

        payload = result.get("payload") if isinstance(result, dict) else None
        data = payload.get("data", payload) if isinstance(payload, dict) else {}
        if isinstance(data, list):
            data = data[0] if data else {}
        return {
            "signal_id": request["signal_id"],
            "success": bool(result.get("ok")),
            "execution_id": data.get("requestId") or data.get("executionId") or data.get("swapTxHash"),
            "approve_tx_hash": data.get("approveTxHash"),
            "swap_tx_hash": data.get("swapTxHash") or data.get("txHash"),
            "received_token_amount": data.get("toAmount") or data.get("outputAmount"),
            "received_token_symbol": data.get("toTokenSymbol") or request["to_token"],
            "error_code": None if result.get("ok") else "SWAP_EXECUTE_FAILED",
            "error_message": result.get("error"),
            "raw_result": result,
        }

    @staticmethod
    def _build_command(request: dict[str, Any]) -> str:
        parts = [
            "onchainos",
            "swap",
            "execute",
            "--from",
            str(request["from_token"]),
            "--to",
            str(request["to_token"]),
            "--readable-amount",
            str(request["readable_amount"]),
            "--chain",
            str(request["chain"]),
            "--wallet",
            str(request["wallet_address"]),
        ]
        if request.get("slippage_pct") is not None:
            parts.extend(["--slippage", str(request["slippage_pct"])])
        return " ".join(parts)


class _NullTradeExecutionRepository:
    def save(self, record: TradeExecutionRecord) -> TradeExecutionRecord:
        if not record.created_at:
            record.created_at = utc_now_iso()
        return record


class _NullPositionRepository:
    def list_by_user(self, user_id: str) -> list[Any]:
        return []

    def save(self, record: PositionRecord) -> PositionRecord:
        return record


class _NullPositionEventRepository:
    def save(self, record: PositionEventRecord) -> PositionEventRecord:
        if not record.created_at:
            record.created_at = utc_now_iso()
        return record


class _SequentialCompiledGraph:
    """Fallback used only when langgraph is not installed in the environment."""

    def __init__(self, service: SignalIntakeGraphService) -> None:
        self.service = service

    def invoke(self, state: TradingGraphState, config: dict[str, Any] | None = None) -> TradingGraphState:
        current = dict(state)
        current.update(self.service._node_ingest_signal(current))
        current.update(self.service._node_parse_signal(current))
        current.update(self.service._node_notify_parse_progress(current))
        route_after_parse = self.service._route_after_validate_parse(current)
        if route_after_parse == "notify_telegram":
            current.update(self.service._node_notify_telegram(current))
            return current  # type: ignore[return-value]
        if route_after_parse == END:
            return current
        current.update(self.service._node_classify_asset_lane(current))
        current.update(self.service._node_resolve_target_asset(current))
        route_after_resolve = self.service._route_after_resolve_target_asset(current)
        if route_after_resolve == "notify_telegram":
            current.update(self.service._node_notify_telegram(current))
            return current  # type: ignore[return-value]
        if route_after_resolve == END:
            return current
        current.update(self.service._node_load_strategy_profile(current))
        current.update(self.service._node_enrich_context(current))
        current.update(self.service._node_notify_enrichment_progress(current))
        current.update(self.service._node_compute_ta(current))
        current.update(self.service._node_decision(current))
        current.update(self.service._node_notify_decision_progress(current))
        current.update(self.service._node_apply_policy_gate(current))
        current.update(self.service._node_notify_policy_progress(current))
        route_after_policy = self.service._route_after_policy_gate(current)
        if route_after_policy == "notify_telegram":
            current.update(self.service._node_notify_telegram(current))
            return current  # type: ignore[return-value]
        if route_after_policy == "execute_trade":
            current.update(self.service._node_execute_trade(current))
            current.update(self.service._node_persist_trade_result(current))
            current.update(self.service._node_notify_telegram(current))
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
        enrichment_agent: EnrichmentAgent | None = None,
        decision_agent: DecisionAgent | None = None,
        swap_execution_agent: SwapExecutionAgent | None = None,
        policy_engine: DefaultTradePolicyEngine | None = None,
        execution_repository: TradeExecutionRepository | None = None,
        position_repository: PositionRepository | None = None,
        position_event_repository: PositionEventRepository | None = None,
        wallet_session_repository: WalletSessionRepository | None = None,
        notification_service: NotificationService | None = None,
        execution_runner: TradeExecutionRunner | None = None,
    ) -> None:
        self.parsing_agent = parsing_agent
        self.strategy_profiles = strategy_profiles
        self.asset_lane_classifier = AssetLaneClassifier()
        self.asset_resolver = AssetResolver()
        self.major_asset_registry = MajorAssetRegistry()
        self.ta_tool = TATool()
        self.enrichment_agent = enrichment_agent or EnrichmentAgent()
        self.decision_agent = decision_agent or DecisionAgent()
        self.policy_engine = policy_engine or DefaultTradePolicyEngine()
        self.execution_repository = execution_repository or _NullTradeExecutionRepository()
        self.position_repository = position_repository or _NullPositionRepository()
        self.position_event_repository = position_event_repository or _NullPositionEventRepository()
        self.wallet_session_repository = wallet_session_repository
        self.wallet_address_resolver = WalletAddressResolver(wallet_session_repository)
        self.notification_service = notification_service
        self.execution_runner = execution_runner or OnchainOSSwapBuyExecutionRunner()
        self.swap_execution_agent = swap_execution_agent or SwapExecutionAgent(
            backend=CallableSwapExecutionBackend(self.execution_runner.execute)
        )
        self.durability_mode = get_settings().langgraph.signal_durability
        self.graph = self._build_graph()

    def run(self, request: SignalIntakeRequest, *, thread_id: str | None = None) -> TradingGraphState:
        initial_state = self._initial_state(request)
        config = {"configurable": {"thread_id": thread_id or f"signal:{request.message_id}"}}
        return invoke_graph(self.graph, initial_state, config=config, durability=self.durability_mode)

    def _initial_state(self, request: SignalIntakeRequest) -> TradingGraphState:
        return {
            "action_type": "signal-intake",
            "source_id": request.source_id,
            "signal_id": request.message_id,
            "position_id": None,
            "request_user_id": request.user_id,
            "raw_message_text": request.message_text,
            "media_blobs": list(request.media_blobs or []),
            "messages": [{"role": "user", "content": request.message_text}],
            "parsed_signal": None,
            "resolved_asset": None,
            "parse_explanation": None,
            "wallet_snapshot": None,
            "market_snapshot": None,
            "risk_snapshot": None,
            "enrichment_explanation": None,
            "ta_snapshot": None,
            "ta_explanation": None,
            "strategy_profile": None,
            "trade_decision": None,
            "decision_explanation": None,
            "policy_gate_result": None,
            "policy_explanation": None,
            "execution_request": None,
            "execution_result": None,
            "execution_receipt_explanation": None,
            "telegram_summary": None,
            "signal_overlay": None,
            "execution_trace": [],
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
        builder.add_node("enrich_context", self._node_enrich_context)
        builder.add_node("notify_parse_progress", self._node_notify_parse_progress)
        builder.add_node("notify_enrichment_progress", self._node_notify_enrichment_progress)
        builder.add_node("compute_ta", self._node_compute_ta)
        builder.add_node("decision", self._node_decision)
        builder.add_node("notify_decision_progress", self._node_notify_decision_progress)
        builder.add_node("apply_policy_gate", self._node_apply_policy_gate)
        builder.add_node("notify_policy_progress", self._node_notify_policy_progress)
        builder.add_node("execute_trade", self._node_execute_trade)
        builder.add_node("persist_trade_result", self._node_persist_trade_result)
        builder.add_node("notify_telegram", self._node_notify_telegram)

        builder.add_edge(START, "ingest_signal")
        builder.add_edge("ingest_signal", "parse_signal")
        builder.add_edge("parse_signal", "notify_parse_progress")
        builder.add_conditional_edges(
            "notify_parse_progress",
            self._route_after_validate_parse,
            {"classify_asset_lane": "classify_asset_lane", "notify_telegram": "notify_telegram", END: END},
        )
        builder.add_edge("classify_asset_lane", "resolve_target_asset")
        builder.add_conditional_edges(
            "resolve_target_asset",
            self._route_after_resolve_target_asset,
            {"load_strategy_profile": "load_strategy_profile", "notify_telegram": "notify_telegram", END: END},
        )
        builder.add_edge("load_strategy_profile", "enrich_context")
        builder.add_edge("enrich_context", "notify_enrichment_progress")
        builder.add_edge("notify_enrichment_progress", "compute_ta")
        builder.add_edge("compute_ta", "decision")
        builder.add_edge("decision", "notify_decision_progress")
        builder.add_edge("notify_decision_progress", "apply_policy_gate")
        builder.add_edge("apply_policy_gate", "notify_policy_progress")
        builder.add_conditional_edges(
            "notify_policy_progress",
            self._route_after_policy_gate,
            {"execute_trade": "execute_trade", "notify_telegram": "notify_telegram", END: END},
        )
        builder.add_edge("execute_trade", "persist_trade_result")
        builder.add_edge("persist_trade_result", "notify_telegram")
        builder.add_edge("notify_telegram", END)
        return builder.compile(checkpointer=build_checkpointer())

    def _node_ingest_signal(self, state: TradingGraphState) -> dict[str, Any]:
        return {"messages": state["messages"]}

    def _node_parse_signal(self, state: TradingGraphState) -> dict[str, Any]:
        message_text = str(state.get("raw_message_text") or state["messages"][-1]["content"])
        media_blobs = list(state.get("media_blobs") or [])
        parsed_signal = self.parsing_agent.parse(
            source_id=str(state["source_id"]),
            message_id=str(state["signal_id"]),
            message_text=message_text,
            media_blobs=media_blobs,
        )
        parse_explanation = self._build_parse_explanation(parsed_signal=parsed_signal, media_blobs=media_blobs)
        if parsed_signal["is_actionable"]:
            return {"parsed_signal": parsed_signal, "parse_explanation": parse_explanation}
        return {
            "parsed_signal": parsed_signal,
            "parse_explanation": parse_explanation,
            "trade_decision": {
                "asset_lane": "regular",
                "decision": "skip",
                "decision_reason_code": "NON_ACTIONABLE_SIGNAL",
                "confidence": parsed_signal["confidence"],
                "recommended_amount_usd": 0,
                "capped_amount_usd": 0,
                "rationale_summary": "Message classified as non-actionable.",
                "telegram_summary": "Signal ignored because it is not a tradeable call.",
                "analysis_thesis": "The message does not contain a tradeable call.",
                "ta_reasoning": "TA was not evaluated because the signal was not actionable.",
                "risk_reasoning": "Risk evaluation was not required for a non-actionable message.",
                "sizing_reasoning": "No position sizing was computed.",
                "policy_expectation_summary": "The policy gate would skip this message.",
                "user_message_long": "I am skipping this message because it does not contain a concrete tradeable call with actionable buy intent.",
            },
            "decision_explanation": self._build_decision_explanation(
                {
                    "decision": "skip",
                    "decision_reason_code": "NON_ACTIONABLE_SIGNAL",
                    "confidence": parsed_signal["confidence"],
                    "analysis_thesis": "The message does not contain a tradeable call.",
                    "ta_reasoning": "TA was not evaluated because the signal was not actionable.",
                    "risk_reasoning": "Risk evaluation was not required for a non-actionable message.",
                    "sizing_reasoning": "No position sizing was computed.",
                    "policy_expectation_summary": "The policy gate would skip this message.",
                    "user_message_long": "I am skipping this message because it does not contain a concrete tradeable call with actionable buy intent.",
                    "rationale_summary": "Message classified as non-actionable.",
                }
            ),
        }

    def _route_after_validate_parse(self, state: TradingGraphState) -> str:
        parsed: ParsedSignal = state["parsed_signal"]  # type: ignore[assignment]
        return "classify_asset_lane" if parsed["is_actionable"] else "notify_telegram"

    def _node_notify_parse_progress(self, state: TradingGraphState) -> dict[str, Any]:
        parsed = state["parsed_signal"] or {}
        summary = (
            f"Signal parsed: type={parsed.get('message_type')}, actionable={parsed.get('is_actionable')}, "
            f"symbol={parsed.get('resolved_symbol') or parsed.get('raw_symbol') or 'unknown'}."
        )
        return self._progress_update(
            state,
            stage="parse",
            summary=summary,
            details={
                "asset": parsed.get("resolved_symbol") or parsed.get("raw_symbol") or "unknown",
                "message_type": parsed.get("message_type"),
                "actionable": parsed.get("is_actionable"),
                "confidence": parsed.get("confidence"),
                "chain": parsed.get("resolved_chain") or parsed.get("raw_chain_hint") or "unknown",
            },
            explanation=state.get("parse_explanation"),
        )

    @staticmethod
    def _build_parse_explanation(
        *,
        parsed_signal: ParsedSignal,
        media_blobs: list[dict[str, Any]],
    ) -> ParseExplanation:
        main_asset = (
            parsed_signal.get("resolved_symbol")
            or parsed_signal.get("raw_symbol")
            or parsed_signal.get("resolved_contract_address")
            or parsed_signal.get("raw_contract_address")
            or "unknown"
        )
        chain_hint = parsed_signal.get("resolved_chain") or parsed_signal.get("raw_chain_hint") or "unknown"
        has_contract = bool(parsed_signal.get("resolved_contract_address") or parsed_signal.get("raw_contract_address"))
        image_count = sum(1 for blob in media_blobs if blob.get("kind") == "image")
        evidence_points = [
            f"Message type classified as {parsed_signal.get('message_type')}.",
            f"Actionable={parsed_signal.get('is_actionable')}.",
            f"Main asset clue: {main_asset}.",
            f"Chain hint: {chain_hint}.",
            "Contract address was provided or resolved." if has_contract else "No contract address was available at parse stage.",
            (
                f"{image_count} supporting image attachment(s) were provided."
                if image_count > 0
                else "No image attachments were provided."
            ),
        ]
        long_form_message = (
            f"I classified this message as a {parsed_signal.get('message_type')} with confidence "
            f"{parsed_signal.get('confidence')}. Main asset clue: {main_asset}. Chain hint: {chain_hint}."
        )
        if image_count > 0:
            long_form_message += " Attached image(s) were provided as supporting context."
        return {
            "title": "Signal parsed",
            "summary": parsed_signal.get("reasoning_summary") or "Telegram message parsed into structured signal fields.",
            "evidence_points": evidence_points,
            "key_metrics": {
                "confidence": parsed_signal.get("confidence"),
                "message_type": parsed_signal.get("message_type"),
                "is_actionable": parsed_signal.get("is_actionable"),
            },
            "long_form_message": long_form_message,
        }

    def _node_classify_asset_lane(self, state: TradingGraphState) -> dict[str, Any]:
        parsed: ParsedSignal = state["parsed_signal"]  # type: ignore[assignment]
        asset_lane, target_chain = self.asset_lane_classifier.classify(parsed)
        normalized_symbol = (parsed.get("resolved_symbol") or parsed.get("raw_symbol") or "UNKNOWN").upper()
        token_contract_address = parsed.get("resolved_contract_address") or parsed.get("raw_contract_address")
        resolved_signal_chain = parsed.get("resolved_chain") or parsed.get("raw_chain_hint")
        approved_major_mapping = None
        token_name = parsed.get("resolved_token_name")
        decimals = parsed.get("resolved_decimals")
        if asset_lane == "major":
            mapping = self.major_asset_registry.get(normalized_symbol)
            if mapping is not None:
                target_chain = mapping.target_chain
                approved_major_mapping = mapping.execution_token
                token_name = mapping.token_name
                decimals = mapping.decimals
        resolved = ResolvedAsset(
            asset_lane=asset_lane,
            normalized_symbol=normalized_symbol,
            target_execution_chain=target_chain or "unknown",
            resolved_signal_chain=resolved_signal_chain,
            token_contract_address=token_contract_address,
            token_name=token_name,
            decimals=decimals,
            is_native=asset_lane == "major",
            approved_major_mapping=approved_major_mapping,
            resolution_confidence=parsed["confidence"],
        )
        return {"resolved_asset": resolved}

    def _node_resolve_target_asset(self, state: TradingGraphState) -> dict[str, Any]:
        resolved: ResolvedAsset = state["resolved_asset"]  # type: ignore[assignment]
        if resolved["asset_lane"] == "major":
            if resolved["approved_major_mapping"]:
                return {}
            return {
                "trade_decision": self._build_resolution_block_decision(
                    reason_code="MAJOR_MAPPING_NOT_FOUND",
                    rationale="Major-asset mapping is unavailable.",
                    telegram="Trade blocked because the approved X Layer major-asset mapping is missing.",
                    thesis="The major asset does not have a product-approved execution mapping on X Layer.",
                    long_message="I am blocking this trade because the major asset could not be mapped to the approved X Layer trading representation.",
                    asset_lane="major",
                ),
                "decision_explanation": self._build_decision_explanation(
                    self._build_resolution_block_decision(
                        reason_code="MAJOR_MAPPING_NOT_FOUND",
                        rationale="Major-asset mapping is unavailable.",
                        telegram="Trade blocked because the approved X Layer major-asset mapping is missing.",
                        thesis="The major asset does not have a product-approved execution mapping on X Layer.",
                        long_message="I am blocking this trade because the major asset could not be mapped to the approved X Layer trading representation.",
                        asset_lane="major",
                    )
                ),
            }

        regular = self.asset_resolver.resolve_regular(state["parsed_signal"] or {})
        if regular.status == "resolved":
            return {
                "resolved_asset": {
                    **resolved,
                    "normalized_symbol": regular.normalized_symbol,
                    "resolved_signal_chain": regular.resolved_chain,
                    "target_execution_chain": regular.resolved_chain or resolved["target_execution_chain"],
                    "token_contract_address": regular.token_contract_address,
                    "token_name": regular.token_name,
                    "decimals": regular.decimals,
                    "resolution_confidence": regular.confidence,
                }
            }

        if regular.reason_code == "TOKEN_AMBIGUOUS":
            return {
                "trade_decision": self._build_resolution_block_decision(
                    reason_code="TOKEN_AMBIGUOUS",
                    rationale="Regular-token signal remains ambiguous after deterministic resolution.",
                    telegram="Trade blocked because token resolution remains ambiguous.",
                    thesis="The signal still has more than one plausible token interpretation.",
                    long_message="I am blocking this trade because the signal did not provide enough exact token identity information for a deterministic resolution step.",
                    asset_lane="regular",
                ),
                "decision_explanation": self._build_decision_explanation(
                    self._build_resolution_block_decision(
                        reason_code="TOKEN_AMBIGUOUS",
                        rationale="Regular-token signal remains ambiguous after deterministic resolution.",
                        telegram="Trade blocked because token resolution remains ambiguous.",
                        thesis="The signal still has more than one plausible token interpretation.",
                        long_message="I am blocking this trade because the signal did not provide enough exact token identity information for a deterministic resolution step.",
                        asset_lane="regular",
                    )
                ),
            }

        return {
            "trade_decision": self._build_resolution_block_decision(
                reason_code="TOKEN_UNRESOLVED",
                rationale="Regular-token signal could not be resolved.",
                telegram="Trade blocked because token identity could not be resolved.",
                thesis="The token target could not be resolved with enough confidence.",
                long_message="I am blocking this trade because I cannot confidently determine which token should be traded from the message.",
                asset_lane="regular",
            ),
            "decision_explanation": self._build_decision_explanation(
                self._build_resolution_block_decision(
                    reason_code="TOKEN_UNRESOLVED",
                    rationale="Regular-token signal could not be resolved.",
                    telegram="Trade blocked because token identity could not be resolved.",
                    thesis="The token target could not be resolved with enough confidence.",
                    long_message="I am blocking this trade because I cannot confidently determine which token should be traded from the message.",
                    asset_lane="regular",
                )
            ),
        }

    def _route_after_resolve_target_asset(self, state: TradingGraphState) -> str:
        decision = state.get("trade_decision")
        if decision and decision.get("decision") == "block":
            return "notify_telegram"
        return "load_strategy_profile"

    def _node_load_strategy_profile(self, state: TradingGraphState) -> dict[str, Any]:
        user_id = state.get("request_user_id") or "unknown"
        profile: UserStrategyProfile = self.strategy_profiles.get_or_create(str(user_id))
        return {"strategy_profile": profile.model_dump()}

    def _node_enrich_context(self, state: TradingGraphState) -> dict[str, Any]:
        resolved_asset = state["resolved_asset"] or {}
        wallet_resolution = self.wallet_address_resolver.resolve_wallet_address_for_chain(
            user_id=str(state.get("request_user_id") or "unknown"),
            chain=str(resolved_asset.get("target_execution_chain") or "unknown"),
        )
        wallet_hints = {
            **self.wallet_address_resolver.get_wallet_hints(user_id=str(state.get("request_user_id") or "unknown")),
            **wallet_resolution.to_prompt_hints(),
        }
        enrichment = self.enrichment_agent.enrich(
            parsed_signal=state["parsed_signal"],
            resolved_asset=state["resolved_asset"],
            strategy_profile=state["strategy_profile"],
            wallet_context_hints=wallet_hints,
        )
        wallet_snapshot = dict(enrichment.get("wallet_snapshot") or {})
        if wallet_resolution.wallet_address:
            wallet_snapshot["wallet_address"] = wallet_resolution.wallet_address
        if wallet_snapshot.get("target_chain") is None:
            wallet_snapshot["target_chain"] = wallet_resolution.chain

        market_snapshot = enrichment["market_snapshot"]
        if not isinstance(market_snapshot.get("kline_window"), list) or len(market_snapshot.get("kline_window", [])) == 0:
            return {
                "wallet_snapshot": wallet_snapshot,
                "market_snapshot": market_snapshot,
                "risk_snapshot": enrichment["risk_snapshot"],
                "enrichment_explanation": self._build_enrichment_explanation(
                    enrichment=enrichment,
                    wallet_snapshot=wallet_snapshot,
                    market_snapshot=market_snapshot,
                ),
                "signal_overlay": enrichment.get("signal_overlay"),
                "trade_decision": {
                    "asset_lane": state["resolved_asset"]["asset_lane"],
                    "decision": "block",
                    "decision_reason_code": "MARKET_KLINE_MISSING",
                    "confidence": 0.0,
                    "recommended_amount_usd": 0,
                    "capped_amount_usd": 0,
                    "rationale_summary": "Trade blocked because enrichment did not provide market kline data for TA.",
                    "telegram_summary": "Trade blocked because market kline data was unavailable.",
                    "analysis_thesis": "Required market context is incomplete because kline data is missing.",
                    "ta_reasoning": "TA cannot be computed without the kline window.",
                    "risk_reasoning": "Risk context may exist, but the setup is still incomplete for a safe trade decision.",
                    "sizing_reasoning": "No size should be proposed when core market context is missing.",
                    "policy_expectation_summary": "The policy gate should block trades with missing required market inputs.",
                    "user_message_long": "I am blocking this trade because the enrichment step did not provide kline data, so I cannot evaluate momentum or price behavior safely.",
                },
                "decision_explanation": self._build_decision_explanation(
                    {
                        "decision": "block",
                        "decision_reason_code": "MARKET_KLINE_MISSING",
                        "confidence": 0.0,
                        "analysis_thesis": "Required market context is incomplete because kline data is missing.",
                        "ta_reasoning": "TA cannot be computed without the kline window.",
                        "risk_reasoning": "Risk context may exist, but the setup is still incomplete for a safe trade decision.",
                        "sizing_reasoning": "No size should be proposed when core market context is missing.",
                        "policy_expectation_summary": "The policy gate should block trades with missing required market inputs.",
                        "user_message_long": "I am blocking this trade because the enrichment step did not provide kline data, so I cannot evaluate momentum or price behavior safely.",
                        "rationale_summary": "Trade blocked because enrichment did not provide market kline data for TA.",
                    }
                ),
            }
        return {
            "wallet_snapshot": wallet_snapshot,
            "market_snapshot": market_snapshot,
            "risk_snapshot": enrichment["risk_snapshot"],
            "enrichment_explanation": self._build_enrichment_explanation(
                enrichment=enrichment,
                wallet_snapshot=wallet_snapshot,
                market_snapshot=market_snapshot,
            ),
            "signal_overlay": enrichment.get("signal_overlay"),
        }

    def _node_notify_enrichment_progress(self, state: TradingGraphState) -> dict[str, Any]:
        resolved = state["resolved_asset"] or {}
        market = state["market_snapshot"] or {}
        risk = state["risk_snapshot"] or {}
        explanation = state.get("enrichment_explanation") or {}
        summary = (
            f"Context ready: lane={resolved.get('asset_lane')}, chain={resolved.get('target_execution_chain')}, "
            f"price={market.get('spot_price_usd')}, risk_scan_required={risk.get('risk_scan_required')}."
        )
        return self._progress_update(
            state,
            stage="enrichment",
            summary=summary,
            details={
                "lane": resolved.get("asset_lane"),
                "chain": resolved.get("target_execution_chain"),
                "price": market.get("spot_price_usd"),
                "wallet_ready": (state.get("wallet_snapshot") or {}).get("logged_in"),
                "risk_scan": risk.get("risk_scan_required"),
                "kline_points": len(market.get("kline_window") or []),
                "summary": explanation.get("summary"),
            },
            explanation=state.get("enrichment_explanation"),
        )

    def _node_compute_ta(self, state: TradingGraphState) -> dict[str, Any]:
        existing_decision = state.get("trade_decision")
        if existing_decision and existing_decision.get("decision") == "block":
            return {
                "ta_snapshot": {
                    "asset_lane": state["resolved_asset"]["asset_lane"],
                    "call_reference_price_usd": None,
                    "current_price_usd": None,
                    "price_deviation_pct": None,
                    "momentum_score": None,
                    "volatility_score": None,
                    "liquidity_gate_passed": None,
                    "ta_score": 0.0,
                    "ta_summary": "TA skipped because enrichment failed to provide required market kline data.",
                }
            }
        resolved: ResolvedAsset = state["resolved_asset"]  # type: ignore[assignment]
        market = state["market_snapshot"] or {}
        strategy = state["strategy_profile"] or {}
        result = self.ta_tool.compute(
            TAInput(
                asset_lane=resolved["asset_lane"],
                current_price_usd=market["spot_price_usd"],
                call_reference_price_usd=self.asset_resolver.parse_reference_price(state["parsed_signal"] or {}),
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

    def _node_decision(self, state: TradingGraphState) -> dict[str, Any]:
        decision = state.get("trade_decision")
        if decision and decision["decision"] == "block":
            return {
                "trade_decision": decision,
                "decision_explanation": state.get("decision_explanation")
                or self._build_decision_explanation(decision),
            }
        decision = self.decision_agent.decide(
            parsed_signal=state["parsed_signal"],
            resolved_asset=state["resolved_asset"],
            wallet_snapshot=state["wallet_snapshot"],
            market_snapshot=state["market_snapshot"],
            risk_snapshot=state["risk_snapshot"],
            ta_snapshot=state["ta_snapshot"],
            strategy_profile=state["strategy_profile"],
            signal_overlay=state["signal_overlay"],
        )
        return {
            "trade_decision": decision,
            "decision_explanation": self._build_decision_explanation(decision),
        }

    def _node_notify_decision_progress(self, state: TradingGraphState) -> dict[str, Any]:
        decision = state["trade_decision"] or {}
        explanation = state.get("decision_explanation") or {}
        summary = (
            f"Decision formed: action={decision.get('decision')}, "
            f"reason={decision.get('decision_reason_code')}, capped_amount={decision.get('capped_amount_usd')}."
        )
        return self._progress_update(
            state,
            stage="decision",
            summary=summary,
            details={
                "action": decision.get("decision"),
                "reason": decision.get("decision_reason_code"),
                "amount_usd": decision.get("capped_amount_usd"),
                "confidence": decision.get("confidence"),
                "analysis": explanation.get("summary"),
            },
            explanation=state.get("decision_explanation"),
        )

    @staticmethod
    def _build_decision_explanation(decision: dict[str, Any]) -> DecisionExplanation:
        evidence_points = [
            point
            for point in [
                decision.get("analysis_thesis"),
                decision.get("ta_reasoning"),
                decision.get("risk_reasoning"),
                decision.get("sizing_reasoning"),
                decision.get("policy_expectation_summary"),
            ]
            if point
        ]
        long_form_message = decision.get("user_message_long") or decision.get("telegram_summary")
        return {
            "title": f"Trade decision: {decision.get('decision', 'unknown')}",
            "summary": decision.get("rationale_summary") or "Trade decision generated.",
            "evidence_points": evidence_points,
            "key_metrics": {
                "decision": decision.get("decision"),
                "reason_code": decision.get("decision_reason_code"),
                "confidence": decision.get("confidence"),
                "recommended_amount_usd": decision.get("recommended_amount_usd"),
                "capped_amount_usd": decision.get("capped_amount_usd"),
            },
            "long_form_message": long_form_message,
        }

    @staticmethod
    def _build_enrichment_explanation(
        *,
        enrichment: dict[str, Any],
        wallet_snapshot: dict[str, Any],
        market_snapshot: dict[str, Any],
    ) -> EnrichmentExplanation:
        risk_snapshot = enrichment.get("risk_snapshot") or {}
        signal_overlay = enrichment.get("signal_overlay") or {}
        evidence_points = list(enrichment.get("evidence_points") or [])
        for point in [
            enrichment.get("wallet_summary"),
            enrichment.get("market_summary"),
            enrichment.get("risk_summary_long"),
            enrichment.get("overlay_summary_long"),
        ]:
            if point and point not in evidence_points:
                evidence_points.append(point)
        if not evidence_points:
            evidence_points = [
                f"Wallet logged_in={wallet_snapshot.get('logged_in')}, chain={wallet_snapshot.get('target_chain')}.",
                f"Spot price={market_snapshot.get('spot_price_usd')}, liquidity={market_snapshot.get('liquidity_usd')}, quote_available={market_snapshot.get('quote_available')}.",
                f"Risk scan required={risk_snapshot.get('risk_scan_required')}, supported={risk_snapshot.get('risk_scan_supported')}, risk_token={risk_snapshot.get('is_risk_token')}.",
            ]
            if signal_overlay:
                evidence_points.append(
                    f"Overlay smart_money={signal_overlay.get('smart_money_count')}, kol={signal_overlay.get('kol_count')}, whale={signal_overlay.get('whale_count')}."
                )
        summary_parts = [
            enrichment.get("wallet_summary"),
            enrichment.get("market_summary"),
            enrichment.get("risk_summary_long"),
        ]
        if signal_overlay:
            summary_parts.append(enrichment.get("overlay_summary_long") or signal_overlay.get("overlay_summary"))
        summary = " ".join(part for part in summary_parts if part) or "Enrichment context collected."
        long_form_message = "\n".join(
            part
            for part in [
                enrichment.get("wallet_summary"),
                enrichment.get("market_summary"),
                enrichment.get("risk_summary_long"),
                enrichment.get("overlay_summary_long"),
            ]
            if part
        ) or summary
        return {
            "title": "Context collection complete",
            "summary": summary,
            "evidence_points": evidence_points,
            "key_metrics": {
                "wallet_logged_in": wallet_snapshot.get("logged_in"),
                "wallet_balance_usd": wallet_snapshot.get("available_balance_usd"),
                "spot_price_usd": market_snapshot.get("spot_price_usd"),
                "liquidity_usd": market_snapshot.get("liquidity_usd"),
                "quote_price_impact_pct": market_snapshot.get("quote_price_impact_pct"),
                "risk_scan_required": risk_snapshot.get("risk_scan_required"),
                "is_risk_token": risk_snapshot.get("is_risk_token"),
                "kline_points": len(market_snapshot.get("kline_window") or []),
            },
            "long_form_message": long_form_message,
        }

    @staticmethod
    def _build_execution_receipt_explanation(
        *,
        execution_result: dict[str, Any],
        trade_side: str,
        asset_symbol: str,
    ) -> dict[str, Any]:
        success = bool(execution_result.get("success"))
        amount = execution_result.get("received_token_amount") or execution_result.get("realized_output_amount")
        output_symbol = execution_result.get("received_token_symbol") or execution_result.get("realized_output_symbol")
        route_summary = execution_result.get("route_summary")
        evidence_points = [
            point
            for point in [
                f"Execution id: {execution_result.get('execution_id')}" if execution_result.get("execution_id") else None,
                f"Swap tx: {execution_result.get('swap_tx_hash')}" if execution_result.get("swap_tx_hash") else None,
                f"Approval tx: {execution_result.get('approve_tx_hash')}" if execution_result.get("approve_tx_hash") else None,
                route_summary,
            ]
            if point
        ]
        if success:
            long_form_message = execution_result.get("receipt_message_long") or (
                f"{trade_side.title()} execution for {asset_symbol} succeeded."
                + (
                    f" Output: {amount} {output_symbol}."
                    if amount is not None and output_symbol is not None
                    else ""
                )
                + (f" Route: {route_summary}." if route_summary else "")
                + (
                    f" Explorer: {execution_result.get('explorer_url')}."
                    if execution_result.get("explorer_url")
                    else ""
                )
            )
            summary = f"{trade_side.title()} execution succeeded."
        else:
            long_form_message = execution_result.get("receipt_message_long") or (
                f"{trade_side.title()} execution for {asset_symbol} failed with "
                f"{execution_result.get('error_code', 'unknown')}."
            )
            summary = f"{trade_side.title()} execution failed."
        return {
            "title": f"{trade_side.title()} execution receipt",
            "summary": summary,
            "evidence_points": evidence_points,
            "key_metrics": {
                "success": success,
                "execution_id": execution_result.get("execution_id"),
                "amount": amount,
                "output_symbol": output_symbol,
                "effective_price_impact_pct": execution_result.get("effective_price_impact_pct"),
                "execution_price": execution_result.get("execution_price"),
            },
            "long_form_message": long_form_message,
        }

    def _node_apply_policy_gate(self, state: TradingGraphState) -> dict[str, Any]:
        active_position_count = 0
        if self.position_repository is not None:
            active_position_count = sum(
                1
                for record in self.position_repository.list_by_user(str(state.get("request_user_id") or "unknown"))
                if getattr(record, "status", None) == "open"
            )
        evaluation = self.policy_engine.evaluate(
            {
                "trade_decision": state["trade_decision"],
                "resolved_asset": state["resolved_asset"],
                "wallet_snapshot": state["wallet_snapshot"],
                "market_snapshot": state["market_snapshot"],
                "risk_snapshot": state["risk_snapshot"],
                "ta_snapshot": state["ta_snapshot"],
                "strategy_profile": state["strategy_profile"],
                "active_position_count": active_position_count,
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

    def _node_notify_policy_progress(self, state: TradingGraphState) -> dict[str, Any]:
        gate = state["policy_gate_result"] or {}
        summary = (
            f"Policy gate: passed={gate.get('passed')}, action={gate.get('action')}, "
            f"failures={gate.get('failure_codes') or []}."
        )
        return self._progress_update(
            state,
            stage="policy_gate",
            summary=summary,
            details={
                "passed": gate.get("passed"),
                "action": gate.get("action"),
                "failures": gate.get("failure_codes") or [],
            },
            explanation=state.get("policy_explanation"),
        )

    def _route_after_policy_gate(self, state: TradingGraphState) -> str:
        gate = state.get("policy_gate_result") or {}
        return "execute_trade" if gate.get("action") == "execute" and gate.get("passed") else "notify_telegram"

    def _node_execute_trade(self, state: TradingGraphState) -> dict[str, Any]:
        resolved: ResolvedAsset = state["resolved_asset"]  # type: ignore[assignment]
        decision = state["trade_decision"] or {}
        strategy = state["strategy_profile"] or {}
        wallet = state["wallet_snapshot"] or {}
        wallet_resolution = self.wallet_address_resolver.resolve_wallet_address_for_chain(
            user_id=str(state.get("request_user_id") or "unknown"),
            chain=str(resolved["target_execution_chain"]),
        )
        resolved_wallet_address = (
            wallet_resolution.wallet_address
            or wallet.get("target_chain_wallet_address")
            or wallet.get("wallet_address")
        )
        amount = decision.get("capped_amount_usd") or decision.get("recommended_amount_usd") or 0
        slippage_pct = (
            strategy.get("max_slippage_pct_major")
            if resolved["asset_lane"] == "major"
            else strategy.get("max_slippage_pct_regular")
        )
        to_token = resolved["approved_major_mapping"] or resolved["token_contract_address"] or resolved["normalized_symbol"]
        intent = {
            "user_id": state.get("request_user_id"),
            "signal_id": state.get("signal_id"),
            "asset_lane": resolved["asset_lane"],
            "side": "buy",
            "chain": resolved["target_execution_chain"],
            "wallet_address": resolved_wallet_address,
            "from_token": "USDC",
            "to_token": to_token,
            "readable_amount": str(amount),
            "slippage_pct": slippage_pct,
        }
        swap_output = _resolve_task_result(_execute_trade_task(self.swap_execution_agent, intent=intent))
        return {
            "execution_request": swap_output["execution_request"],
            "execution_result": swap_output["execution_result"],
            "execution_receipt_explanation": self._build_execution_receipt_explanation(
                execution_result=swap_output["execution_result"],
                trade_side="buy",
                asset_symbol=str(resolved["normalized_symbol"]),
            ),
            "position_id": f"pos:{state.get('signal_id')}",
        }

    def _node_persist_trade_result(self, state: TradingGraphState) -> dict[str, Any]:
        resolved: ResolvedAsset = state["resolved_asset"]  # type: ignore[assignment]
        execution_request = state["execution_request"] or {}
        execution_result = state["execution_result"] or {}
        signal_id = str(state.get("signal_id") or "unknown")
        position_id = str(state.get("position_id") or f"pos:{signal_id}")
        user_id = str(state.get("request_user_id") or "unknown")
        source_id = str(state.get("source_id") or "unknown")
        market = state["market_snapshot"] or {}

        execution_id = execution_result.get("execution_id") or f"buy:{signal_id}"
        self.execution_repository.save(
            TradeExecutionRecord(
                execution_id=execution_id,
                signal_id=signal_id,
                position_id=position_id,
                asset_lane=resolved["asset_lane"],
                side="buy",
                chain=str(execution_request.get("chain", resolved["target_execution_chain"])),
                wallet_address=str(execution_request.get("wallet_address", "")),
                from_token=str(execution_request.get("from_token", "")),
                to_token=str(execution_request.get("to_token", "")),
                requested_amount=str(execution_request.get("readable_amount", "")),
                approve_tx_hash=execution_result.get("approve_tx_hash"),
                swap_tx_hash=execution_result.get("swap_tx_hash"),
                success=bool(execution_result.get("success")),
                error_code=execution_result.get("error_code"),
                error_message=execution_result.get("error_message"),
                idempotency_key=f"{signal_id}:buy",
                execution=execution_result,
            )
        )

        self.position_event_repository.save(
            PositionEventRecord(
                position_id=position_id,
                event_type="entry_execution_succeeded" if execution_result.get("success") else "entry_execution_failed",
                event_reason_code=(state.get("trade_decision") or {}).get("decision_reason_code"),
                event={
                    "trade_decision": state.get("trade_decision"),
                    "execution_result": execution_result,
                    "signal_id": signal_id,
                },
            )
        )

        if execution_result.get("success"):
            self.position_repository.save(
                PositionRecord(
                    position_id=position_id,
                    user_id=user_id,
                    source_id=source_id,
                    asset_lane=resolved["asset_lane"],
                    chain=str(execution_request.get("chain", resolved["target_execution_chain"])),
                    symbol=str(resolved["normalized_symbol"]),
                    token_contract_address=resolved["token_contract_address"],
                    wallet_address=str(execution_request.get("wallet_address", "")),
                    entry_price_usd=market.get("spot_price_usd"),
                    entry_amount_usd=float(execution_request.get("readable_amount", 0) or 0),
                    entry_token_amount=(
                        float(execution_result["received_token_amount"])
                        if execution_result.get("received_token_amount") is not None
                        else None
                    ),
                    current_price_usd=market.get("spot_price_usd"),
                    peak_price_since_open_usd=market.get("spot_price_usd"),
                    trailing_state={"armed": False},
                    status="open",
                    opened_at=utc_now_iso(),
                )
            )
        return {"position_id": position_id}

    def _node_notify_telegram(self, state: TradingGraphState) -> dict[str, Any]:
        execution_result = state["execution_result"] or {}
        decision = state["trade_decision"] or {}
        receipt = state.get("execution_receipt_explanation") or {}
        summary = decision.get("telegram_summary") or "Trade evaluated."
        explanation_payload = state.get("execution_receipt_explanation") or state.get("decision_explanation")
        if execution_result:
            if execution_result.get("success"):
                summary = f"{summary} Buy execution submitted successfully."
            else:
                summary = f"{summary} Buy execution failed: {execution_result.get('error_code', 'unknown')}."
            if receipt.get("long_form_message"):
                summary = f"{summary}\n\n{receipt['long_form_message']}"
        elif decision.get("user_message_long"):
            summary = f"{summary}\n\n{decision['user_message_long']}"
        if self.notification_service is not None:
            chat_id = self._resolve_notification_chat_id(str(state.get("request_user_id") or "unknown"))
            self.notification_service.send_trade_notification(
                user_id=str(state.get("request_user_id") or "unknown"),
                chat_id=chat_id,
                signal_id=str(state.get("signal_id") or "unknown"),
                position_id=str(state.get("position_id") or f"pos:{state.get('signal_id')}"),
                message_text=summary,
                explanation_payload=explanation_payload,
            )
        return {"telegram_summary": summary}

    @staticmethod
    def _build_resolution_block_decision(
        *,
        reason_code: str,
        rationale: str,
        telegram: str,
        thesis: str,
        long_message: str,
        asset_lane: str,
    ) -> dict[str, Any]:
        return {
            "asset_lane": asset_lane,
            "decision": "block",
            "decision_reason_code": reason_code,
            "confidence": 0.0,
            "recommended_amount_usd": 0,
            "capped_amount_usd": 0,
            "rationale_summary": rationale,
            "telegram_summary": telegram,
            "analysis_thesis": thesis,
            "ta_reasoning": "TA was not evaluated because the trade target was unresolved.",
            "risk_reasoning": "Risk checks cannot run safely without a fully resolved token identity.",
            "sizing_reasoning": "No amount can be proposed while the asset target is unresolved.",
            "policy_expectation_summary": "The policy gate should block trades with unresolved or ambiguous target assets.",
            "user_message_long": long_message,
        }

    def _progress_update(
        self,
        state: TradingGraphState,
        *,
        stage: str,
        summary: str,
        details: dict | None = None,
        explanation: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        trace = list(state.get("execution_trace") or [])
        trace.append({"stage": stage, "summary": summary})
        if self.notification_service is not None:
            chat_id = self._resolve_notification_chat_id(str(state.get("request_user_id") or "unknown"))
            self.notification_service.send_progress_notification(
                user_id=str(state.get("request_user_id") or "unknown"),
                chat_id=chat_id,
                related_signal_id=str(state.get("signal_id") or "unknown"),
                related_position_id=state.get("position_id"),
                stage=stage,
                message_text=summary,
                details=details,
                explanation=explanation,
            )
        return {"execution_trace": trace}

    def _resolve_notification_chat_id(self, user_id: str) -> str:
        if self.wallet_session_repository is not None:
            session = self.wallet_session_repository.get(user_id)
            if session is not None and session.chat_id:
                return session.chat_id
        return user_id
