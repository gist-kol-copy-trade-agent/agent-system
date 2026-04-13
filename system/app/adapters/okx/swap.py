from __future__ import annotations

from app.adapters.okx.base import OKXAdapter, OKXCommand, OKXCommandResult


class OKXSwapAdapter(OKXAdapter):
    def build_quote_command(self, *, from_token: str, to_token: str, readable_amount: str, chain: str) -> OKXCommand:
        return OKXCommand(
            command="onchainos swap quote",
            arguments=[
                "--from",
                from_token,
                "--to",
                to_token,
                "--readable-amount",
                readable_amount,
                "--chain",
                chain,
            ],
        )

    def build_execute_command(
        self,
        *,
        from_token: str,
        to_token: str,
        readable_amount: str,
        chain: str,
        wallet_address: str,
        slippage_pct: float | None = None,
        gas_level: str | None = None,
    ) -> OKXCommand:
        arguments = [
            "--from",
            from_token,
            "--to",
            to_token,
            "--readable-amount",
            readable_amount,
            "--chain",
            chain,
            "--wallet",
            wallet_address,
        ]
        if slippage_pct is not None:
            arguments.extend(["--slippage", str(slippage_pct)])
        if gas_level is not None:
            arguments.extend(["--gas-level", gas_level])
        return OKXCommand(command="onchainos swap execute", arguments=arguments)

    def get_quote(self, *, from_token: str, to_token: str, readable_amount: str, chain: str) -> OKXCommandResult:
        return self.run(
            self.build_quote_command(from_token=from_token, to_token=to_token, readable_amount=readable_amount, chain=chain)
        )

    def execute(
        self,
        *,
        from_token: str,
        to_token: str,
        readable_amount: str,
        chain: str,
        wallet_address: str,
        slippage_pct: float | None = None,
        gas_level: str | None = None,
    ) -> OKXCommandResult:
        return self.run(
            self.build_execute_command(
                from_token=from_token,
                to_token=to_token,
                readable_amount=readable_amount,
                chain=chain,
                wallet_address=wallet_address,
                slippage_pct=slippage_pct,
                gas_level=gas_level,
            )
        )
