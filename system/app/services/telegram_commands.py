from __future__ import annotations

from app.agents.wallet_command import WalletCommandAgent
from app.schemas.commands import CommandEnvelope, CommandResponse
from app.services.command_flow import DeterministicCommandGraphService
from app.services.source_registry import SourceRegistryService
from app.services.strategy_profiles import StrategyProfileService
from app.services.wallet_command_flow import WalletCommandGraphService


class TelegramCommandRouter:
    def __init__(
        self,
        *,
        strategy_profiles: StrategyProfileService,
        source_registry: SourceRegistryService,
        callback_url: str,
        callback_secret: str,
        wallet_command_agent: WalletCommandAgent | None = None,
        wallet_command_graph: WalletCommandGraphService | None = None,
        deterministic_command_graph: DeterministicCommandGraphService | None = None,
    ) -> None:
        self.strategy_profiles = strategy_profiles
        self.source_registry = source_registry
        self.callback_url = callback_url
        self.callback_secret = callback_secret
        self.wallet_command_agent = wallet_command_agent or WalletCommandAgent()
        self.wallet_command_graph = wallet_command_graph or WalletCommandGraphService(
            wallet_command_agent=self.wallet_command_agent
        )
        self.deterministic_command_graph = deterministic_command_graph or DeterministicCommandGraphService(
            strategy_profiles=self.strategy_profiles,
            source_registry=self.source_registry,
            callback_url=self.callback_url,
            callback_secret=self.callback_secret,
        )

    def handle(self, envelope: CommandEnvelope) -> CommandResponse:
        text = envelope.raw_text.strip()
        if text.startswith("/trade-style"):
            return self._handle_trade_style(envelope)
        if text.startswith("/follow "):
            return self._handle_follow(envelope)
        if text.startswith("/stop "):
            return self._handle_stop(envelope)
        if text == "/status":
            return self._handle_wallet_command(envelope, command_name="status")
        if text == "/start":
            return self._handle_wallet_command(envelope, command_name="start")
        if text == "/portfolio":
            return self._handle_wallet_command(envelope, command_name="portfolio")
        if text.startswith("/history"):
            return self._handle_wallet_command(envelope, command_name="history")
        return CommandResponse(ok=False, command="status", message="Unsupported command.", payload={})

    def _handle_trade_style(self, envelope: CommandEnvelope) -> CommandResponse:
        state = self.deterministic_command_graph.run(envelope)
        return CommandResponse(
            ok=bool(state["supported_command"]),
            command="trade-style",
            message=str(state["response_message"] or ""),
            payload=state["response_payload"] or {},
        )

    def _handle_follow(self, envelope: CommandEnvelope) -> CommandResponse:
        state = self.deterministic_command_graph.run(envelope)
        return CommandResponse(
            ok=bool(state["supported_command"]),
            command="follow",
            message=str(state["response_message"] or ""),
            payload=state["response_payload"] or {},
        )

    def _handle_stop(self, envelope: CommandEnvelope) -> CommandResponse:
        state = self.deterministic_command_graph.run(envelope)
        return CommandResponse(
            ok=bool(state["supported_command"]),
            command="stop",
            message=str(state["response_message"] or ""),
            payload=state["response_payload"] or {},
        )

    def _handle_wallet_command(self, envelope: CommandEnvelope, *, command_name: str) -> CommandResponse:
        state = self.wallet_command_graph.run(envelope)
        return CommandResponse(
            ok=bool(state["supported_command"]),
            command=command_name,  # type: ignore[arg-type]
            message=str(state["response_message"] or ""),
            payload=state["response_payload"] or {},
        )
