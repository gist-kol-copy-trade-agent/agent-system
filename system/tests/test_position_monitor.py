from app.agents.exit import ExitAgent
from app.agents.position_tracker import PositionTrackerAgent
from app.persistence.repositories import InMemoryPositionRepository, InMemoryWorkflowRunRepository, PositionRecord
from app.services.exit_flow import ExitGraphService
from app.services.position_monitor import PositionMonitorService
from app.services.strategy_profiles import StrategyProfileService
from app.persistence.repositories import InMemoryStrategyProfileRepository
from app.services.workflow_runtime import ExitWorkflowQueueService, ExitWorkflowRuntime


class FakeExitBackend:
    def decide(
        self,
        *,
        position_snapshot,
        trailing_state,
        market_snapshot,
        ta_snapshot,
        strategy_profile,
    ):
        return {
            "asset_lane": position_snapshot["asset_lane"],
            "decision": "hold",
            "decision_reason_code": "NO_EXIT_TRIGGER",
            "confidence": 0.8,
            "rationale_summary": "Hold.",
            "telegram_summary": "Hold.",
        }


class FakePositionTrackerBackend:
    def track_position(self, *, position_snapshot, strategy_profile):
        return {
            "position_tracking_snapshot": {
                "symbol": position_snapshot["symbol"],
                "chain": position_snapshot["chain"],
                "current_price_usd": 105.0,
                "unrealized_pnl_pct": 5.0,
                "realized_pnl_pct": None,
                "position_value_usd": 105.0,
                "cost_basis_usd": position_snapshot["entry_amount_usd"],
                "liquidity_usd": 100000.0,
                "volume_24h_usd": 200000.0,
                "quote_available": True,
                "quote_price_impact_pct": 0.4,
                "kline_window": [{"close": 100.0}, {"close": 105.0}],
            }
        }

    def track_portfolio(self, *, user_id, bot_positions, strategy_profile=None):
        return {
            "portfolio_tracking_snapshot": {
                "wallet_recent_pnl": [],
                "token_pnl_rows": [],
                "tracked_bot_positions": [],
            }
        }


def test_position_monitor_runs_one_cycle() -> None:
    position_repo = InMemoryPositionRepository()
    workflow_repo = InMemoryWorkflowRunRepository()
    strategy_service = StrategyProfileService(InMemoryStrategyProfileRepository())
    position_repo.save(
        PositionRecord(
            position_id="pos-1",
            user_id="u1",
            source_id="src1",
            asset_lane="major",
            chain="xlayer",
            symbol="ETH",
            token_contract_address=None,
            wallet_address="0xabc",
            entry_price_usd=100.0,
            entry_amount_usd=100.0,
        )
    )
    monitor = PositionMonitorService(
        position_repository=position_repo,
        queue_service=ExitWorkflowQueueService(workflow_repo),
        runtime=ExitWorkflowRuntime(
            workflow_repo,
            ExitGraphService(
                strategy_profiles=strategy_service,
                exit_agent=ExitAgent(backend=FakeExitBackend()),
                position_tracker_agent=PositionTrackerAgent(backend=FakePositionTrackerBackend()),
            ),
        ),
    )
    result = monitor.run_cycle(cycle_id="cycle-1")
    assert result.position_ids == ["pos-1"]
    assert result.completed_threads == ["position:pos-1:exit:cycle-1"]
