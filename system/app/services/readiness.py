from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from app.adapters.scraper.client import ScraperClient
from app.adapters.telegram.client import TelegramClient
from app.config.settings import get_settings
from app.services.onchainos_runner import OnchainOSReadonlyRunner
from app.services.okx_skills import OKXSkillRegistry


@dataclass(frozen=True)
class ReadinessCheckResult:
    ok: bool
    checks: dict[str, dict[str, str | bool]]


class RuntimeReadinessService:
    def __init__(
        self,
        *,
        onchainos_binary: str = "onchainos",
        skill_registry: OKXSkillRegistry | None = None,
        session_factory: sessionmaker[Session] | None = None,
        scraper_client: ScraperClient | None = None,
        telegram_client: TelegramClient | None = None,
    ) -> None:
        self.onchainos_binary = onchainos_binary
        self.skill_registry = skill_registry or OKXSkillRegistry()
        self.session_factory = session_factory
        self.scraper_client = scraper_client
        self.telegram_client = telegram_client
        self.readonly_runner = OnchainOSReadonlyRunner(binary=onchainos_binary, timeout_seconds=10)

    def run(self) -> ReadinessCheckResult:
        settings = get_settings()
        binary_path = shutil.which(self.onchainos_binary)
        skills_root = self.skill_registry.root
        db_ok, db_detail = self._check_database()
        checkpointer_ok, checkpointer_detail = self._check_checkpointer_backend()
        onchainos_probe_ok, onchainos_probe_detail = self._check_onchainos_readonly_probe(binary_path)
        scraper_reachability_ok, scraper_reachability_detail = self._check_scraper_reachability()
        wallet_sessions_ok, wallet_sessions_detail = self._check_wallet_sessions()
        openai_api_key = settings.openai.api_key or os.getenv("OPENAI_API_KEY")
        checks = {
            "onchainos_binary": {
                "ok": binary_path is not None,
                "detail": binary_path or f"{self.onchainos_binary} not found in PATH",
            },
            "skills_root": {
                "ok": Path(skills_root).exists(),
                "detail": str(skills_root),
            },
            "wallet_skill": {
                "ok": (Path(skills_root) / "okx-agentic-wallet" / "SKILL.md").exists(),
                "detail": str(Path(skills_root) / "okx-agentic-wallet" / "SKILL.md"),
            },
            "database": {
                "ok": db_ok,
                "detail": db_detail,
            },
            "langgraph_checkpointer": {
                "ok": checkpointer_ok,
                "detail": checkpointer_detail,
            },
            "onchainos_readonly_probe": {
                "ok": onchainos_probe_ok,
                "detail": onchainos_probe_detail,
            },
            "openai_api_key": {
                "ok": bool(openai_api_key),
                "detail": "configured" if openai_api_key else "missing OPENAI_API_KEY / OKX_AGENT_OPENAI__API_KEY",
            },
            "scraper_client": {
                "ok": settings.scraper.base_url is not None and settings.scraper.base_url.strip() != "",
                "detail": settings.scraper.base_url or "scraper base URL not configured",
            },
            "scraper_reachability": {
                "ok": scraper_reachability_ok,
                "detail": scraper_reachability_detail,
            },
            "telegram_client": {
                "ok": self.telegram_client is not None and self.telegram_client.__class__.__name__ != "UnconfiguredTelegramClient",
                "detail": self.telegram_client.__class__.__name__ if self.telegram_client is not None else "telegram client missing",
            },
            "wallet_sessions": {
                "ok": wallet_sessions_ok,
                "detail": wallet_sessions_detail,
            },
        }
        execution_stack_ready = all(
            (
                checks["onchainos_binary"]["ok"],
                checks["onchainos_readonly_probe"]["ok"],
                checks["database"]["ok"],
                checks["langgraph_checkpointer"]["ok"],
                checks["openai_api_key"]["ok"],
                checks["scraper_reachability"]["ok"],
                checks["telegram_client"]["ok"],
            )
        )
        checks["trading_runtime_ready"] = {
            "ok": bool(execution_stack_ready and checks["wallet_sessions"]["ok"]),
            "detail": (
                "execution stack configured and at least one logged-in wallet session is available"
                if execution_stack_ready and checks["wallet_sessions"]["ok"]
                else "missing one or more execution-critical prerequisites"
            ),
        }
        ok = all(bool(check["ok"]) for check in checks.values())
        return ReadinessCheckResult(ok=ok, checks=checks)

    def _check_database(self) -> tuple[bool, str]:
        if self.session_factory is None:
            return False, "session factory not configured"
        try:
            with self.session_factory() as session:
                session.execute(text("SELECT 1"))
            return True, "ok"
        except Exception as exc:  # pragma: no cover - integration check
            return False, str(exc)

    def _check_checkpointer_backend(self) -> tuple[bool, str]:
        settings = get_settings()
        backend = settings.langgraph.checkpointer_backend
        if backend == "memory":
            return True, "memory backend enabled"
        try:
            from langgraph.checkpoint.postgres import PostgresSaver  # noqa: F401
        except ModuleNotFoundError:
            return False, "postgres backend requested but langgraph-checkpoint-postgres is not installed"
        return True, "postgres checkpointer backend available"

    def _check_onchainos_readonly_probe(self, binary_path: str | None) -> tuple[bool, str]:
        if binary_path is None:
            return False, "onchainos binary unavailable"
        try:
            result = self.readonly_runner.run("onchainos swap chains")
        except Exception as exc:  # pragma: no cover - integration path
            return False, str(exc)
        return bool(result.get("ok")), str(result.get("error") or "ok")

    def _check_scraper_reachability(self) -> tuple[bool, str]:
        settings = get_settings()
        base_url = (settings.scraper.base_url or "").strip()
        if not base_url:
            return False, "scraper base URL not configured"
        try:
            with httpx.Client(base_url=base_url.rstrip("/"), timeout=settings.scraper.timeout_seconds) as client:
                response = client.get("/readiness")
                response.raise_for_status()
                payload = response.json()
        except Exception as exc:  # pragma: no cover - integration path
            return False, str(exc)
        return bool(payload.get("ok")), str(payload.get("checks") or payload)

    def _check_wallet_sessions(self) -> tuple[bool, str]:
        if self.session_factory is None:
            return False, "session factory not configured"
        try:
            with self.session_factory() as session:
                row = session.execute(
                    text(
                        """
                        SELECT
                            COUNT(*) AS total_count,
                            SUM(CASE WHEN logged_in = TRUE THEN 1 ELSE 0 END) AS logged_in_count,
                            SUM(
                                CASE
                                    WHEN logged_in = TRUE
                                     AND (wallet_xlayer_address IS NOT NULL OR wallet_evm_address IS NOT NULL OR wallet_sol_address IS NOT NULL)
                                    THEN 1
                                    ELSE 0
                                END
                            ) AS usable_wallet_count
                        FROM wallet_sessions
                        """
                    )
                ).mappings().one()
        except Exception as exc:  # pragma: no cover - integration path
            return False, str(exc)

        usable = int(row.get("usable_wallet_count") or 0)
        logged_in = int(row.get("logged_in_count") or 0)
        total = int(row.get("total_count") or 0)
        detail = f"total={total}, logged_in={logged_in}, usable={usable}"
        return usable > 0, detail
