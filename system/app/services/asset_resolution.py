from __future__ import annotations

from dataclasses import dataclass
import re
import shlex
from typing import Any

from app.services.onchainos_runner import OnchainOSCommandError, OnchainOSReadonlyRunner


@dataclass(frozen=True)
class MajorAssetMapping:
    symbol: str
    target_chain: str
    execution_token: str
    token_name: str
    decimals: int


@dataclass(frozen=True)
class RegularResolutionResult:
    status: str
    normalized_symbol: str
    resolved_chain: str | None
    token_contract_address: str | None
    token_name: str | None
    decimals: int | None
    confidence: float
    reason_code: str | None = None


class MajorAssetRegistry:
    """Product-approved major asset mapping for the X Layer lane.

    The values here are treated as explicit execution identifiers rather than
    raw parser symbols, so the execution path does not rely on bare ticker
    strings alone.
    """

    _MAPPINGS: dict[str, MajorAssetMapping] = {
        "BTC": MajorAssetMapping(
            symbol="BTC",
            target_chain="xlayer",
            execution_token="xlayer:WBTC",
            token_name="Wrapped Bitcoin",
            decimals=8,
        ),
        "ETH": MajorAssetMapping(
            symbol="ETH",
            target_chain="xlayer",
            execution_token="xlayer:WETH",
            token_name="Wrapped Ether",
            decimals=18,
        ),
        "SOL": MajorAssetMapping(
            symbol="SOL",
            target_chain="xlayer",
            execution_token="xlayer:SOL",
            token_name="Wrapped Solana",
            decimals=9,
        ),
    }

    def get(self, symbol: str) -> MajorAssetMapping | None:
        return self._MAPPINGS.get(symbol.upper().strip())


