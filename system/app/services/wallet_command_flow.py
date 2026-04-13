from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.agents.wallet_command import WalletCommandAgent
from app.config.settings import get_settings
from app.graphs.runtime import build_checkpointer, build_thread_id, invoke_graph
from app.graphs.state import WalletCommandGraphState
from app.schemas.commands import CommandEnvelope

try:
    from langgraph.graph import END, START, StateGraph
except ModuleNotFoundError:  # pragma: no cover - local scaffold fallback
    END = "__end__"
    START = "__start__"
    StateGraph = None  # type: ignore[assignment]


SUPPORTED_WALLET_COMMANDS = {"start", "status", "portfolio", "history"}


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
        current.update(self.service._node_wallet_agent(current))
        current.update(self.service._node_post_process(current))
        return current  # type: ignore[return-value]


class WalletCommandGraphService:
    def __init__(self, *, wallet_command_agent: WalletCommandAgent) -> None:
        self.wallet_command_agent = wallet_command_agent
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
            "wallet_command_result": None,
            "response_message": None,
            "response_payload": None,
        }

    def _build_graph(self):
        if StateGraph is None:
            return _SequentialWalletCommandGraph(self)

        builder = StateGraph(WalletCommandGraphState)
        builder.add_node("ingest_command", self._node_ingest_command)
        builder.add_node("classify_command", self._node_classify_command)
        builder.add_node("wallet_agent", self._node_wallet_agent)
        builder.add_node("post_process", self._node_post_process)

        builder.add_edge(START, "ingest_command")
        builder.add_edge("ingest_command", "classify_command")
        builder.add_conditional_edges(
            "classify_command",
            self._route_after_classify,
            {"wallet_agent": "wallet_agent", END: END},
        )
        builder.add_edge("wallet_agent", "post_process")
        builder.add_edge("post_process", END)
        return builder.compile(checkpointer=build_checkpointer())

    def _node_ingest_command(self, state: WalletCommandGraphState) -> dict[str, Any]:
        return {"messages": state["messages"]}

    def _node_classify_command(self, state: WalletCommandGraphState) -> dict[str, Any]:
        raw_text = state["raw_text"].strip()
        command_name: str | None = None
        if raw_text == "/start":
            command_name = "start"
        elif raw_text == "/status":
            command_name = "status"
        elif raw_text == "/portfolio":
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
        return "wallet_agent" if state["supported_command"] else END

    def _node_wallet_agent(self, state: WalletCommandGraphState) -> dict[str, Any]:
        result = self.wallet_command_agent.handle(
            user_id=state["user_id"],
            command_name=str(state["command_name"]),
            raw_text=state["raw_text"],
        )
        return {
            "wallet_command_result": result.model_dump(),
        }

    def _node_post_process(self, state: WalletCommandGraphState) -> dict[str, Any]:
        result = state["wallet_command_result"] or {}
        return {
            "response_message": result.get("message"),
            "response_payload": result.get("payload"),
        }
