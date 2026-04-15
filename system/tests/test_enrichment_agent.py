from app.agents.enrichment import EnrichmentAgent


class FakeEnrichmentBackend:
    def enrich(
        self,
        *,
        parsed_signal,
        resolved_asset,
        strategy_profile,
        wallet_context_hints=None,
    ):
        if resolved_asset["asset_lane"] == "major":
            return {
                "wallet_snapshot": {
                    "logged_in": True,
                    "account_id": "acct-1",
                    "account_name": "Test Wallet",
                    "target_chain": "xlayer",
                    "wallet_address": "0xmajor",
                    "available_balance_usd": 1200.0,
                    "available_balance_token": None,
                    "policy_single_tx_limit_usd": None,
                    "policy_daily_trade_limit_usd": None,
                    "policy_daily_trade_used_usd": None,
                },
                "market_snapshot": {
                    "asset_lane": "major",
                    "chain": "xlayer",
                    "spot_price_usd": 3200.0,
                    "market_cap_usd": None,
                    "liquidity_usd": None,
                    "volume_24h_usd": 500000.0,
                    "price_change_24h_pct": 4.2,
                    "kline_window": [{"close": 3000.0}, {"close": 3200.0}],
                    "quote_available": True,
                    "quote_price_impact_pct": 0.4,
                },
                "risk_snapshot": {
                    "asset_lane": "major",
                    "risk_scan_required": False,
                    "risk_scan_supported": False,
                    "is_risk_token": None,
                    "buy_tax_pct": None,
                    "sell_tax_pct": None,
                    "risk_control_level": None,
                    "token_tags": [],
                    "dev_rug_pull_token_count": None,
                    "dev_create_token_count": None,
                    "top10_hold_percent": None,
                    "lp_burned_percent": None,
                    "creator_address": None,
                    "risk_summary": "Major-asset lane skips regular-token risk scan.",
                },
                "signal_overlay": None,
                "wallet_summary": "Wallet is authenticated on X Layer with sufficient buying power.",
                "market_summary": "ETH market context is available with positive price change and usable quote depth.",
                "risk_summary_long": "Major-asset lane skips regular-token risk scanning and relies on market plus TA context.",
                "overlay_summary_long": "",
                "evidence_points": [
                    "Wallet logged in on xlayer.",
                    "Spot price is 3200.0 USD with recent upward candles.",
                ],
            }
        return {
            "wallet_snapshot": {
                "logged_in": True,
                "account_id": "acct-2",
                "account_name": "Test Wallet",
                "target_chain": resolved_asset["target_execution_chain"],
                "wallet_address": "0xregular",
                "available_balance_usd": 800.0,
                "available_balance_token": None,
                "policy_single_tx_limit_usd": None,
                "policy_daily_trade_limit_usd": None,
                "policy_daily_trade_used_usd": None,
            },
            "market_snapshot": {
                "asset_lane": "regular",
                "chain": resolved_asset["target_execution_chain"],
                "spot_price_usd": 100.0,
                "market_cap_usd": 1000000.0,
                "liquidity_usd": 200000.0,
                "volume_24h_usd": 500000.0,
                "price_change_24h_pct": 4.2,
                "kline_window": [{"close": 95.0}, {"close": 100.0}],
                "quote_available": True,
                "quote_price_impact_pct": 0.8,
            },
            "risk_snapshot": {
                "asset_lane": "regular",
                "risk_scan_required": True,
                "risk_scan_supported": True,
                "is_risk_token": False,
                "buy_tax_pct": 0.0,
                "sell_tax_pct": 0.0,
                "risk_control_level": "1",
                "token_tags": ["communityRecognized"],
                "dev_rug_pull_token_count": 0,
                "dev_create_token_count": 2,
                "top10_hold_percent": 15.0,
                "lp_burned_percent": 80.0,
                "creator_address": "stub-creator",
                "risk_summary": "Regular-token enrichment context.",
            },
            "signal_overlay": {
                "supported": True,
                "smart_money_count": 2,
                "kol_count": 1,
                "whale_count": 0,
                "overlay_summary": "Regular token overlay context.",
            },
            "wallet_summary": "Wallet is ready on the target chain with enough balance for a bounded trade.",
            "market_summary": "Market context shows active liquidity, non-empty kline history, and a live quote.",
            "risk_summary_long": "Risk scan is supported and the token is not currently flagged as risky.",
            "overlay_summary_long": "Overlay signals show some smart-money participation with limited whale presence.",
            "evidence_points": [
                "Liquidity is 200000.0 USD.",
                "Kline window has at least two candles.",
                "Smart money count is 2.",
            ],
        }


def test_regular_lane_enrichment_output_contract() -> None:
    agent = EnrichmentAgent(backend=FakeEnrichmentBackend())
    result = agent.enrich(
        parsed_signal={"message_type": "trade_call", "confidence": 0.8},
        resolved_asset={"asset_lane": "regular", "target_execution_chain": "ethereum"},
        strategy_profile={"user_id": "u1"},
    )
    assert result["wallet_snapshot"]["wallet_address"] == "0xregular"
    assert result["risk_snapshot"]["risk_scan_required"] is True
    assert result["market_summary"] != ""
    assert len(result["evidence_points"]) >= 2
