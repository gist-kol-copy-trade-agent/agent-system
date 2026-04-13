from __future__ import annotations

from app.adapters.okx.base import OKXAdapter, OKXCommand, OKXCommandResult


class OKXMarketAdapter(OKXAdapter):
    def build_price_command(self, *, address: str, chain: str) -> OKXCommand:
        return OKXCommand(command="onchainos market price", arguments=["--address", address, "--chain", chain])

    def build_kline_command(self, *, address: str, chain: str) -> OKXCommand:
        return OKXCommand(command="onchainos market kline", arguments=["--address", address, "--chain", chain])

    def get_price(self, *, address: str, chain: str) -> OKXCommandResult:
        return self.run(self.build_price_command(address=address, chain=chain))

    def get_kline(self, *, address: str, chain: str) -> OKXCommandResult:
        return self.run(self.build_kline_command(address=address, chain=chain))
