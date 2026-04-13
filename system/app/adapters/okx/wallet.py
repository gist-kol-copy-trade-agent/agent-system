from __future__ import annotations

from app.adapters.okx.base import OKXAdapter, OKXCommand, OKXCommandResult


class OKXWalletAdapter(OKXAdapter):
    def build_status_command(self) -> OKXCommand:
        return OKXCommand(command="onchainos wallet status", arguments=[])

    def build_balance_command(self, *, chain: str) -> OKXCommand:
        return OKXCommand(command="onchainos wallet balance", arguments=["--chain", chain])

    def build_addresses_command(self, *, chain: str) -> OKXCommand:
        return OKXCommand(command="onchainos wallet addresses", arguments=["--chain", chain])

    def get_status(self) -> OKXCommandResult:
        return self.run(self.build_status_command())

    def get_balance(self, *, chain: str) -> OKXCommandResult:
        return self.run(self.build_balance_command(chain=chain))

    def get_addresses(self, *, chain: str) -> OKXCommandResult:
        return self.run(self.build_addresses_command(chain=chain))
