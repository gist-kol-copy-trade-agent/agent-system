from app.adapters.okx.base import OKXCommand, OKXCommandResult, OKXCommandRunner
from app.adapters.okx.market import OKXMarketAdapter
from app.adapters.okx.security import OKXSecurityAdapter
from app.adapters.okx.swap import OKXSwapAdapter
from app.adapters.okx.token import OKXTokenAdapter
from app.adapters.okx.wallet import OKXWalletAdapter
from app.services.okx_contexts import OKXContextService


class FakeRunner(OKXCommandRunner):
    def __init__(self) -> None:
        self.commands: list[OKXCommand] = []

    def run(self, command: OKXCommand) -> OKXCommandResult:
        self.commands.append(command)
        payload = self._payload_for(command)
        return OKXCommandResult(ok=True, command=command, payload=payload)

    def _payload_for(self, command: OKXCommand) -> dict:
        if command.command == "onchainos wallet status":
            return {"data": {"loggedIn": True, "currentAccountId": "acc1", "currentAccountName": "Main", "policy": {}}}
        if command.command == "onchainos wallet balance":
            return {"data": {"totalValueUsd": "1234.56"}}
        if command.command == "onchainos wallet addresses":
            return {"data": {"address": "0xwallet"}}
        if command.command == "onchainos market price":
            return {"data": {"priceUsd": "100.5"}}
        if command.command == "onchainos token price-info":
            return {"data": {"marketCap": "1000000", "liquidity": "250000", "volume24H": "500000", "priceChange24H": "4.5"}}
        if command.command == "onchainos market kline":
            return {"data": [{"close": "100"}, {"close": "105"}]}
        if command.command == "onchainos swap quote":
            return {"data": {"priceImpactPercent": "0.5"}}
        if command.command == "onchainos security token-scan":
            return {"data": {"isRiskToken": False, "buyTaxes": "0", "sellTaxes": "0"}}
        if command.command == "onchainos token advanced-info":
            return {
                "data": {
                    "riskControlLevel": "1",
                    "tokenTags": ["communityRecognized", "smartMoneyBuy"],
                    "devRugPullTokenCount": "0",
                    "devCreateTokenCount": "3",
                    "top10HoldPercent": "12.5",
                    "lpBurnedPercent": "80.0",
                    "creatorAddress": "creator-1",
                }
            }
        return {"data": {}}


def test_wallet_adapter_builds_expected_commands() -> None:
    runner = FakeRunner()
    adapter = OKXWalletAdapter(runner)
    adapter.get_status()
    adapter.get_balance(chain="xlayer")
    adapter.get_addresses(chain="xlayer")
    assert runner.commands[0].command == "onchainos wallet status"
    assert runner.commands[1].arguments == ["--chain", "xlayer"]
    assert runner.commands[2].arguments == ["--chain", "xlayer"]


def test_swap_adapter_builds_execute_command() -> None:
    runner = FakeRunner()
    adapter = OKXSwapAdapter(runner)
    adapter.execute(
        from_token="usdc",
        to_token="eth",
        readable_amount="100",
        chain="xlayer",
        wallet_address="0xwallet",
        slippage_pct=1.0,
        gas_level="average",
    )
    cmd = runner.commands[0]
    assert cmd.command == "onchainos swap execute"
    assert "--wallet" in cmd.arguments
    assert "--slippage" in cmd.arguments
    assert "--gas-level" in cmd.arguments


def test_context_service_normalizes_regular_token_context() -> None:
    runner = FakeRunner()
    service = OKXContextService(
        wallet_adapter=OKXWalletAdapter(runner),
        market_adapter=OKXMarketAdapter(runner),
        token_adapter=OKXTokenAdapter(runner),
        security_adapter=OKXSecurityAdapter(runner),
        swap_adapter=OKXSwapAdapter(runner),
    )
    wallet = service.load_wallet_snapshot(chain="ethereum")
    market = service.load_market_snapshot(
        asset_lane="regular",
        chain="ethereum",
        token_address="0xtoken",
        from_token="usdc",
        readable_amount="100",
    )
    risk = service.load_risk_snapshot(asset_lane="regular", chain="ethereum", token_address="0xtoken")

    assert wallet["logged_in"] is True
    assert wallet["available_balance_usd"] == 1234.56
    assert market["spot_price_usd"] == 100.5
    assert market["liquidity_usd"] == 250000.0
    assert risk["is_risk_token"] is False
    assert risk["dev_rug_pull_token_count"] == 0
    assert risk["token_tags"] == ["communityRecognized", "smartMoneyBuy"]


def test_context_service_major_lane_skips_regular_risk() -> None:
    runner = FakeRunner()
    service = OKXContextService(
        wallet_adapter=OKXWalletAdapter(runner),
        market_adapter=OKXMarketAdapter(runner),
        token_adapter=OKXTokenAdapter(runner),
        security_adapter=OKXSecurityAdapter(runner),
        swap_adapter=OKXSwapAdapter(runner),
    )
    risk = service.load_risk_snapshot(asset_lane="major", chain="xlayer", token_address="eth")
    assert risk["risk_scan_required"] is False
    assert risk["is_risk_token"] is None
