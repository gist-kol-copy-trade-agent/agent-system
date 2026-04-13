from __future__ import annotations

from dataclasses import dataclass

from app.agents.trade_style_override import TradeStyleOverrideAgent
from app.persistence.repositories import StrategyProfileSessionRecord, StrategyProfileSessionRepository
from app.schemas.commands import CommandResponse
from app.schemas.strategy import TradingStyle, UserStrategyProfile
from app.services.strategy_profiles import StrategyProfileService


STYLE_CHOICES: set[str] = {"safe", "normal", "degen"}


@dataclass
class TradeStyleSetupService:
    strategy_profiles: StrategyProfileService
    repository: StrategyProfileSessionRepository
    override_agent: TradeStyleOverrideAgent | None = None

    def has_pending_session(self, *, user_id: str) -> bool:
        session = self.repository.get(user_id)
        return bool(session and session.status in {"awaiting_base_style", "awaiting_override_or_confirm"})

    def handle(self, *, user_id: str, chat_id: str, raw_text: str) -> CommandResponse:
        text = raw_text.strip()
        normalized = text.lower()
        session = self.repository.get(user_id)

        if normalized == "/trade-style":
            current = self.strategy_profiles.get_or_create(user_id)
            self.repository.save(
                StrategyProfileSessionRecord(
                    user_id=user_id,
                    chat_id=chat_id,
                    status="awaiting_base_style",
                )
            )
            return CommandResponse(
                ok=True,
                command="trade-style",
                message=self._render_choose_style(current),
                payload={"phase": "awaiting_base_style", "current_profile": current.model_dump()},
            )

        preset, patch = self.strategy_profiles.parse_trade_style_text(text)

        if preset is not None:
            draft = self.strategy_profiles.build_preset_profile(user_id=user_id, base_style=preset, updated_by="user")
            self.repository.save(
                StrategyProfileSessionRecord(
                    user_id=user_id,
                    chat_id=chat_id,
                    status="awaiting_override_or_confirm",
                    selected_base_style=preset,
                    draft_profile=draft.model_dump(),
                )
            )
            return CommandResponse(
                ok=True,
                command="trade-style",
                message=self._render_draft(draft),
                payload={"phase": "awaiting_override_or_confirm", "draft_profile": draft.model_dump()},
            )

        if session is None or session.status not in {"awaiting_base_style", "awaiting_override_or_confirm"}:
            return CommandResponse(
                ok=False,
                command="trade-style",
                message="Start with `/trade-style`, then choose `safe`, `normal`, or `degen`.",
                payload={},
            )

        if normalized == "cancel":
            self.repository.clear(user_id)
            return CommandResponse(
                ok=True,
                command="trade-style",
                message="Trade-style setup cancelled. Your saved profile was not changed.",
                payload={"phase": "cancelled"},
            )

        if session.status == "awaiting_base_style":
            return CommandResponse(
                ok=False,
                command="trade-style",
                message="Choose one style first: `safe`, `normal`, or `degen`.",
                payload={"phase": "awaiting_base_style"},
            )

        draft = UserStrategyProfile(**(session.draft_profile or self.strategy_profiles.get_or_create(user_id).model_dump()))

        if normalized == "confirm":
            saved = self.strategy_profiles.save_profile(draft)
            self.repository.clear(user_id)
            return CommandResponse(
                ok=True,
                command="trade-style",
                message=self._render_saved(saved),
                payload={"phase": "ready", "profile": saved.model_dump()},
            )

        if patch is None:
            if self.override_agent is not None:
                parsed = self.override_agent.parse_override(raw_text=text, current_profile=draft.model_dump())
                patch = parsed.patch

        if patch is None or not patch.model_dump(exclude_none=True):
            return CommandResponse(
                ok=False,
                command="trade-style",
                message="Tell me what to change, or reply `confirm` to save this profile.",
                payload={"phase": "awaiting_override_or_confirm", "draft_profile": draft.model_dump()},
            )

        updated = self.strategy_profiles.merge_patch(profile=draft, patch=patch, updated_by="user")
        self.repository.save(
            StrategyProfileSessionRecord(
                user_id=user_id,
                chat_id=chat_id,
                status="awaiting_override_or_confirm",
                selected_base_style=updated.base_style,
                draft_profile=updated.model_dump(),
            )
        )
        return CommandResponse(
            ok=True,
            command="trade-style",
            message=self._render_draft(updated, changed_fields=list(patch.model_dump(exclude_none=True).keys())),
            payload={"phase": "awaiting_override_or_confirm", "draft_profile": updated.model_dump()},
        )

    @staticmethod
    def _render_choose_style(current: UserStrategyProfile) -> str:
        return (
            "🎛️ Trade Style Setup\n\n"
            "Choose your trading style:\n"
            "- `degen`\n"
            "- `normal`\n"
            "- `safe`\n\n"
            "Current profile:\n"
            f"- Style: `{current.base_style}`\n"
            f"- Max per trade: `${current.max_amount_per_trade_usd}`\n"
            f"- Active positions: `{current.max_active_positions}`"
        )

    @staticmethod
    def _render_draft(profile: UserStrategyProfile, *, changed_fields: list[str] | None = None) -> str:
        lines = [
            "📋 Proposed Trade Style",
            "",
            f"Style: `{profile.base_style}`",
            "",
            "Sizing",
            f"- Max per trade: `${profile.max_amount_per_trade_usd}`",
            f"- Major max: `${profile.major_asset_max_amount_usd}`",
            f"- Regular max: `${profile.regular_token_max_amount_usd}`",
            f"- Max active positions: `{profile.max_active_positions}`",
            "",
            "Entry Guards",
            f"- Major slippage: `{profile.max_slippage_pct_major}%`",
            f"- Regular slippage: `{profile.max_slippage_pct_regular}%`",
            f"- Major deviation: `{profile.max_price_deviation_pct_major}%`",
            f"- Regular deviation: `{profile.max_price_deviation_pct_regular}%`",
            f"- Regular min liquidity: `${profile.min_liquidity_usd_regular}`",
            "",
            "Exit Defaults",
            f"- Stop loss: `{profile.default_stop_loss_pct}%`",
            f"- Take profit: `{profile.default_take_profit_pct}%`",
            f"- Max holding time: `{profile.max_holding_time_hours}h`",
            "",
            "Lane Toggles",
            f"- Major lane: `{profile.major_asset_lane_enabled}`",
            f"- Regular lane: `{profile.regular_token_lane_enabled}`",
        ]
        if changed_fields:
            formatted = ", ".join(f"`{field}`" for field in changed_fields)
            lines.extend(["", f"Updated: {formatted}"])
        lines.extend(
            [
                "",
                "Reply `confirm` to save.",
                "Or type what you want to change next.",
            ]
        )
        return "\n".join(lines)

    @staticmethod
    def _render_saved(profile: UserStrategyProfile) -> str:
        return (
            "✅ Trade Style Saved\n\n"
            f"Style: `{profile.base_style}`\n"
            f"Max per trade: `${profile.max_amount_per_trade_usd}`\n"
            f"Major / Regular caps: `${profile.major_asset_max_amount_usd}` / `${profile.regular_token_max_amount_usd}`\n\n"
            "This profile will now be used globally for future trade decisions."
        )
