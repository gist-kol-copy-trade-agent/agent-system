from __future__ import annotations

from dataclasses import dataclass

from app.agents.wallet_agent import WalletAgent
from app.persistence.repositories import WalletSessionRecord, WalletSessionRepository, utc_now_iso
from app.schemas.commands import CommandResponse


@dataclass
class WalletService:
    agent: WalletAgent
    repository: WalletSessionRepository

    def handle(self, *, user_id: str, chat_id: str, raw_text: str, command: str = "start") -> CommandResponse:
        session = self.repository.get(user_id)
        phase = self._resolve_phase(session, raw_text)
        locale = self._infer_locale(raw_text)
        result = self.agent.handle(user_id=user_id, raw_text=raw_text, phase=phase, locale=locale)
        updated = self._persist_result(
            user_id=user_id,
            chat_id=chat_id,
            current=session,
            result=result.model_dump(),
        )
        return CommandResponse(ok=True, command=command, message=result.message, payload={**result.payload, "phase": updated.onboarding_phase})

    def has_pending_session(self, *, user_id: str) -> bool:
        session = self.repository.get(user_id)
        return bool(session and session.onboarding_phase in {"awaiting_email", "awaiting_otp"})

    @staticmethod
    def _resolve_phase(session: WalletSessionRecord | None, raw_text: str) -> str:
        if raw_text.strip() == "/status":
            return "status"
        if raw_text.strip() == "/start":
            return "start"
        if session and session.onboarding_phase in {"awaiting_email", "awaiting_otp"}:
            return session.onboarding_phase
        return "start"

    def _persist_result(
        self,
        *,
        user_id: str,
        chat_id: str,
        current: WalletSessionRecord | None,
        result: dict,
    ) -> WalletSessionRecord:
        payload = result.get("payload") or {}
        logged_in = bool(payload.get("logged_in", current.logged_in if current else False))
        policy = dict((current.policy if current else {}) or {})
        phase = result.get("phase")
        if phase == "status":
            phase = "status"
        elif logged_in:
            phase = "ready"
        record = WalletSessionRecord(
            user_id=user_id,
            logged_in=logged_in,
            account_id=payload.get("account_id", current.account_id if current else None),
            account_name=payload.get("account_name", current.account_name if current else None),
            login_type=payload.get("login_type", current.login_type if current else None),
            wallet_evm_address=payload.get("wallet_evm_address", current.wallet_evm_address if current else None),
            wallet_sol_address=payload.get("wallet_sol_address", current.wallet_sol_address if current else None),
            wallet_xlayer_address=payload.get("wallet_xlayer_address", current.wallet_xlayer_address if current else None),
            policy=policy,
            onboarding_phase=phase,
            onboarding_email=payload.get("email", current.onboarding_email if current else None),
            chat_id=chat_id,
            last_synced_at=utc_now_iso(),
        )
        return self.repository.save(record)

    @staticmethod
    def _infer_locale(raw_text: str) -> str:
        if any("\u4e00" <= ch <= "\u9fff" for ch in raw_text):
            return "zh-CN"
        if any("\u3040" <= ch <= "\u30ff" for ch in raw_text):
            return "ja-JP"
        return "en-US"
