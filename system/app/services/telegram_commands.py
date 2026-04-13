from __future__ import annotations

from app.schemas.commands import CommandEnvelope, CommandResponse
from app.services.follow_command import FollowCommandService
from app.services.command_flow import DeterministicCommandGraphService
from app.services.source_registry import SourceRegistryService
from app.services.strategy_profiles import StrategyProfileService
from app.services.trade_style_setup import TradeStyleSetupService
from app.services.wallet_command_flow import WalletCommandGraphService
from app.services.wallet_service import WalletService


class TelegramCommandRouter:
    def __init__(
        self,
        *,
        strategy_profiles: StrategyProfileService,
        source_registry: SourceRegistryService,
        callback_url: str,
        callback_secret: str,
        wallet_service: WalletService | None = None,
        follow_command_service: FollowCommandService | None = None,
        trade_style_setup_service: TradeStyleSetupService | None = None,
        wallet_command_graph: WalletCommandGraphService | None = None,
        deterministic_command_graph: DeterministicCommandGraphService | None = None,
    ) -> None:
        self.strategy_profiles = strategy_profiles
        self.source_registry = source_registry
        self.callback_url = callback_url
        self.callback_secret = callback_secret
        self.wallet_service = wallet_service
        self.follow_command_service = follow_command_service
        self.trade_style_setup_service = trade_style_setup_service
        self.wallet_command_graph = wallet_command_graph or WalletCommandGraphService()
        self.deterministic_command_graph = deterministic_command_graph or DeterministicCommandGraphService(
            strategy_profiles=self.strategy_profiles,
            source_registry=self.source_registry,
            callback_url=self.callback_url,
            callback_secret=self.callback_secret,
        )

    def handle(self, envelope: CommandEnvelope) -> CommandResponse:
        text = envelope.raw_text.strip()
        if self.wallet_service is not None and (
            text in {"/start", "/status"} or self.wallet_service.has_pending_session(user_id=envelope.user_id)
        ):
            return self.wallet_service.handle(
                user_id=envelope.user_id,
                chat_id=envelope.chat_id,
                raw_text=envelope.raw_text,
                command="status" if text == "/status" else "start",
            )
        if self.trade_style_setup_service is not None and (
            text.startswith("/trade-style") or self.trade_style_setup_service.has_pending_session(user_id=envelope.user_id)
        ):
            return self._handle_trade_style(envelope)
        if self.follow_command_service is not None and (
            text.startswith("/follow")
            or (
                self.follow_command_service.has_pending_confirmation(user_id=envelope.user_id)
                and text.lower() in {"yes", "y", "no", "n"}
            )
        ):
            return self._handle_follow(envelope)
        if text.startswith("/stop "):
            return self._handle_stop(envelope)
        if text == "/portfolio":
            return self._handle_wallet_command(envelope, command_name="portfolio")
        if text.startswith("/history"):
            return self._handle_wallet_command(envelope, command_name="history")
        return CommandResponse(ok=False, command="status", message="Unsupported command.", payload={})

    def _handle_trade_style(self, envelope: CommandEnvelope) -> CommandResponse:
        if self.trade_style_setup_service is None:
            return CommandResponse(ok=False, command="trade-style", message="Trade-style service is not configured.", payload={})
        return self.trade_style_setup_service.handle(
            user_id=envelope.user_id,
            chat_id=envelope.chat_id,
            raw_text=envelope.raw_text,
        )

    def _handle_follow(self, envelope: CommandEnvelope) -> CommandResponse:
        if self.follow_command_service is None:
            return CommandResponse(ok=False, command="follow", message="Follow service is not configured.", payload={})
        return self.follow_command_service.handle(
            user_id=envelope.user_id,
            chat_id=envelope.chat_id,
            raw_text=envelope.raw_text,
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
