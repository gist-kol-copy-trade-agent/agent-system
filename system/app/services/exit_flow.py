from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from app.agents.exit import ExitAgent
from app.agents.position_tracker import PositionTrackerAgent
from app.agents.swap_execution import CallableSwapExecutionBackend, SwapExecutionAgent
from app.config.settings import get_settings
from app.graphs.runtime import build_checkpointer, invoke_graph
from app.graphs.state import ExitGraphState
from app.persistence.repositories import (
    PositionExitEvaluationRecord,
    PositionExitEvaluationRepository,
    PositionEventRecord,
    PositionEventRepository,
    PositionRecord,
    PositionRepository,
    TradeExecutionRecord,
    TradeExecutionRepository,
    utc_now_iso,
)
from app.policies.exit_policy import DefaultExitPolicyEngine
from app.schemas.domain import ExitMarketSnapshot, ExitTASnapshot, PositionSnapshot, PositionTrackingSnapshot, TrailingState
from app.schemas.strategy import UserStrategyProfile
from app.services.onchainos_runner import OnchainOSCommandError, OnchainOSMutatingRunner
from app.services.notifications import NotificationService
from app.services.strategy_profiles import StrategyProfileService

try:
    from langgraph.graph import END, START, StateGraph
except ModuleNotFoundError:  # pragma: no cover
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
def _execute_exit_task(swap_execution_agent: SwapExecutionAgent, *, intent: dict[str, Any]) -> dict[str, Any]:
    return swap_execution_agent.execute(intent=intent)


class ExitExecutionRunner(Protocol):
    def execute(self, request: dict[str, Any]) -> dict[str, Any]: ...


