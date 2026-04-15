from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.adapters.scraper.client import ScraperClient, ScraperHistoricalProfileRequest
from app.agents.follow_profiling import FollowProfilingAgent
from app.persistence.repositories import FollowedSourceRecord, FollowedSourceRepository, utc_now_iso
from app.schemas.commands import CommandResponse
from app.schemas.webhook import ScraperFollowProfileWebhookPayload
from app.services.notifications import NotificationService
from app.services.source_registry import SourceRegistryService


def normalize_channel_name(raw: str) -> str:
    text = raw.strip()
    if text.startswith("https://t.me/"):
        text = text.removeprefix("https://t.me/")
    if text.startswith("t.me/"):
        text = text.removeprefix("t.me/")
    return text.lstrip("@").strip().rstrip("/")


@dataclass(frozen=True)
class FollowProfileAccepted:
    source_id: str
    channel_name: str
    suggested_conviction: str
    status: str


class FollowCommandService:
    def __init__(
        self,
        *,
        repository: FollowedSourceRepository,
        scraper_client: ScraperClient,
        source_registry: SourceRegistryService,
        profiling_agent: FollowProfilingAgent,
        notification_service: NotificationService | None,
        callback_url: str,
        callback_secret: str,
    ) -> None:
        self.repository = repository
        self.scraper_client = scraper_client
        self.source_registry = source_registry
        self.profiling_agent = profiling_agent
        self.notification_service = notification_service
        self.callback_url = callback_url
        self.callback_secret = callback_secret

    def has_pending_confirmation(self, *, user_id: str) -> bool:
        return self.repository.get_pending_confirmation(user_id) is not None

    def handle(self, *, user_id: str, chat_id: str, raw_text: str) -> CommandResponse:
        text = raw_text.strip()
        lowered = text.lower()

        if lowered in {"yes", "y", "no", "n"} and self.has_pending_confirmation(user_id=user_id):
            pending = self.repository.get_pending_confirmation(user_id)
            if pending is None:
                return CommandResponse(ok=False, command="follow", message="No pending follow confirmation.", payload={})
            if lowered in {"yes", "y"}:
                return self._confirm_follow(record=pending)
            return self._cancel_follow(record=pending)

        if lowered.startswith("/follow confirm "):
            channel_name = normalize_channel_name(text.removeprefix("/follow confirm "))
            record = self.repository.get_by_channel_name(user_id, channel_name)
            if record is None:
                return CommandResponse(ok=False, command="follow", message="No pending follow request found.", payload={})
            return self._confirm_follow(record=record)

        if lowered.startswith("/follow cancel "):
            channel_name = normalize_channel_name(text.removeprefix("/follow cancel "))
            record = self.repository.get_by_channel_name(user_id, channel_name)
            if record is None:
                return CommandResponse(ok=False, command="follow", message="No pending follow request found.", payload={})
            return self._cancel_follow(record=record)

        channel_name = normalize_channel_name(text.removeprefix("/follow"))
        if not channel_name:
            return CommandResponse(ok=False, command="follow", message="Please provide a Telegram channel name.", payload={})

        source_id = f"{user_id}:{channel_name}"
        record = self.repository.get_by_source_id(source_id) or FollowedSourceRecord(
            source_id=source_id,
            user_id=user_id,
            channel_name=channel_name,
            channel_url=f"https://t.me/{channel_name}",
            chat_id=chat_id,
            status="profiling_pending",
        )
        record.chat_id = chat_id
        record.status = "profiling_pending"
        record.last_profile_requested_at = utc_now_iso()

        request = ScraperHistoricalProfileRequest(
            source_id=source_id,
            channel_name=channel_name,
            channel_url=record.channel_url,
            callback_url=self.callback_url,
            callback_secret=self.callback_secret,
            user_id=user_id,
            lookback_days=7,
        )
        response = self.scraper_client.request_channel_profile(request)
        record.profile_job_id = response.get("profile_job_id")
        record.status = "profiling_pending" if response.get("ok") else "profiling_failed"
        self.repository.save(record)
        return CommandResponse(
            ok=bool(response.get("ok")),
            command="follow",
            message=(
                (
                    f"Started profiling `{channel_name}` over the last 7 days. "
                    "I will send you a retrospective summary and ask for confirmation before live follow."
                )
                if response.get("ok")
                else str(response.get("message") or "Scraper profiling is unavailable.")
            ),
            payload={
                "source_id": source_id,
                "channel_name": channel_name,
                "status": record.status,
                "profile_job_id": record.profile_job_id,
            },
        )

    def accept_profile_callback(self, payload: ScraperFollowProfileWebhookPayload) -> FollowProfileAccepted:
        record = self.repository.get_by_source_id(payload.source_id) or FollowedSourceRecord(
            source_id=payload.source_id,
            user_id=payload.user_id,
            channel_name=payload.channel_name,
            channel_url=payload.channel_url,
            status="profiling_pending",
        )
        profile = self.profiling_agent.profile(
            user_id=payload.user_id,
            source_id=payload.source_id,
            channel_name=payload.channel_name,
            messages=[message.model_dump() for message in payload.messages],
        )
        record.channel_url = payload.channel_url
        record.profile_job_id = payload.profile_job_id
        record.status = "awaiting_confirmation"
        record.suggested_conviction = str(profile.get("suggested_conviction"))
        record.profile_summary = profile
        record.profiled_at = utc_now_iso()
        saved = self.repository.save(record)

        if self.notification_service is not None and saved.chat_id is not None:
            self.notification_service.send_generic_notification(
                user_id=saved.user_id,
                chat_id=saved.chat_id,
                notification_type="follow_profile_ready",
                message_text=self._format_profile_message(saved),
                explanation_payload=saved.profile_summary,
            )

        return FollowProfileAccepted(
            source_id=saved.source_id,
            channel_name=saved.channel_name,
            suggested_conviction=saved.suggested_conviction or "unknown",
            status=saved.status,
        )

    def _confirm_follow(self, *, record: FollowedSourceRecord) -> CommandResponse:
        saved = self.source_registry.register_existing(
            record=record,
            callback_url=self.callback_url.replace("/follow-profile", "/messages"),
            callback_secret=self.callback_secret,
        )
        return CommandResponse(
            ok=saved.status == "active",
            command="follow",
            message=(
                f"Following `{saved.channel_name}` is now active.\n"
                f"Conviction: {saved.suggested_conviction or 'n/a'}"
            ),
            payload={
                "source_id": saved.source_id,
                "channel_name": saved.channel_name,
                "status": saved.status,
                "scraper_subscription_id": saved.scraper_subscription_id,
                "suggested_conviction": saved.suggested_conviction,
            },
        )

    def _cancel_follow(self, *, record: FollowedSourceRecord) -> CommandResponse:
        record.status = "inactive"
        saved = self.repository.save(record)
        return CommandResponse(
            ok=True,
            command="follow",
            message=f"Cancelled follow request for `{saved.channel_name}`.",
            payload={
                "source_id": saved.source_id,
                "channel_name": saved.channel_name,
                "status": saved.status,
            },
        )

    def _format_profile_message(self, record: FollowedSourceRecord) -> str:
        profile = record.profile_summary or {}
        patterns = profile.get("notable_patterns") or []
        pattern_breakdown = profile.get("pattern_breakdown") or []
        lines = [
            "📊 Follow Profile Ready",
            "",
            f"Channel: `{record.channel_name}`",
            f"Suggested Conviction: `{record.suggested_conviction or 'n/a'}`",
            "",
            "Retrospective Metrics",
            f"- Extracted calls: `{profile.get('extracted_call_count', 'n/a')}`",
            f"- Evaluated calls: `{profile.get('evaluated_call_count', 'n/a')}`",
            f"- 1D win rate: `{profile.get('win_rate_1d_pct', 'n/a')}%`",
            f"- Median 1D return: `{profile.get('median_return_1d_pct', 'n/a')}%`",
            f"- Average 1D return: `{profile.get('average_return_1d_pct', 'n/a')}%`",
        ]
        if profile.get("biggest_win_symbol") is not None or profile.get("biggest_win_return_pct") is not None:
            lines.append(
                f"- Biggest winner: `{profile.get('biggest_win_symbol', 'n/a')}` "
                f"(`{profile.get('biggest_win_return_pct', 'n/a')}%`)"
            )
        summary = str(profile.get("profiling_summary", "")).strip()
        if summary:
            lines.extend(["", "Summary", summary])
        long_message = str(profile.get("user_message_long", "")).strip()
        if long_message:
            lines.extend(["", "Analysis", long_message])
        if profile.get("major_asset_bias") or profile.get("regular_token_bias"):
            lines.extend(["", "Asset Bias"])
            if profile.get("major_asset_bias"):
                lines.append(f"- Majors: {profile.get('major_asset_bias')}")
            if profile.get("regular_token_bias"):
                lines.append(f"- Regular tokens: {profile.get('regular_token_bias')}")
        if patterns:
            lines.extend(["", "Patterns"] + [f"- {pattern}" for pattern in patterns])
        if pattern_breakdown:
            lines.extend(["", "Pattern Breakdown"] + [f"- {pattern}" for pattern in pattern_breakdown])
        lines.extend(
            [
                "",
                "Reply `yes` to start live follow.",
                "Reply `no` to cancel.",
            ]
        )
        return "\n".join(lines)
