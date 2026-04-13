from app.agents.wallet_command import WalletCommandAgent, WalletCommandOutput
from app.persistence.repositories import (
    InMemoryFollowedSourceRepository,
    InMemoryPositionRepository,
    InMemoryStrategyProfileRepository,
    FollowedSourceRecord,
    PositionRecord,
)
from app.services.strategy_profiles import StrategyProfileService
from app.services.wallet_command_flow import WalletCommandGraphService, WalletCommandRequest


class FakeWalletFlowBackend:
    def handle(self, *, user_id: str, command_name: str, raw_text: str) -> WalletCommandOutput:
        return WalletCommandOutput(
            command=command_name,
            message=f"{command_name} handled",
            payload={"skill": "okx-agentic-wallet", "raw_text": raw_text, "user_id": user_id},
        )


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
        wallet_command_agent=WalletCommandAgent(backend=FakeWalletFlowBackend()),
        strategy_profiles=strategy_profiles,
        source_repository=source_repo,
        position_repository=position_repo,
    )


def test_wallet_command_flow_start() -> None:
    service = build_service()
    state = service.run(WalletCommandRequest(user_id="u1", chat_id="c1", raw_text="/start"))
    assert state["supported_command"] is True
    assert state["command_name"] == "start"
    assert state["response_payload"]["skill"] == "okx-agentic-wallet"


def test_wallet_command_flow_status_includes_local_counts() -> None:
    service = build_service()
    state = service.run(WalletCommandRequest(user_id="u1", chat_id="c1", raw_text="/status"))
    assert state["response_payload"]["strategy_profile_exists"] is True
    assert state["response_payload"]["followed_source_count"] == 1
    assert state["response_payload"]["active_position_count"] == 1


def test_wallet_command_flow_portfolio_includes_active_positions() -> None:
    service = build_service()
    state = service.run(WalletCommandRequest(user_id="u1", chat_id="c1", raw_text="/portfolio"))
    assert state["response_payload"]["active_position_count"] == 1
    assert state["response_payload"]["chain_distribution"]["xlayer"] == 1


def test_wallet_command_flow_history() -> None:
    service = build_service()
    state = service.run(WalletCommandRequest(user_id="u1", chat_id="c1", raw_text="/history 7d"))
    assert state["supported_command"] is True
    assert state["command_name"] == "history"
    assert state["response_payload"]["completed_trade_count"] == 1
