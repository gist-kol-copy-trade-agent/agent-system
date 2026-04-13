from dataclasses import dataclass
from typing import Protocol


@dataclass
class ToolResult:
    ok: bool
    payload: dict
    error_code: str | None = None
    error_message: str | None = None


class WalletContextTool(Protocol):
    def __call__(self, *, chain: str) -> ToolResult: ...


class TokenRiskTool(Protocol):
    def __call__(self, *, chain: str, token_contract_address: str) -> ToolResult: ...


class MarketSnapshotTool(Protocol):
    def __call__(self, *, chain: str, token_contract_address: str) -> ToolResult: ...
