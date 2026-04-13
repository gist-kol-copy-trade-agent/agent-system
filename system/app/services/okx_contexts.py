from __future__ import annotations

from app.adapters.okx.market import OKXMarketAdapter
from app.adapters.okx.security import OKXSecurityAdapter
from app.adapters.okx.swap import OKXSwapAdapter
from app.adapters.okx.token import OKXTokenAdapter
from app.adapters.okx.wallet import OKXWalletAdapter
from app.services.okx_normalizers import normalize_market_snapshot, normalize_risk_snapshot, normalize_wallet_snapshot


class OKXContextService:
    def __init__(
        self,
        *,
        wallet_adapter: OKXWalletAdapter,
        market_adapter: OKXMarketAdapter,
        token_adapter: OKXTokenAdapter,
        security_adapter: OKXSecurityAdapter,
        swap_adapter: OKXSwapAdapter,
    ) -> None:
        self.wallet_adapter = wallet_adapter
        self.market_adapter = market_adapter
        self.token_adapter = token_adapter
        self.security_adapter = security_adapter
        self.swap_adapter = swap_adapter

    def load_wallet_snapshot(self, *, chain: str):
        status = self.wallet_adapter.get_status()
        balance = self.wallet_adapter.get_balance(chain=chain)
        addresses = self.wallet_adapter.get_addresses(chain=chain)
        return normalize_wallet_snapshot(
            chain=chain,
            status_payload=status.payload,
            balance_payload=balance.payload,
            addresses_payload=addresses.payload,
        )

    def load_market_snapshot(
        self,
        *,
        asset_lane: str,
        chain: str,
        token_address: str,
        from_token: str,
        readable_amount: str,
    ):
        price = self.market_adapter.get_price(address=token_address, chain=chain)
        price_info = self.token_adapter.get_price_info(address=token_address) if asset_lane == "regular" else None
        kline = self.market_adapter.get_kline(address=token_address, chain=chain)
        quote = self.swap_adapter.get_quote(
            from_token=from_token,
            to_token=token_address,
            readable_amount=readable_amount,
            chain=chain,
        )
        return normalize_market_snapshot(
            asset_lane=asset_lane,
            chain=chain,
            price_payload=price.payload,
            price_info_payload=price_info.payload if price_info else None,
            kline_payload=kline.payload,
            quote_payload=quote.payload,
        )

    def load_risk_snapshot(self, *, asset_lane: str, chain: str, token_address: str):
        if asset_lane == "major":
            return normalize_risk_snapshot(asset_lane=asset_lane, security_payload=None, advanced_info_payload=None)

        security = self.security_adapter.get_token_scan(chain=chain, token_contract_address=token_address)
        advanced = self.token_adapter.get_advanced_info(address=token_address)
        return normalize_risk_snapshot(
            asset_lane=asset_lane,
            security_payload=security.payload,
            advanced_info_payload=advanced.payload,
        )
