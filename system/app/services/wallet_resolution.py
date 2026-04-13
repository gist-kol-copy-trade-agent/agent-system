from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.persistence.repositories import WalletSessionRecord, WalletSessionRepository


EVM_CHAINS = {
    "1",
    "10",
    "56",
    "137",
    "8453",
    "42161",
    "43114",
    "ethereum",
    "eth",
    "optimism",
    "op",
    "bsc",
    "bnb",
    "polygon",
    "matic",
    "base",
    "arbitrum",
    "arb",
    "avalanche",
    "avax",
    "linea",
    "scroll",
    "zksync",
    "fantom",
    "ftm",
}
SOLANA_CHAINS = {"501", "solana", "sol"}
XLAYER_CHAINS = {"196", "xlayer", "okb"}


@dataclass(frozen=True)
class WalletAddressResolution:
    chain: str
    chain_type: str
    wallet_address: str | None
    logged_in: bool
    account_id: str | None
    source: str

    def to_prompt_hints(self) -> dict[str, Any]:
        return {
            "target_chain": self.chain,
            "chain_type": self.chain_type,
            "resolved_wallet_address": self.wallet_address,
            "wallet_resolution_source": self.source,
            "wallet_logged_in": self.logged_in,
            "account_id": self.account_id,
        }


class WalletAddressResolver:
    def __init__(self, repository: WalletSessionRepository | None = None) -> None:
        self.repository = repository

    def resolve_wallet_address_for_chain(self, *, user_id: str, chain: str) -> WalletAddressResolution:
        session = self._get_session(user_id)
        chain_key = self._normalize_chain(chain)
        chain_type = self._infer_chain_type(chain_key)
        wallet_address = self._resolve_from_session(session=session, chain_type=chain_type)
        source = "wallet_session" if wallet_address is not None else "unresolved"
        return WalletAddressResolution(
            chain=chain_key,
            chain_type=chain_type,
            wallet_address=wallet_address,
            logged_in=bool(session.logged_in) if session is not None else False,
            account_id=session.account_id if session is not None else None,
            source=source,
        )

    def get_wallet_hints(self, *, user_id: str) -> dict[str, Any]:
        session = self._get_session(user_id)
        if session is None:
            return {
                "logged_in": False,
                "account_id": None,
                "wallet_evm_address": None,
                "wallet_sol_address": None,
                "wallet_xlayer_address": None,
            }
        return {
            "logged_in": bool(session.logged_in),
            "account_id": session.account_id,
            "wallet_evm_address": session.wallet_evm_address,
            "wallet_sol_address": session.wallet_sol_address,
            "wallet_xlayer_address": session.wallet_xlayer_address,
        }

    def _get_session(self, user_id: str) -> WalletSessionRecord | None:
        if self.repository is None:
            return None
        return self.repository.get(user_id)

    @staticmethod
    def _normalize_chain(chain: str | None) -> str:
        if chain is None:
            return "unknown"
        return str(chain).strip().lower()

    @staticmethod
    def _infer_chain_type(chain: str) -> str:
        if chain in XLAYER_CHAINS:
            return "xlayer"
        if chain in SOLANA_CHAINS:
            return "solana"
        if chain in EVM_CHAINS:
            return "evm"
        if chain.isdigit():
            if chain in XLAYER_CHAINS:
                return "xlayer"
            if chain in SOLANA_CHAINS:
                return "solana"
            return "evm"
        return "evm"

    @staticmethod
    def _resolve_from_session(*, session: WalletSessionRecord | None, chain_type: str) -> str | None:
        if session is None:
            return None
        if chain_type == "xlayer":
            return session.wallet_xlayer_address or session.wallet_evm_address
        if chain_type == "solana":
            return session.wallet_sol_address
        return session.wallet_evm_address

