from __future__ import annotations

import json
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class OnchainOSCommandError(Exception):
    pass


@dataclass(frozen=True)
class OnchainOSCommandResult:
    ok: bool
    command: list[str]
    exit_code: int
    payload: dict[str, Any] | list[Any] | None = None
    stdout: str | None = None
    stderr: str | None = None
    error: str | None = None

    def model_dump(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "command": self.command,
            "exit_code": self.exit_code,
            "payload": self.payload,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "error": self.error,
        }


class OnchainOSReadonlyRunner:
    READONLY_COMMANDS: dict[tuple[str, ...], set[str] | None] = {
        ("wallet",): {"status", "balance", "addresses", "chains", "history"},
        ("token",): {
            "search",
            "info",
            "price-info",
            "holders",
            "liquidity",
            "hot-tokens",
            "advanced-info",
            "top-trader",
            "trades",
            "cluster-overview",
            "cluster-top-holders",
            "cluster-list",
            "cluster-supported-chains",
        },
        ("market",): {
            "price",
            "prices",
            "kline",
            "index",
            "portfolio-supported-chains",
            "portfolio-dex-history",
            "portfolio-recent-pnl",
            "portfolio-token-pnl",
        },
        ("security",): {"token-scan", "dapp-scan", "tx-scan", "sig-scan", "approvals"},
        ("swap",): {"chains", "liquidity", "quote"},
        ("signal",): None,
        ("tracker",): None,
    }

    def __init__(self, *, binary: str = "onchainos", timeout_seconds: int = 30) -> None:
        self.binary = binary
        self.timeout_seconds = timeout_seconds

    def run(self, command: str) -> dict[str, Any]:
        argv = self._validate_and_split(command)
        completed = self._execute(argv)
        return completed.model_dump()

    def _validate_and_split(self, command: str) -> list[str]:
        if any(token in command for token in ["|", "&&", "||", ";", "$(", "`", ">", "<"]):
            raise OnchainOSCommandError("Shell operators are not allowed in onchainos commands.")

        argv = shlex.split(command)
        if not argv or argv[0] != self.binary:
            raise OnchainOSCommandError("Command must start with the onchainos binary.")
        if len(argv) < 3:
            raise OnchainOSCommandError("Incomplete onchainos command.")

        group = argv[1]
        action = argv[2]
        allowed_actions = self.READONLY_COMMANDS.get((group,))
        if allowed_actions is None and (group,) in self.READONLY_COMMANDS:
            return argv
        if allowed_actions is None or action not in allowed_actions:
            raise OnchainOSCommandError(f"Read-only execution is not allowed for: {group} {action}")
        return argv

    def _execute(self, argv: list[str]) -> OnchainOSCommandResult:
        try:
            completed = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
            )
        except FileNotFoundError as exc:
            raise OnchainOSCommandError(
                f"Could not find the onchainos binary '{self.binary}' in the server environment."
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise OnchainOSCommandError(f"onchainos command timed out after {self.timeout_seconds}s.") from exc

        stdout = (completed.stdout or "").strip()
        stderr = (completed.stderr or "").strip()
        payload: dict[str, Any] | list[Any] | None = None
        if stdout:
            try:
                payload = json.loads(stdout)
            except json.JSONDecodeError:
                payload = None

        ok = completed.returncode == 0
        return OnchainOSCommandResult(
            ok=ok,
            command=argv,
            exit_code=completed.returncode,
            payload=payload,
            stdout=stdout or None,
            stderr=stderr or None,
            error=None if ok else (stderr or f"onchainos exited with code {completed.returncode}"),
        )


class OnchainOSMutatingRunner:
    MUTATING_COMMANDS: dict[tuple[str, ...], set[str]] = {
        ("swap",): {"execute"},
        ("wallet",): {"login", "verify"},
    }

    def __init__(self, *, binary: str = "onchainos", timeout_seconds: int = 60) -> None:
        self.binary = binary
        self.timeout_seconds = timeout_seconds

    def run(self, command: str) -> dict[str, Any]:
        argv = self._validate_and_split(command)
        completed = self._execute(argv)
        return completed.model_dump()

    def _validate_and_split(self, command: str) -> list[str]:
        if any(token in command for token in ["|", "&&", "||", ";", "$(", "`", ">", "<"]):
            raise OnchainOSCommandError("Shell operators are not allowed in onchainos commands.")

        argv = shlex.split(command)
        if not argv or argv[0] != self.binary:
            raise OnchainOSCommandError("Command must start with the onchainos binary.")
        if len(argv) < 3:
            raise OnchainOSCommandError("Incomplete onchainos command.")

        group = argv[1]
        action = argv[2]
        allowed_actions = self.MUTATING_COMMANDS.get((group,))
        if allowed_actions is None or action not in allowed_actions:
            raise OnchainOSCommandError(f"Mutating execution is not allowed for: {group} {action}")
        return argv

    def _execute(self, argv: list[str]) -> OnchainOSCommandResult:
        try:
            completed = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
            )
        except FileNotFoundError as exc:
            raise OnchainOSCommandError(
                f"Could not find the onchainos binary '{self.binary}' in the server environment."
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise OnchainOSCommandError(f"onchainos command timed out after {self.timeout_seconds}s.") from exc

        stdout = (completed.stdout or "").strip()
        stderr = (completed.stderr or "").strip()
        payload: dict[str, Any] | list[Any] | None = None
        if stdout:
            try:
                payload = json.loads(stdout)
            except json.JSONDecodeError:
                payload = None

        ok = completed.returncode == 0
        return OnchainOSCommandResult(
            ok=ok,
            command=argv,
            exit_code=completed.returncode,
            payload=payload,
            stdout=stdout or None,
            stderr=stderr or None,
            error=None if ok else (stderr or f"onchainos exited with code {completed.returncode}"),
        )


class StubReadonlyRunner(OnchainOSReadonlyRunner):
    def __init__(self, responses: dict[str, dict[str, Any]] | None = None) -> None:
        super().__init__(binary="onchainos", timeout_seconds=1)
        self.responses = responses or {}

    def run(self, command: str) -> dict[str, Any]:
        self._validate_and_split(command)
        return self.responses.get(
            command,
            {
                "ok": False,
                "command": shlex.split(command),
                "exit_code": 1,
                "payload": None,
                "stdout": None,
                "stderr": None,
                "error": "stub response missing",
            },
        )
