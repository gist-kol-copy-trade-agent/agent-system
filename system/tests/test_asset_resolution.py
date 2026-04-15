from app.services.asset_resolution import AssetResolver


class FakeReadonlyRunner:
    def __init__(self, response: dict):
        self.response = response
        self.commands: list[str] = []

    def run(self, command: str) -> dict:
        self.commands.append(command)
        return self.response


def test_asset_resolver_uses_token_search_for_symbol_and_chain() -> None:
    resolver = AssetResolver(
        readonly_runner=FakeReadonlyRunner(
            {
                "ok": True,
                "payload": {
                    "data": [
                        {
                            "symbol": "PEPE",
                            "tokenContractAddress": "0x6982508145454ce325ddbe47a25d4ec3d2311933",
                            "chain": "ethereum",
                            "decimals": 18,
                            "tokenName": "Pepe",
                        }
                    ]
                },
            }
        )
    )

    result = resolver.resolve_regular(
        {
            "raw_symbol": "PEPE",
            "raw_chain_hint": "ethereum",
            "resolved_symbol": "PEPE",
            "resolved_chain": "ethereum",
            "confidence": 0.8,
        }
    )

    assert result.status == "resolved"
    assert result.token_contract_address == "0x6982508145454ce325ddbe47a25d4ec3d2311933"
    assert result.resolved_chain == "ethereum"


def test_asset_resolver_marks_ambiguous_when_search_returns_multiple_candidates() -> None:
    resolver = AssetResolver(
        readonly_runner=FakeReadonlyRunner(
            {
                "ok": True,
                "payload": {
                    "data": [
                        {
                            "symbol": "PEPE",
                            "tokenContractAddress": "0x1111111111111111111111111111111111111111",
                            "chain": "ethereum",
                        },
                        {
                            "symbol": "PEPE",
                            "tokenContractAddress": "0x2222222222222222222222222222222222222222",
                            "chain": "ethereum",
                        },
                    ]
                },
            }
        )
    )

    result = resolver.resolve_regular(
        {
            "raw_symbol": "PEPE",
            "raw_chain_hint": "ethereum",
            "resolved_symbol": "PEPE",
            "resolved_chain": "ethereum",
            "confidence": 0.8,
        }
    )

    assert result.status == "ambiguous"
    assert result.reason_code == "TOKEN_AMBIGUOUS"


def test_parse_reference_price_prefers_entry_text() -> None:
    assert AssetResolver.parse_reference_price({"entry_reference_text": "entry 3200-3300"}) == 3250.0
    assert AssetResolver.parse_reference_price({"entry_reference_text": "entry around 3200"}) == 3200.0
    assert AssetResolver.parse_reference_price({"entry_reference_text": None, "target_reference_text": "target 3500"}) is None
