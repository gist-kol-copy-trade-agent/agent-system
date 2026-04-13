from __future__ import annotations

from app.schemas.commands import CommandEnvelope, CommandResponse
from app.services.source_registry import SourceRegistryService
from app.services.strategy_profiles import StrategyProfileService


class TelegramCommandRouter:
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

    def handle(self, envelope: CommandEnvelope) -> CommandResponse:
        text = envelope.raw_text.strip()
        if text.startswith("/trade-style"):
            return self._handle_trade_style(envelope)
        if text.startswith("/follow "):
            return self._handle_follow(envelope)
        if text.startswith("/stop "):
            return self._handle_stop(envelope)
        if text == "/status":
            return CommandResponse(ok=True, command="status", message="System scaffold is online.", payload={})
        if text == "/start":
            profile = self.strategy_profiles.get_or_create(envelope.user_id)
            return CommandResponse(
                ok=True,
                command="start",
                message="Wallet/bootstrap readiness scaffold initialized.",
                payload={"strategy_profile_exists": profile is not None, "base_style": profile.base_style},
            )
        if text == "/portfolio":
            return CommandResponse(ok=True, command="portfolio", message="Portfolio read model is pending later phases.", payload={})
        if text.startswith("/history"):
            return CommandResponse(ok=True, command="history", message="History read model is pending later phases.", payload={})
        return CommandResponse(ok=False, command="status", message="Unsupported command.", payload={})

    def _handle_trade_style(self, envelope: CommandEnvelope) -> CommandResponse:
        preset, patch = self.strategy_profiles.parse_trade_style_text(envelope.raw_text)
        if preset:
            profile = self.strategy_profiles.apply_preset(user_id=envelope.user_id, base_style=preset, updated_by="user")
            return CommandResponse(
                ok=True,
                command="trade-style",
                message=f"Trading style updated to {profile.base_style}.",
                payload=profile.model_dump(),
            )

        if patch:
            profile = self.strategy_profiles.apply_patch(user_id=envelope.user_id, patch=patch, updated_by="user")
            return CommandResponse(
                ok=True,
                command="trade-style",
                message="Trading style overrides updated.",
                payload=profile.model_dump(),
            )

        profile = self.strategy_profiles.get_or_create(envelope.user_id)
        return CommandResponse(
            ok=True,
            command="trade-style",
            message="Current trading style profile.",
            payload=profile.model_dump(),
        )

    def _handle_follow(self, envelope: CommandEnvelope) -> CommandResponse:
        channel_name = envelope.raw_text.removeprefix("/follow").strip()
        record = self.source_registry.follow(
            user_id=envelope.user_id,
            channel_name=channel_name,
            channel_url=f"https://t.me/{channel_name}",
            callback_url=self.callback_url,
            callback_secret=self.callback_secret,
        )
        return CommandResponse(
            ok=True,
            command="follow",
            message=f"Source {record.channel_name} is {record.status}.",
            payload={
                "source_id": record.source_id,
                "channel_name": record.channel_name,
                "status": record.status,
                "scraper_subscription_id": record.scraper_subscription_id,
            },
        )

    def _handle_stop(self, envelope: CommandEnvelope) -> CommandResponse:
        channel_name = envelope.raw_text.removeprefix("/stop").strip()
        record = self.source_registry.stop(user_id=envelope.user_id, channel_name=channel_name)
        return CommandResponse(
            ok=True,
            command="stop",
            message=f"Source {record.channel_name} is {record.status}.",
            payload={
                "source_id": record.source_id,
                "channel_name": record.channel_name,
                "status": record.status,
            },
        )
