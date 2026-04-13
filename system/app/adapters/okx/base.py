from dataclasses import dataclass
from typing import Any


@dataclass
class OKXCommand:
    command: str
    arguments: list[str]


@dataclass
class OKXCommandResult:
    ok: bool
    command: OKXCommand
    payload: dict[str, Any]
    error_code: str | None = None
    error_message: str | None = None


class OKXAdapterError(Exception):
    pass


class OKXCommandRunner:
    """Boundary for executing built OKX commands."""

    def run(self, command: OKXCommand) -> OKXCommandResult:
        raise NotImplementedError("OKX command execution is implemented in a later phase.")


class OKXAdapter:
    """Base adapter boundary for OKX skill invocations."""

    def __init__(self, runner: OKXCommandRunner) -> None:
        self.runner = runner

    def run(self, command: OKXCommand) -> OKXCommandResult:
        return self.runner.run(command)
