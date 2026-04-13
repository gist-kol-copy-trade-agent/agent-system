from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from app.services.okx_skills import OKXSkillRegistry


@dataclass(frozen=True)
class ReadinessCheckResult:
    ok: bool
    checks: dict[str, dict[str, str | bool]]


class RuntimeReadinessService:
    def __init__(self, *, onchainos_binary: str = "onchainos", skill_registry: OKXSkillRegistry | None = None) -> None:
        self.onchainos_binary = onchainos_binary
        self.skill_registry = skill_registry or OKXSkillRegistry()

    def run(self) -> ReadinessCheckResult:
        binary_path = shutil.which(self.onchainos_binary)
        skills_root = self.skill_registry.root
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
        }
        ok = all(bool(check["ok"]) for check in checks.values())
        return ReadinessCheckResult(ok=ok, checks=checks)
