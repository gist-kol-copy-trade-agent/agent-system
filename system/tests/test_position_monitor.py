from app.agents.exit import ExitAgent
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
            ExitGraphService(strategy_profiles=strategy_service, exit_agent=ExitAgent(backend=FakeExitBackend())),
        ),
    )
    result = monitor.run_cycle(cycle_id="cycle-1")
    assert result.position_ids == ["pos-1"]
    assert result.completed_threads == ["position:pos-1:exit:cycle-1"]
