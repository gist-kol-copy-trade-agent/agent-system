from __future__ import annotations

from app.adapters.okx.base import OKXAdapter, OKXCommand, OKXCommandResult


class OKXTokenAdapter(OKXAdapter):
    def build_search_command(self, *, query: str, chain: str) -> OKXCommand:
        return OKXCommand(command="onchainos token search", arguments=["--query", query, "--chains", chain])

    def build_price_info_command(self, *, address: str) -> OKXCommand:
        return OKXCommand(command="onchainos token price-info", arguments=["--address", address])

    def build_advanced_info_command(self, *, address: str) -> OKXCommand:
        return OKXCommand(command="onchainos token advanced-info", arguments=["--address", address])

    def search(self, *, query: str, chain: str) -> OKXCommandResult:
        return self.run(self.build_search_command(query=query, chain=chain))

    def get_price_info(self, *, address: str) -> OKXCommandResult:
        return self.run(self.build_price_info_command(address=address))

    def get_advanced_info(self, *, address: str) -> OKXCommandResult:
        return self.run(self.build_advanced_info_command(address=address))
