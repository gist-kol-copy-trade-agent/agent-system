from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.graphs.runtime import build_checkpointer, build_thread_id
from app.graphs.state import WalletCommandGraphState
from app.schemas.commands import CommandEnvelope
from app.services.source_registry import SourceRegistryService
from app.services.strategy_profiles import StrategyProfileService

try:
    from langgraph.graph import END, START, StateGraph
except ModuleNotFoundError:  # pragma: no cover - local scaffold fallback
    END = "__end__"
    START = "__start__"
    StateGraph = None  # type: ignore[assignment]


SUPPORTED_DETERMINISTIC_COMMANDS = {"trade-style", "follow", "stop"}


@dataclass
class DeterministicCommandRequest:
    user_id: str
    chat_id: str
    raw_text: str


class _SequentialDeterministicCommandGraph:
    def __init__(self, service: DeterministicCommandGraphService) -> None:
        self.service = service

    def invoke(self, state: WalletCommandGraphState, config: dict[str, Any] | None = None) -> WalletCommandGraphState:
        current = dict(state)
        current.update(self.service._node_ingest_command(current))
        current.update(self.service._node_classify_command(current))
        if self.service._route_after_classify(current) == END:
            return current  # type: ignore[return-value]
        current.update(self.service._node_execute_command(current))
        current.update(self.service._node_post_process(current))
        return current  # type: ignore[return-value]


class DeterministicCommandGraphService:
    def __init__(
        self,
        *,
        strategy_profiles: StrategyProfileService,
        source_registry: SourceRegistryService,
        callback_url: str,
        callback_secret: str,
    ) -> None:
        self.strategy_profiles = strategy_profiles
        self.source_registry = source_registry
        self.callback_url = callback_url
        self.callback_secret = callback_secret
        self.graph = self._build_graph()

    def run(self, request: DeterministicCommandRequest | CommandEnvelope) -> WalletCommandGraphState:
        if isinstance(request, CommandEnvelope):
            normalized = DeterministicCommandRequest(
                user_id=request.user_id,
                chat_id=request.chat_id,
                raw_text=request.raw_text,
            )
        else:
            normalized = request
        initial_state = self._initial_state(normalized)
        config = {"configurable": {"thread_id": build_thread_id("command", f"{normalized.user_id}:{normalized.raw_text}")}}
        return self.graph.invoke(initial_state, config=config)

    def _initial_state(self, request: DeterministicCommandRequest) -> WalletCommandGraphState:
        return {
            "messages": [{"role": "user", "content": request.raw_text}],
            "action_type": "deterministic-command",
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
            return _SequentialDeterministicCommandGraph(self)

        builder = StateGraph(WalletCommandGraphState)
        builder.add_node("ingest_command", self._node_ingest_command)
        builder.add_node("classify_command", self._node_classify_command)
        builder.add_node("execute_command", self._node_execute_command)
        builder.add_node("post_process", self._node_post_process)

        builder.add_edge(START, "ingest_command")
        builder.add_edge("ingest_command", "classify_command")
        builder.add_conditional_edges(
            "classify_command",
            self._route_after_classify,
            {"execute_command": "execute_command", END: END},
        )
        builder.add_edge("execute_command", "post_process")
        builder.add_edge("post_process", END)
        return builder.compile(checkpointer=build_checkpointer())

    def _node_ingest_command(self, state: WalletCommandGraphState) -> dict[str, Any]:
        return {"messages": state["messages"]}

    def _node_classify_command(self, state: WalletCommandGraphState) -> dict[str, Any]:
        raw_text = state["raw_text"].strip()
        command_name: str | None = None
        if raw_text.startswith("/trade-style"):
            command_name = "trade-style"
        elif raw_text.startswith("/follow "):
            command_name = "follow"
        elif raw_text.startswith("/stop "):
            command_name = "stop"

        supported = command_name in SUPPORTED_DETERMINISTIC_COMMANDS
        message = None if supported else "Unsupported deterministic command."
        return {
            "command_name": command_name,
            "supported_command": supported,
            "response_message": message,
            "response_payload": {} if not supported else None,
        }

    def _route_after_classify(self, state: WalletCommandGraphState) -> str:
        return "execute_command" if state["supported_command"] else END

    def _node_execute_command(self, state: WalletCommandGraphState) -> dict[str, Any]:
        command_name = state["command_name"]
        raw_text = state["raw_text"]
        user_id = state["user_id"]

        if command_name == "trade-style":
            preset, patch = self.strategy_profiles.parse_trade_style_text(raw_text)
            if preset:
                profile = self.strategy_profiles.apply_preset(user_id=user_id, base_style=preset, updated_by="user")
                return {
                    "wallet_command_result": {
                        "message": f"Trading style updated to {profile.base_style}.",
                        "payload": profile.model_dump(),
                    }
                }
            if patch:
                profile = self.strategy_profiles.apply_patch(user_id=user_id, patch=patch, updated_by="user")
                return {
                    "wallet_command_result": {
                        "message": "Trading style overrides updated.",
                        "payload": profile.model_dump(),
                    }
                }
            profile = self.strategy_profiles.get_or_create(user_id)
            return {
                "wallet_command_result": {
                    "message": "Current trading style profile.",
                    "payload": profile.model_dump(),
                }
            }

        if command_name == "follow":
            channel_name = raw_text.removeprefix("/follow").strip()
            record = self.source_registry.follow(
                user_id=user_id,
                channel_name=channel_name,
                channel_url=f"https://t.me/{channel_name}",
                callback_url=self.callback_url,
                callback_secret=self.callback_secret,
            )
            return {
                "wallet_command_result": {
                    "message": f"Source {record.channel_name} is {record.status}.",
                    "payload": {
                        "source_id": record.source_id,
                        "channel_name": record.channel_name,
                        "status": record.status,
                        "scraper_subscription_id": record.scraper_subscription_id,
                    },
                }
            }

        channel_name = raw_text.removeprefix("/stop").strip()
        record = self.source_registry.stop(user_id=user_id, channel_name=channel_name)
        return {
            "wallet_command_result": {
                "message": f"Source {record.channel_name} is {record.status}.",
                "payload": {
                    "source_id": record.source_id,
                    "channel_name": record.channel_name,
                    "status": record.status,
                },
            }
        }

    def _node_post_process(self, state: WalletCommandGraphState) -> dict[str, Any]:
        result = state["wallet_command_result"] or {}
        return {
            "response_message": result.get("message"),
            "response_payload": result.get("payload"),
        }
