from __future__ import annotations

from app.adapters.okx.base import OKXAdapter, OKXCommand, OKXCommandResult


class OKXSecurityAdapter(OKXAdapter):
    def build_token_scan_command(self, *, chain: str, token_contract_address: str) -> OKXCommand:
        token_arg = f"{chain}:{token_contract_address}"
        return OKXCommand(command="onchainos security token-scan", arguments=["--tokens", token_arg])

    def get_token_scan(self, *, chain: str, token_contract_address: str) -> OKXCommandResult:
        return self.run(self.build_token_scan_command(chain=chain, token_contract_address=token_contract_address))
