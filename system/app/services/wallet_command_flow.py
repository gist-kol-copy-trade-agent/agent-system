from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.agents.history import HistoryAgent
from app.agents.position_tracker import PositionTrackerAgent
from app.config.settings import get_settings
from app.graphs.runtime import build_checkpointer, build_thread_id, invoke_graph
from app.graphs.state import WalletCommandGraphState
from app.persistence.repositories import FollowedSourceRepository, PositionRepository
from app.schemas.commands import CommandEnvelope
from app.services.strategy_profiles import StrategyProfileService

try:
    from langgraph.graph import END, START, StateGraph
except ModuleNotFoundError:  # pragma: no cover - local scaffold fallback
    END = "__end__"
    START = "__start__"
    StateGraph = None  # type: ignore[assignment]


SUPPORTED_WALLET_COMMANDS = {"portfolio", "history"}


@dataclass
class WalletCommandRequest:
    user_id: str
    chat_id: str
    raw_text: str


class _SequentialWalletCommandGraph:
    def __init__(self, service: WalletCommandGraphService) -> None:
        self.service = service

    def invoke(self, state: WalletCommandGraphState, config: dict[str, Any] | None = None) -> WalletCommandGraphState:
        current = dict(state)
        current.update(self.service._node_ingest_command(current))
        current.update(self.service._node_classify_command(current))
        if self.service._route_after_classify(current) == END:
            return current  # type: ignore[return-value]
        current.update(self.service._node_post_process(current))
        return current  # type: ignore[return-value]


