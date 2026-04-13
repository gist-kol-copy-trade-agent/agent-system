from app.agents.history import HistoryAgent
from app.agents.position_tracker import PositionTrackerAgent
from app.persistence.repositories import (
    InMemoryFollowedSourceRepository,
    InMemoryPositionRepository,
    InMemoryStrategyProfileRepository,
    FollowedSourceRecord,
    PositionRecord,
)
from app.services.strategy_profiles import StrategyProfileService
from app.services.wallet_command_flow import WalletCommandGraphService, WalletCommandRequest


class FakePositionTrackerBackend:
    def track_position(self, *, position_snapshot, strategy_profile, resolved_wallet_address=None, wallet_context_hints=None):
        return {
            "position_tracking_snapshot": {
                "symbol": position_snapshot["symbol"],
                "chain": position_snapshot["chain"],
                "current_price_usd": position_snapshot["current_price_usd"],
                "unrealized_pnl_pct": 5.0,
                "realized_pnl_pct": None,
                "position_value_usd": 105.0,
                "cost_basis_usd": position_snapshot["entry_amount_usd"],
                "liquidity_usd": 100000.0,
                "volume_24h_usd": 200000.0,
                "quote_available": True,
                "quote_price_impact_pct": 0.4,
                "kline_window": [{"close": 1.0}, {"close": 1.1}],
            }
        }

    def track_portfolio(
        self,
        *,
        user_id,
        bot_positions,
        strategy_profile=None,
        resolved_wallet_address=None,
        target_chain=None,
        wallet_context_hints=None,
    ):
        return {
            "portfolio_tracking_snapshot": {
                "wallet_recent_pnl": [{"token": "ETH", "pnl_usd": 12.0, "pnl_pct": 4.0}],
                "token_pnl_rows": [{"symbol": "ETH", "chain": "xlayer", "unrealized_pnl_pct": 6.0, "realized_pnl_pct": None, "value_usd": 106.0}],
                "tracked_bot_positions": [{"symbol": "ETH", "chain": "xlayer", "unrealized_pnl_pct": 6.0, "realized_pnl_pct": None, "value_usd": 106.0}],
            }
        }


class FakeHistoryBackend:
    def load_history(
        self,
        *,
        user_id: str,
        raw_text: str,
        time_window: str | None,
        resolved_wallet_address: str | None = None,
        target_chain: str | None = None,
        wallet_context_hints: dict | None = None,
    ):
        return {
            "dex_history_rows": [
                {
                    "chain": "xlayer",
                    "token": "ETH",
                    "side": "buy",
                    "amount_usd": 100.0,
                    "timestamp": "2026-01-01T00:00:00Z",
                    "tx_hash": "0xabc",
                }
            ]
        }


def build_service() -> WalletCommandGraphService:
    strategy_profiles = StrategyProfileService(InMemoryStrategyProfileRepository())
    source_repo = InMemoryFollowedSourceRepository()
    position_repo = InMemoryPositionRepository()
    strategy_profiles.get_or_create("u1")
    source_repo.save(
        FollowedSourceRecord(
            source_id="u1:alpha",
            user_id="u1",
            channel_name="alpha",
            channel_url="https://t.me/alpha",
            status="active",
        )
    )
    position_repo.save(
        PositionRecord(
            position_id="pos-1",
            user_id="u1",
            source_id="u1:alpha",
            asset_lane="major",
            chain="xlayer",
            symbol="ETH",
            token_contract_address=None,
            wallet_address="0xabc",
            entry_price_usd=3000.0,
            entry_amount_usd=100.0,
            current_price_usd=3200.0,
            status="open",
            opened_at="2026-01-01T00:00:00+00:00",
        )
    )
    position_repo.save(
        PositionRecord(
            position_id="pos-2",
            user_id="u1",
            source_id="u1:alpha",
            asset_lane="regular",
            chain="ethereum",
            symbol="PEPE",
            token_contract_address="0xpepe",
            wallet_address="0xabc",
            entry_price_usd=1.0,
            entry_amount_usd=50.0,
            current_price_usd=0.8,
            status="closed",
            opened_at="2026-01-01T00:00:00+00:00",
            closed_at="2026-01-02T00:00:00+00:00",
        )
    )
    return WalletCommandGraphService(
        position_tracker_agent=PositionTrackerAgent(backend=FakePositionTrackerBackend()),
        history_agent=HistoryAgent(backend=FakeHistoryBackend()),
        strategy_profiles=strategy_profiles,
        source_repository=source_repo,
        position_repository=position_repo,
    )


def test_wallet_command_flow_rejects_start() -> None:
    service = build_service()
    state = service.run(WalletCommandRequest(user_id="u1", chat_id="c1", raw_text="/start"))
    assert state["supported_command"] is False


def test_wallet_command_flow_portfolio_includes_active_positions() -> None:
    service = build_service()
    state = service.run(WalletCommandRequest(user_id="u1", chat_id="c1", raw_text="/portfolio"))
    assert state["response_payload"]["active_position_count"] == 1
    assert state["response_payload"]["chain_distribution"]["xlayer"] == 1
    assert state["response_payload"]["portfolio_tracking"]["tracked_bot_positions"][0]["symbol"] == "ETH"
    assert "PnL Snapshot" in state["response_message"]


def test_wallet_command_flow_history() -> None:
    service = build_service()
    state = service.run(WalletCommandRequest(user_id="u1", chat_id="c1", raw_text="/history 7d"))
    assert state["supported_command"] is True
    assert state["command_name"] == "history"
    assert state["response_payload"]["completed_trade_count"] == 1
    assert len(state["response_payload"]["dex_history_snapshot"]["dex_history_rows"]) == 1
    assert "DEX history rows" in state["response_message"]