class AssetResolver:
    _EVM_ADDRESS_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")

    def __init__(self, readonly_runner: OnchainOSReadonlyRunner | None = None) -> None:
        self.readonly_runner = readonly_runner or OnchainOSReadonlyRunner()

    def resolve_regular(self, parsed_signal: dict[str, Any]) -> RegularResolutionResult:
        resolved_chain = self._normalize_chain(
            parsed_signal.get("resolved_chain") or parsed_signal.get("raw_chain_hint")
        )
        contract_address = self._normalize_contract(
            parsed_signal.get("resolved_contract_address") or parsed_signal.get("raw_contract_address")
        )
        normalized_symbol = (
            str(
                parsed_signal.get("resolved_symbol")
                or parsed_signal.get("raw_symbol")
                or "UNKNOWN"
            )
            .strip()
            .upper()
        )

        if contract_address and resolved_chain:
            return RegularResolutionResult(
                status="resolved",
                normalized_symbol=normalized_symbol,
                resolved_chain=resolved_chain,
                token_contract_address=contract_address,
                token_name=parsed_signal.get("resolved_token_name"),
                decimals=parsed_signal.get("resolved_decimals"),
                confidence=float(parsed_signal.get("confidence") or 0.0),
            )

        if contract_address and not resolved_chain:
            return RegularResolutionResult(
                status="ambiguous",
                normalized_symbol=normalized_symbol,
                resolved_chain=None,
                token_contract_address=contract_address,
                token_name=parsed_signal.get("resolved_token_name"),
                decimals=parsed_signal.get("resolved_decimals"),
                confidence=float(parsed_signal.get("confidence") or 0.0),
                reason_code="TOKEN_AMBIGUOUS",
            )

        if normalized_symbol != "UNKNOWN" and resolved_chain:
            searched = self._search_token_candidates(query=normalized_symbol, chain=resolved_chain)
            if searched is not None:
                if len(searched) == 1:
                    return searched[0]
                if len(searched) > 1:
                    return RegularResolutionResult(
                        status="ambiguous",
                        normalized_symbol=normalized_symbol,
                        resolved_chain=resolved_chain,
                        token_contract_address=None,
                        token_name=None,
                        decimals=None,
                        confidence=float(parsed_signal.get("confidence") or 0.0),
                        reason_code="TOKEN_AMBIGUOUS",
                    )

        if normalized_symbol != "UNKNOWN":
            return RegularResolutionResult(
                status="ambiguous",
                normalized_symbol=normalized_symbol,
                resolved_chain=resolved_chain,
                token_contract_address=None,
                token_name=parsed_signal.get("resolved_token_name"),
                decimals=parsed_signal.get("resolved_decimals"),
                confidence=float(parsed_signal.get("confidence") or 0.0),
                reason_code="TOKEN_AMBIGUOUS",
            )

        return RegularResolutionResult(
            status="unresolved",
            normalized_symbol="UNKNOWN",
            resolved_chain=resolved_chain,
            token_contract_address=None,
            token_name=None,
            decimals=None,
            confidence=float(parsed_signal.get("confidence") or 0.0),
            reason_code="TOKEN_UNRESOLVED",
        )

    @staticmethod
    def parse_reference_price(parsed_signal: dict[str, Any]) -> float | None:
        entry_text = str(parsed_signal.get("entry_reference_text") or "").strip().lower()
        if not entry_text:
            return None

        range_match = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:-|to)\s*(\d+(?:[.,]\d+)?)", entry_text)
        if range_match:
            low = float(range_match.group(1).replace(",", ""))
            high = float(range_match.group(2).replace(",", ""))
            if low > 0 and high > 0:
                return (low + high) / 2

        anchored_match = re.search(
            r"(?:entry|buy(?:ing)?|around|at)\s*(?:price\s*)?(?:around\s*)?(\d+(?:[.,]\d+)?)",
            entry_text,
        )
        if anchored_match:
            return float(anchored_match.group(1).replace(",", ""))

        standalone_numbers = re.findall(r"(\d+(?:[.,]\d+)?)", entry_text)
        for match in standalone_numbers:
            value = float(match.replace(",", ""))
            if value > 0:
                return value
        return None

    def _search_token_candidates(self, *, query: str, chain: str) -> list[RegularResolutionResult] | None:
        command = f"onchainos token search --query {shlex.quote(query)} --chains {shlex.quote(chain)}"
        try:
            result = self.readonly_runner.run(command)
        except OnchainOSCommandError:
            return None
        if not result.get("ok"):
            return None

        payload = result.get("payload")
        rows = self._extract_rows(payload)
        resolved_rows: list[RegularResolutionResult] = []
        for row in rows:
            symbol = str(row.get("symbol") or row.get("tokenSymbol") or query).upper()
            address = self._normalize_contract(
                row.get("tokenContractAddress") or row.get("address") or row.get("tokenAddress")
            )
            row_chain = self._normalize_chain(row.get("chain") or row.get("chainName") or row.get("chain_id") or chain)
            decimals_raw = row.get("decimals") or row.get("decimal")
            decimals = None
            try:
                decimals = int(decimals_raw) if decimals_raw is not None else None
            except (TypeError, ValueError):
                decimals = None
            if address and row_chain == chain:
                resolved_rows.append(
                    RegularResolutionResult(
                        status="resolved",
                        normalized_symbol=symbol,
                        resolved_chain=row_chain,
                        token_contract_address=address,
                        token_name=row.get("tokenName") or row.get("name"),
                        decimals=decimals,
                        confidence=1.0,
                    )
                )
        deduped: dict[tuple[str, str], RegularResolutionResult] = {}
        for row in resolved_rows:
            deduped[(row.resolved_chain or "", row.token_contract_address or "")] = row
        return list(deduped.values())

    @staticmethod
    def _extract_rows(payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if not isinstance(payload, dict):
            return []
        data = payload.get("data", payload.get("rows", payload))
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        if isinstance(data, dict):
            for key in ("tokens", "rows", "list", "items"):
                value = data.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]
        return []

    @staticmethod
    def _normalize_chain(value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().lower()
        if not normalized:
            return None
        aliases = {
            "eth": "ethereum",
            "erc20": "ethereum",
            "sol": "solana",
            "xlayer": "xlayer",
            "x-layer": "xlayer",
        }
        return aliases.get(normalized, normalized)

    def _normalize_contract(self, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            return None
        if normalized.lower().startswith("0x") and self._EVM_ADDRESS_RE.match(normalized):
            return normalized.lower()
        return normalized