class WalletCommandGraphService:
    def __init__(
        self,
        *,
        position_tracker_agent: PositionTrackerAgent | None = None,
        history_agent: HistoryAgent | None = None,
        strategy_profiles: StrategyProfileService | None = None,
        source_repository: FollowedSourceRepository | None = None,
        position_repository: PositionRepository | None = None,
    ) -> None:
        self.position_tracker_agent = position_tracker_agent or PositionTrackerAgent()
        self.history_agent = history_agent or HistoryAgent()
        self.strategy_profiles = strategy_profiles
        self.source_repository = source_repository
        self.position_repository = position_repository
        self.durability_mode = get_settings().langgraph.command_durability
        self.graph = self._build_graph()

    def run(self, request: WalletCommandRequest | CommandEnvelope) -> WalletCommandGraphState:
        if isinstance(request, CommandEnvelope):
            normalized = WalletCommandRequest(user_id=request.user_id, chat_id=request.chat_id, raw_text=request.raw_text)
        else:
            normalized = request
        initial_state = self._initial_state(normalized)
        config = {"configurable": {"thread_id": build_thread_id("command", f"{normalized.user_id}:{normalized.raw_text}")}}
        return invoke_graph(self.graph, initial_state, config=config, durability=self.durability_mode)

    def _initial_state(self, request: WalletCommandRequest) -> WalletCommandGraphState:
        return {
            "messages": [{"role": "user", "content": request.raw_text}],
            "action_type": "wallet-command",
            "user_id": request.user_id,
            "chat_id": request.chat_id,
            "raw_text": request.raw_text,
            "command_name": None,
            "supported_command": False,
            "response_message": None,
            "response_payload": None,
        }

    def _build_graph(self):
        if StateGraph is None:
            return _SequentialWalletCommandGraph(self)

        builder = StateGraph(WalletCommandGraphState)
        builder.add_node("ingest_command", self._node_ingest_command)
        builder.add_node("classify_command", self._node_classify_command)
        builder.add_node("post_process", self._node_post_process)

        builder.add_edge(START, "ingest_command")
        builder.add_edge("ingest_command", "classify_command")
        builder.add_conditional_edges(
            "classify_command",
            self._route_after_classify,
            {"post_process": "post_process", END: END},
        )
        builder.add_edge("post_process", END)
        return builder.compile(checkpointer=build_checkpointer())

    def _node_ingest_command(self, state: WalletCommandGraphState) -> dict[str, Any]:
        return {"messages": state["messages"]}

    def _node_classify_command(self, state: WalletCommandGraphState) -> dict[str, Any]:
        raw_text = state["raw_text"].strip()
        command_name: str | None = None
        if raw_text == "/portfolio":
            command_name = "portfolio"
        elif raw_text.startswith("/history"):
            command_name = "history"

        supported = command_name in SUPPORTED_WALLET_COMMANDS
        message = None if supported else "Unsupported wallet command."
        return {
            "command_name": command_name,
            "supported_command": supported,
            "response_message": message,
            "response_payload": {} if not supported else None,
        }

    def _route_after_classify(self, state: WalletCommandGraphState) -> str:
        return "post_process" if state["supported_command"] else END

    def _node_post_process(self, state: WalletCommandGraphState) -> dict[str, Any]:
        command_name = state.get("command_name")
        payload: dict[str, Any] = {}
        response_message = state.get("response_message")

        if command_name == "portfolio":
            positions = self._list_open_positions(state["user_id"])
            tracked = self.position_tracker_agent.track_portfolio(
                user_id=state["user_id"],
                bot_positions=[self._serialize_position(position) for position in positions],
                strategy_profile=self._get_strategy_profile(state["user_id"]),
            )
            portfolio_tracking = tracked.get("portfolio_tracking_snapshot") or {}
            chain_distribution = self._build_chain_distribution(positions)
            payload.update(
                {
                    "active_positions": [self._serialize_position(position) for position in positions],
                    "active_position_count": len(positions),
                    "chain_distribution": chain_distribution,
                    "portfolio_tracking": portfolio_tracking,
                }
            )
            position_lines = (
                [
                    f"- `{item['symbol']}` on `{item['chain']}` | entry `${item['entry_amount_usd']}` | current `${item.get('current_price_usd')}`"
                    for item in payload["active_positions"][:5]
                ]
                if payload["active_positions"]
                else ["- No active bot-managed positions."]
            )
            tracked_rows = portfolio_tracking.get("tracked_bot_positions") or []
            pnl_lines = (
                [
                    f"- `{item.get('symbol')}` | unrealized `{item.get('unrealized_pnl_pct')}`% | value `${item.get('value_usd')}`"
                    for item in tracked_rows[:5]
                ]
                if tracked_rows
                else ["- No tracked token PnL rows."]
            )
            response_message = (
                "💼 Portfolio\n\n"
                "Overview\n"
                f"- Active positions: `{len(positions)}`\n"
                f"- Chains: `{chain_distribution}`\n\n"
                "PnL Snapshot\n"
                + "\n".join(pnl_lines)
                + "\n\n"
                "Positions\n"
                + "\n".join(position_lines)
            )
        elif command_name == "history":
            closed_positions = [position for position in self._list_all_positions(state["user_id"]) if position.status == "closed"]
            time_window = self._extract_history_window(state["raw_text"])
            history_snapshot = self.history_agent.load_history(
                user_id=state["user_id"],
                raw_text=state["raw_text"],
                time_window=time_window,
            )
            payload.update(
                {
                    "dex_history_snapshot": history_snapshot,
                    "completed_trades": [self._serialize_position(position) for position in closed_positions],
                    "completed_trade_count": len(closed_positions),
                    "win_loss_summary": self._build_win_loss_summary(closed_positions),
                }
            )
            recent_lines = (
                [
                    f"- `{item['symbol']}` on `{item['chain']}` | entry `${item['entry_amount_usd']}`"
                    for item in payload["completed_trades"][:5]
                ]
                if payload["completed_trades"]
                else ["- No completed trades yet."]
            )
            response_message = (
                "📚 Trade History\n\n"
                "Summary\n"
                f"- Completed trades: `{len(closed_positions)}`\n"
                f"- Win/Loss: `{payload.get('win_loss_summary')}`\n"
                f"- DEX history rows: `{len((history_snapshot or {}).get('dex_history_rows') or [])}`\n\n"
                "Recent Trades\n"
                + "\n".join(recent_lines)
            )
        return {
            "response_message": response_message,
            "response_payload": payload,
        }

    def _count_active_sources(self, user_id: str) -> int:
        if self.source_repository is None:
            return 0
        return len([record for record in self.source_repository.list_by_user(user_id) if record.status == "active"])

    def _list_open_positions(self, user_id: str):
        if self.position_repository is None:
            return []
        return [position for position in self.position_repository.list_by_user(user_id) if position.status == "open"]

    def _list_all_positions(self, user_id: str):
        if self.position_repository is None:
            return []
        return self.position_repository.list_by_user(user_id)

    def _get_strategy_profile(self, user_id: str) -> dict[str, Any] | None:
        if self.strategy_profiles is None:
            return None
        profile = self.strategy_profiles.repository.get(user_id)
        return profile.model_dump() if profile is not None else None

    @staticmethod
    def _extract_history_window(raw_text: str) -> str | None:
        parts = raw_text.strip().split(maxsplit=1)
        if len(parts) == 2:
            return parts[1].strip()
        return None

    @staticmethod
    def _build_chain_distribution(positions) -> dict[str, int]:
        distribution: dict[str, int] = {}
        for position in positions:
            distribution[position.chain] = distribution.get(position.chain, 0) + 1
        return distribution

    @staticmethod
    def _build_win_loss_summary(positions) -> dict[str, int]:
        summary = {"wins": 0, "losses": 0, "unknown": 0}
        for position in positions:
            if position.entry_price_usd is None or position.current_price_usd is None:
                summary["unknown"] += 1
            elif position.current_price_usd >= position.entry_price_usd:
                summary["wins"] += 1
            else:
                summary["losses"] += 1
        return summary

    @staticmethod
    def _serialize_position(position) -> dict[str, Any]:
        return {
            "position_id": position.position_id,
            "symbol": position.symbol,
            "chain": position.chain,
            "status": position.status,
            "entry_amount_usd": position.entry_amount_usd,
            "entry_price_usd": position.entry_price_usd,
            "current_price_usd": position.current_price_usd,
            "opened_at": position.opened_at,
            "closed_at": position.closed_at,
        }
