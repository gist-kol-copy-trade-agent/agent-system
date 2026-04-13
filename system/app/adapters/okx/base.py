from dataclasses import dataclass


@dataclass
class OKXCommand:
    command: str
    arguments: list[str]


class OKXAdapterError(Exception):
    pass


class OKXAdapter:
    """Base adapter boundary for OKX skill invocations."""

    def run(self, command: OKXCommand) -> dict:
        raise NotImplementedError("OKX command execution is implemented in a later phase.")