class OnchainOSSwapExitExecutionRunner:
    def __init__(self, runner: OnchainOSMutatingRunner | None = None) -> None:
        self.runner = runner or OnchainOSMutatingRunner()

    def execute(self, request: dict[str, Any]) -> dict[str, Any]:
        command = self._build_command(request)
        try:
            result = self.runner.run(command)
        except OnchainOSCommandError as exc:
            return {
                "position_id": request["position_id"],
                "success": False,
                "execution_id": None,
                "approve_tx_hash": None,
                "swap_tx_hash": None,
                "realized_output_amount": None,
                "realized_output_symbol": request["to_token"],
                "error_code": "ONCHAINOS_EXECUTION_ERROR",
                "error_message": str(exc),
            }

        payload = result.get("payload") if isinstance(result, dict) else None
        data = payload.get("data", payload) if isinstance(payload, dict) else {}
        if isinstance(data, list):
            data = data[0] if data else {}
        return {
            "position_id": request["position_id"],
            "success": bool(result.get("ok")),
            "execution_id": data.get("requestId") or data.get("executionId") or data.get("swapTxHash"),
            "approve_tx_hash": data.get("approveTxHash"),
            "swap_tx_hash": data.get("swapTxHash") or data.get("txHash"),
            "realized_output_amount": data.get("toAmount") or data.get("outputAmount"),
            "realized_output_symbol": data.get("toTokenSymbol") or request["to_token"],
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


class NullExitExecutionRunner:
    def execute(self, request: dict[str, Any]) -> dict[str, Any]:
        return {
            "position_id": request["position_id"],
            "success": False,
            "execution_id": None,
            "approve_tx_hash": None,
            "swap_tx_hash": None,
            "realized_output_amount": None,
            "realized_output_symbol": request["to_token"],
            "error_code": "EXECUTION_NOT_IMPLEMENTED",
            "error_message": "Exit execution runner is not implemented yet.",
        }


@dataclass
class ExitFlowRequest:
    user_id: str
    position_id: str
    cycle_id: str
    position_record: PositionRecord


class _NullPositionExitEvaluationRepository:
    def save(self, record: PositionExitEvaluationRecord) -> PositionExitEvaluationRecord:
        if not record.created_at:
            record.created_at = utc_now_iso()
        return record


class _SequentialCompiledExitGraph:
    def __init__(self, service: ExitGraphService) -> None:
        self.service = service

    def invoke(self, state: ExitGraphState, config: dict[str, Any] | None = None) -> ExitGraphState:
        current = dict(state)
        current.update(self.service._node_load_position(current))
        current.update(self.service._node_load_strategy_profile(current))
        current.update(self.service._node_load_market_context(current))
        current.update(self.service._node_compute_exit_ta(current))
        current.update(self.service._node_notify_ta_progress(current))
        current.update(self.service._node_build_exit_inputs(current))
        current.update(self.service._node_exit_decision(current))
        current.update(self.service._node_notify_decision_progress(current))
        current.update(self.service._node_apply_exit_policy_gate(current))
        current.update(self.service._node_notify_policy_progress(current))

        route = self.service._route_after_policy_gate(current)
        if route == "persist_evaluation":
            current.update(self.service._node_persist_evaluation(current))
            return current  # type: ignore[return-value]

        current.update(self.service._node_execute_exit(current))
        current.update(self.service._node_persist_exit_result(current))
        current.update(self.service._node_notify_telegram(current))
        return current  # type: ignore[return-value]


class ExitGraphService:
    def __init__(
        self,
        *,
        strategy_profiles: StrategyProfileService,
        exit_agent: ExitAgent | None = None,
        position_tracker_agent: PositionTrackerAgent | None = None,
        swap_execution_agent: SwapExecutionAgent | None = None,
        policy_engine: DefaultExitPolicyEngine | None = None,
        position_repository: PositionRepository | None = None,
        evaluation_repository: PositionExitEvaluationRepository | None = None,
        execution_repository: TradeExecutionRepository | None = None,
        position_event_repository: PositionEventRepository | None = None,
        notification_service: NotificationService | None = None,
        execution_runner: ExitExecutionRunner | None = None,
    ) -> None:
        self.strategy_profiles = strategy_profiles
        self.exit_agent = exit_agent or ExitAgent()
        self.position_tracker_agent = position_tracker_agent or PositionTrackerAgent()
        self.policy_engine = policy_engine or DefaultExitPolicyEngine()
        self.position_repository = position_repository
        self.evaluation_repository = evaluation_repository or _NullPositionExitEvaluationRepository()
        self.execution_repository = execution_repository
        self.position_event_repository = position_event_repository
        self.notification_service = notification_service
        self.execution_runner = execution_runner or OnchainOSSwapExitExecutionRunner()
        self.swap_execution_agent = swap_execution_agent or SwapExecutionAgent(
            backend=CallableSwapExecutionBackend(self.execution_runner.execute)
        )
        self.durability_mode = get_settings().langgraph.exit_durability
        self.graph = self._build_graph()

    def run(self, request: ExitFlowRequest, *, thread_id: str | None = None) -> ExitGraphState:
        initial_state = self._initial_state(request)
        config = {"configurable": {"thread_id": thread_id or f"position:{request.position_id}:exit:{request.cycle_id}"}}
        return invoke_graph(self.graph, initial_state, config=config, durability=self.durability_mode)

    def _initial_state(self, request: ExitFlowRequest) -> ExitGraphState:
        return {
            "messages": [],
            "action_type": "scheduled_exit_evaluation",
            "user_id": request.user_id,
            "position_id": request.position_id,
            "cycle_id": request.cycle_id,
            "position_record": request.position_record,
            "position_snapshot": None,
            "trailing_state": None,
            "exit_market_snapshot": None,
            "position_tracking_snapshot": None,
            "exit_ta_snapshot": None,
            "strategy_profile": None,
            "exit_decision": None,
            "policy_gate_result": None,
            "execution_request": None,
            "execution_result": None,
            "telegram_summary": None,
            "execution_trace": [],
        }  # type: ignore[return-value]

    def _build_graph(self):
        if StateGraph is None:
            return _SequentialCompiledExitGraph(self)

        builder = StateGraph(ExitGraphState)
        builder.add_node("load_position", self._node_load_position)
        builder.add_node("load_strategy_profile", self._node_load_strategy_profile)
        builder.add_node("load_market_context", self._node_load_market_context)
        builder.add_node("compute_exit_ta", self._node_compute_exit_ta)
        builder.add_node("notify_ta_progress", self._node_notify_ta_progress)
        builder.add_node("build_exit_inputs", self._node_build_exit_inputs)
        builder.add_node("exit_decision", self._node_exit_decision)
        builder.add_node("notify_decision_progress", self._node_notify_decision_progress)
        builder.add_node("apply_exit_policy_gate", self._node_apply_exit_policy_gate)
        builder.add_node("notify_policy_progress", self._node_notify_policy_progress)
        builder.add_node("persist_evaluation", self._node_persist_evaluation)
        builder.add_node("execute_exit", self._node_execute_exit)
        builder.add_node("persist_exit_result", self._node_persist_exit_result)
        builder.add_node("notify_telegram", self._node_notify_telegram)

        builder.add_edge(START, "load_position")
        builder.add_edge("load_position", "load_strategy_profile")
        builder.add_edge("load_strategy_profile", "load_market_context")
        builder.add_edge("load_market_context", "compute_exit_ta")
        builder.add_edge("compute_exit_ta", "notify_ta_progress")
        builder.add_edge("notify_ta_progress", "build_exit_inputs")
        builder.add_edge("build_exit_inputs", "exit_decision")
        builder.add_edge("exit_decision", "notify_decision_progress")
        builder.add_edge("notify_decision_progress", "apply_exit_policy_gate")
        builder.add_edge("apply_exit_policy_gate", "notify_policy_progress")
        builder.add_conditional_edges(
            "notify_policy_progress",
            self._route_after_policy_gate,
            {
                "persist_evaluation": "persist_evaluation",
                "execute_exit": "execute_exit",
                END: END,
            },
        )
        builder.add_edge("persist_evaluation", END)
        builder.add_edge("execute_exit", "persist_exit_result")
        builder.add_edge("persist_exit_result", "notify_telegram")
        builder.add_edge("notify_telegram", END)
        return builder.compile(checkpointer=build_checkpointer())

    def _node_load_position(self, state: ExitGraphState) -> dict[str, Any]:
        record: PositionRecord = state["position_record"]  # type: ignore[assignment]
        current_price = record.current_price_usd or record.entry_price_usd
        unrealized_pnl_pct = None
        if record.entry_price_usd and current_price:
            unrealized_pnl_pct = ((current_price - record.entry_price_usd) / record.entry_price_usd) * 100

        opened_at = self._parse_datetime(record.opened_at)
        holding_time_hours = None
        if opened_at is not None:
            holding_time_hours = max((datetime.now(UTC) - opened_at).total_seconds() / 3600, 0.0)

        position_snapshot: PositionSnapshot = {
            "position_id": record.position_id,
            "user_id": record.user_id,
            "source_id": record.source_id,
            "asset_lane": record.asset_lane,  # type: ignore[typeddict-item]
            "chain": record.chain,
            "symbol": record.symbol,
            "token_contract_address": record.token_contract_address,
            "wallet_address": record.wallet_address,
            "status": "closed" if record.status == "closed" else "open",
            "entry_price_usd": record.entry_price_usd,
            "entry_amount_usd": record.entry_amount_usd,
            "entry_token_amount": record.entry_token_amount,
            "current_price_usd": current_price,
            "unrealized_pnl_pct": unrealized_pnl_pct,
            "holding_time_hours": holding_time_hours,
            "opened_at": record.opened_at,
            "last_evaluated_at": record.last_exit_evaluated_at,
        }
        trailing_state: TrailingState = {
            "armed": bool((record.trailing_state or {}).get("armed", False)),
            "activated_at": (record.trailing_state or {}).get("activated_at"),
            "activation_price_usd": (record.trailing_state or {}).get("activation_price_usd"),
            "peak_price_usd": (record.trailing_state or {}).get("peak_price_usd", record.peak_price_since_open_usd),
            "trailing_drawdown_pct": (record.trailing_state or {}).get("trailing_drawdown_pct"),
            "last_action": (record.trailing_state or {}).get("last_action"),
        }
        return {"position_snapshot": position_snapshot, "trailing_state": trailing_state}

    def _node_load_strategy_profile(self, state: ExitGraphState) -> dict[str, Any]:
        user_id = state.get("user_id") or "unknown"
        profile: UserStrategyProfile = self.strategy_profiles.get_or_create(str(user_id))
        return {"strategy_profile": profile.model_dump()}

    def _node_load_market_context(self, state: ExitGraphState) -> dict[str, Any]:
        position: PositionSnapshot = state["position_snapshot"]  # type: ignore[assignment]
        trailing_state: TrailingState = state["trailing_state"] or {}  # type: ignore[assignment]
        strategy_profile = state["strategy_profile"] or {}
        tracked = self.position_tracker_agent.track_position(
            position_snapshot=position,
            strategy_profile=strategy_profile,
        )
        position_tracking = PositionTrackingSnapshot(**tracked["position_tracking_snapshot"])
        return {
            "position_tracking_snapshot": position_tracking,
            "exit_market_snapshot": ExitMarketSnapshot(
                asset_lane=position["asset_lane"],
                chain=position["chain"],
                current_price_usd=position_tracking["current_price_usd"],
                liquidity_usd=position_tracking["liquidity_usd"],
                volume_24h_usd=position_tracking["volume_24h_usd"],
                quote_available=position_tracking["quote_available"],
                quote_price_impact_pct=position_tracking["quote_price_impact_pct"],
                kline_window=position_tracking["kline_window"],
            ),
        }

    def _node_compute_exit_ta(self, state: ExitGraphState) -> dict[str, Any]:
        position: PositionSnapshot = state["position_snapshot"]  # type: ignore[assignment]
        trailing_state: TrailingState = state["trailing_state"] or {}  # type: ignore[assignment]
        strategy = state["strategy_profile"] or {}
        market: ExitMarketSnapshot = state["exit_market_snapshot"]  # type: ignore[assignment]
        tracking: PositionTrackingSnapshot = state["position_tracking_snapshot"] or {}  # type: ignore[assignment]

        entry_price = position["entry_price_usd"]
        current_price = market["current_price_usd"]
        kline_peak = self._extract_kline_peak(market.get("kline_window") or [])
        peak_candidates = [
            trailing_state.get("peak_price_usd"),
            position.get("current_price_usd"),
            kline_peak,
            current_price,
            entry_price,
        ]
        filtered_peak_candidates = [float(value) for value in peak_candidates if value is not None]
        peak_price = max(filtered_peak_candidates) if filtered_peak_candidates else None
        unrealized_pnl_pct = tracking.get("unrealized_pnl_pct")
        if unrealized_pnl_pct is None and entry_price and current_price:
            unrealized_pnl_pct = ((current_price - entry_price) / entry_price) * 100
        drawdown_from_peak_pct = None
        if peak_price and current_price:
            drawdown_from_peak_pct = max(((peak_price - current_price) / peak_price) * 100, 0.0)

        hard_stop_hit = (unrealized_pnl_pct or 0.0) <= -float(strategy.get("default_stop_loss_pct", 0.0))
        hard_take_profit_hit = (unrealized_pnl_pct or 0.0) >= float(strategy.get("default_take_profit_pct", 0.0))
        trailing_activation_hit = (
            bool(strategy.get("trailing_enabled", True))
            and not bool(trailing_state.get("armed"))
            and (unrealized_pnl_pct or 0.0) >= float(strategy.get("trailing_activation_profit_pct", 0.0))
        )
        trailing_fire_hit = (
            bool(trailing_state.get("armed"))
            and drawdown_from_peak_pct is not None
            and drawdown_from_peak_pct >= float(
                trailing_state.get("trailing_drawdown_pct") or strategy.get("trailing_drawdown_pct", 0.0)
            )
        )
        max_holding_time_hit = (
            position["holding_time_hours"] is not None
            and position["holding_time_hours"] >= float(strategy.get("max_holding_time_hours", 0))
        )

        summary_parts = []
        for code, flag in (
            ("hard_stop", hard_stop_hit),
            ("hard_take_profit", hard_take_profit_hit),
            ("trailing_activation", trailing_activation_hit),
            ("trailing_fire", trailing_fire_hit),
            ("max_holding_time", max_holding_time_hit),
        ):
            if flag:
                summary_parts.append(code)

        exit_ta_snapshot: ExitTASnapshot = {
            "asset_lane": position["asset_lane"],
            "entry_price_usd": entry_price,
            "current_price_usd": current_price,
            "peak_price_usd": peak_price,
            "unrealized_pnl_pct": unrealized_pnl_pct,
            "drawdown_from_peak_pct": drawdown_from_peak_pct,
            "hard_stop_hit": hard_stop_hit,
            "hard_take_profit_hit": hard_take_profit_hit,
            "trailing_activation_hit": trailing_activation_hit,
            "trailing_fire_hit": trailing_fire_hit,
            "max_holding_time_hit": max_holding_time_hit,
            "exit_ta_summary": ", ".join(summary_parts) or "no exit trigger hit",
        }
        return {"exit_ta_snapshot": exit_ta_snapshot}

    def _node_notify_ta_progress(self, state: ExitGraphState) -> dict[str, Any]:
        ta = state["exit_ta_snapshot"] or {}
        summary = (
            f"Exit TA ready: pnl={ta.get('unrealized_pnl_pct')}, drawdown={ta.get('drawdown_from_peak_pct')}, "
            f"summary={ta.get('exit_ta_summary')}."
        )
        return self._progress_update(
            state,
            stage="exit_ta",
            summary=summary,
            details={
                "symbol": (state.get("position_snapshot") or {}).get("symbol"),
                "pnl_pct": ta.get("unrealized_pnl_pct"),
                "drawdown_pct": ta.get("drawdown_from_peak_pct"),
                "triggers": ta.get("exit_ta_summary"),
            },
        )

    def _node_build_exit_inputs(self, state: ExitGraphState) -> dict[str, Any]:
        position: PositionSnapshot = state["position_snapshot"]  # type: ignore[assignment]
        market: ExitMarketSnapshot = state["exit_market_snapshot"]  # type: ignore[assignment]
        ta_snapshot: ExitTASnapshot = state["exit_ta_snapshot"]  # type: ignore[assignment]
        return {
            "telegram_summary": (
                f"Reevaluating {position['symbol']} on {position['chain']} at "
                f"${market['current_price_usd']:.4f}. TA: {ta_snapshot['exit_ta_summary']}."
            )
        }

    def _node_exit_decision(self, state: ExitGraphState) -> dict[str, Any]:
        position: PositionSnapshot = state["position_snapshot"]  # type: ignore[assignment]
        trailing_state: TrailingState = state["trailing_state"]  # type: ignore[assignment]
        market_snapshot: ExitMarketSnapshot = state["exit_market_snapshot"]  # type: ignore[assignment]
        ta_snapshot: ExitTASnapshot = state["exit_ta_snapshot"]  # type: ignore[assignment]
        strategy_profile = state["strategy_profile"] or {}
        decision = self.exit_agent.decide(
            position_snapshot=position,
            trailing_state=trailing_state,
            market_snapshot=market_snapshot,
            ta_snapshot=ta_snapshot,
            strategy_profile=strategy_profile,
        )
        return {"exit_decision": decision, "telegram_summary": decision["telegram_summary"]}

    def _node_notify_decision_progress(self, state: ExitGraphState) -> dict[str, Any]:
        decision = state["exit_decision"] or {}
        summary = (
            f"Exit decision formed: action={decision.get('decision')}, "
            f"reason={decision.get('decision_reason_code')}."
        )
        return self._progress_update(
            state,
            stage="exit_decision",
            summary=summary,
            details={
                "action": decision.get("decision"),
                "reason": decision.get("decision_reason_code"),
                "confidence": decision.get("confidence"),
            },
        )

    def _node_apply_exit_policy_gate(self, state: ExitGraphState) -> dict[str, Any]:
        evaluation = self.policy_engine.evaluate(state)
        return {
            "policy_gate_result": {
                "passed": evaluation.passed,
                "action": evaluation.action,
                "failure_codes": evaluation.failure_codes,
                "summary": evaluation.summary,
            }
        }

    def _node_notify_policy_progress(self, state: ExitGraphState) -> dict[str, Any]:
        gate = state["policy_gate_result"] or {}
        summary = (
            f"Exit policy gate: passed={gate.get('passed')}, action={gate.get('action')}, "
            f"failures={gate.get('failure_codes') or []}."
        )
        return self._progress_update(
            state,
            stage="exit_policy_gate",
            summary=summary,
            details={
                "passed": gate.get("passed"),
                "action": gate.get("action"),
                "failures": gate.get("failure_codes") or [],
            },
        )

    def _route_after_policy_gate(self, state: ExitGraphState) -> str:
        gate = state.get("policy_gate_result") or {}
        action = gate.get("action")
        if action in {"hold", "persist_trailing", "block"}:
            return "persist_evaluation"
        if action == "execute":
            return "execute_exit"
        return END

    def _node_persist_evaluation(self, state: ExitGraphState) -> dict[str, Any]:
        position: PositionSnapshot = state["position_snapshot"]  # type: ignore[assignment]
        trailing_state: TrailingState = dict(state["trailing_state"] or {})  # type: ignore[assignment]
        decision = state["exit_decision"] or {}
        gate = state["policy_gate_result"] or {}
        market = state["exit_market_snapshot"] or {}
        ta = state["exit_ta_snapshot"] or {}

        if gate.get("action") == "persist_trailing":
            trailing_state["armed"] = True
            trailing_state["activated_at"] = utc_now_iso()
            trailing_state["activation_price_usd"] = market.get("current_price_usd")
            trailing_state["peak_price_usd"] = ta.get("peak_price_usd") or market.get("current_price_usd")
            trailing_state["trailing_drawdown_pct"] = trailing_state.get("trailing_drawdown_pct") or (
                state["strategy_profile"] or {}
            ).get("trailing_drawdown_pct")
            trailing_state["last_action"] = "armed"
        elif gate.get("action") == "hold":
            if ta.get("peak_price_usd") is not None:
                trailing_state["peak_price_usd"] = max(
                    trailing_state.get("peak_price_usd") or ta.get("peak_price_usd"),
                    ta.get("peak_price_usd"),
                )
            trailing_state["last_action"] = "hold"

        self.evaluation_repository.save(
            PositionExitEvaluationRecord(
                position_id=position["position_id"],
                cycle_id=str(state.get("cycle_id") or "unknown"),
                decision=decision.get("decision", "hold"),
                decision_reason_code=decision.get("decision_reason_code", "UNKNOWN"),
                evaluation={
                    "policy_gate_result": gate,
                    "telegram_summary": state.get("telegram_summary"),
                },
                trailing_state=trailing_state,
                market_snapshot=market,
                ta_snapshot=ta,
            )
        )

        if self.position_repository is not None:
            record = self.position_repository.get_by_position_id(position["position_id"])
            if record is not None:
                current_price = market.get("current_price_usd")
                peak_price = trailing_state.get("peak_price_usd")
                if current_price is not None:
                    record.current_price_usd = current_price
                if peak_price is not None:
                    record.peak_price_since_open_usd = max(record.peak_price_since_open_usd or peak_price, peak_price)
                record.trailing_state = trailing_state
                record.last_exit_evaluated_at = utc_now_iso()
                self.position_repository.save(record)

        return {"trailing_state": trailing_state}

    def _node_execute_exit(self, state: ExitGraphState) -> dict[str, Any]:
        position: PositionSnapshot = state["position_snapshot"]  # type: ignore[assignment]
        strategy = state["strategy_profile"] or {}
        exit_token = "USDC"
        amount = position["entry_token_amount"] or position["entry_amount_usd"]
        execution_request = {
            "asset_lane": position["asset_lane"],
            "position_id": position["position_id"],
            "side": "sell",
            "chain": position["chain"],
            "wallet_address": position["wallet_address"],
            "from_token": position["token_contract_address"] or position["symbol"],
            "to_token": exit_token,
            "readable_amount": str(amount),
            "slippage_pct": (
                strategy.get("max_slippage_pct_major")
                if position["asset_lane"] == "major"
                else strategy.get("max_slippage_pct_regular")
            ),
        }
        swap_output = _resolve_task_result(_execute_exit_task(
            self.swap_execution_agent,
            intent={
                "user_id": state.get("user_id"),
                "position_id": position["position_id"],
                "asset_lane": position["asset_lane"],
                "side": "sell",
                "chain": position["chain"],
                "wallet_address": position["wallet_address"],
                "from_token": position["token_contract_address"] or position["symbol"],
                "to_token": exit_token,
                "readable_amount": str(amount),
                "slippage_pct": (
                    strategy.get("max_slippage_pct_major")
                    if position["asset_lane"] == "major"
                    else strategy.get("max_slippage_pct_regular")
                ),
            },
        ))
        return {
            "execution_request": swap_output["execution_request"],
            "execution_result": swap_output["execution_result"],
        }

    def _node_persist_exit_result(self, state: ExitGraphState) -> dict[str, Any]:
        position: PositionSnapshot = state["position_snapshot"]  # type: ignore[assignment]
        decision = state["exit_decision"] or {}
        market = state["exit_market_snapshot"] or {}
        ta = state["exit_ta_snapshot"] or {}
        trailing_state = state["trailing_state"] or {}
        execution_result = state["execution_result"] or {}

        self.evaluation_repository.save(
            PositionExitEvaluationRecord(
                position_id=position["position_id"],
                cycle_id=str(state.get("cycle_id") or "unknown"),
                decision=decision.get("decision", "exit_hard"),
                decision_reason_code=decision.get("decision_reason_code", "UNKNOWN"),
                evaluation={
                    "policy_gate_result": state.get("policy_gate_result"),
                    "execution_result": execution_result,
                    "telegram_summary": state.get("telegram_summary"),
                },
                trailing_state=trailing_state,
                market_snapshot=market,
                ta_snapshot=ta,
            )
        )

        if self.execution_repository is not None:
            execution_id = execution_result.get("execution_id") or f"exit:{position['position_id']}:{state.get('cycle_id')}"
            self.execution_repository.save(
                TradeExecutionRecord(
                    execution_id=execution_id,
                    signal_id=None,
                    position_id=position["position_id"],
                    asset_lane=position["asset_lane"],
                    side="sell",
                    chain=position["chain"],
                    wallet_address=position["wallet_address"],
                    from_token=str((state["execution_request"] or {}).get("from_token", "")),
                    to_token=str((state["execution_request"] or {}).get("to_token", "")),
                    requested_amount=str((state["execution_request"] or {}).get("readable_amount", "")),
                    approve_tx_hash=execution_result.get("approve_tx_hash"),
                    swap_tx_hash=execution_result.get("swap_tx_hash"),
                    success=bool(execution_result.get("success")),
                    error_code=execution_result.get("error_code"),
                    error_message=execution_result.get("error_message"),
                    idempotency_key=f"{position['position_id']}:{state.get('cycle_id')}:sell",
                    execution=execution_result,
                )
            )

        if self.position_event_repository is not None:
            self.position_event_repository.save(
                PositionEventRecord(
                    position_id=position["position_id"],
                    event_type="exit_execution_succeeded" if execution_result.get("success") else "exit_execution_failed",
                    event_reason_code=decision.get("decision_reason_code"),
                    event={
                        "decision": decision,
                        "execution_result": execution_result,
                        "cycle_id": state.get("cycle_id"),
                    },
                )
            )

        if self.position_repository is not None:
            record = self.position_repository.get_by_position_id(position["position_id"])
            if record is not None:
                record.last_exit_evaluated_at = utc_now_iso()
                current_price = market.get("current_price_usd")
                peak_price = trailing_state.get("peak_price_usd")
                if current_price is not None:
                    record.current_price_usd = current_price
                if peak_price is not None:
                    record.peak_price_since_open_usd = max(record.peak_price_since_open_usd or peak_price, peak_price)
                if execution_result.get("success"):
                    record.status = "closed"
                    record.closed_at = utc_now_iso()
                self.position_repository.save(record)
        return {}

    def _node_notify_telegram(self, state: ExitGraphState) -> dict[str, Any]:
        execution = state["execution_result"] or {}
        if execution.get("success"):
            summary = f"{state['telegram_summary']} Exit execution submitted successfully."
        else:
            summary = f"{state['telegram_summary']} Exit execution failed: {execution.get('error_code', 'unknown')}."
        if self.notification_service is not None:
            self.notification_service.send_exit_notification(
                user_id=str(state.get("user_id") or "unknown"),
                chat_id=str(state.get("user_id") or "unknown"),
                position_id=str(state.get("position_id") or "unknown"),
                message_text=summary,
            )
        return {"telegram_summary": summary}

    @staticmethod
    def _extract_kline_peak(kline_window: list[dict[str, Any]]) -> float | None:
        closes: list[float] = []
        for candle in kline_window:
            close = candle.get("close")
            if isinstance(close, (int, float)):
                closes.append(float(close))
        return max(closes) if closes else None

    def _progress_update(
        self,
        state: ExitGraphState,
        *,
        stage: str,
        summary: str,
        details: dict | None = None,
    ) -> dict[str, Any]:
        trace = list(state.get("execution_trace") or [])
        trace.append({"stage": stage, "summary": summary})
        if self.notification_service is not None:
            self.notification_service.send_progress_notification(
                user_id=str(state.get("user_id") or "unknown"),
                chat_id=str(state.get("user_id") or "unknown"),
                related_signal_id=None,
                related_position_id=str(state.get("position_id") or "unknown"),
                stage=stage,
                message_text=summary,
                details=details,
            )
        return {"execution_trace": trace}

    @staticmethod
    def _parse_datetime(value: str | None) -> datetime | None:
        if not value:
            return None
        normalized = value.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(normalized)
        except ValueError:
            return None
