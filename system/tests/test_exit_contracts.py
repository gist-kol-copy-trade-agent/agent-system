from app.graphs.state import ExitGraphState
from app.persistence.repositories import (
    InMemoryPositionExitEvaluationRepository,
    InMemoryPositionRepository,
    PositionExitEvaluationRecord,
    PositionRecord,
)
from app.schemas.domain import ExitDecision, ExitExecutionRequest, PositionSnapshot, TrailingState
from app.services.strategy_profiles import StrategyProfileService
from app.persistence.repositories import InMemoryStrategyProfileRepository


def test_strategy_profile_includes_trailing_defaults() -> None:
    service = StrategyProfileService(InMemoryStrategyProfileRepository())
    profile = service.get_or_create("u-exit")

    assert profile.trailing_enabled is True
    assert profile.trailing_activation_profit_pct > 0
    assert profile.trailing_drawdown_pct > 0


def test_exit_graph_state_contract_accepts_expected_fields() -> None:
    position_snapshot: PositionSnapshot = {
        "position_id": "pos-1",
        "user_id": "u1",
        "source_id": "src1",
        "asset_lane": "major",
        "chain": "xlayer",
        "symbol": "ETH",
        "token_contract_address": None,
        "wallet_address": "0xabc",
        "status": "open",
        "entry_price_usd": 3000.0,
        "entry_amount_usd": 500.0,
        "entry_token_amount": 0.16,
        "current_price_usd": 3200.0,
        "unrealized_pnl_pct": 6.6,
        "holding_time_hours": 4.0,
        "opened_at": "2026-01-01T00:00:00Z",
        "last_evaluated_at": None,
    }
    trailing_state: TrailingState = {
        "armed": False,
        "activated_at": None,
        "activation_price_usd": None,
        "peak_price_usd": 3200.0,
        "trailing_drawdown_pct": 4.0,
        "last_action": None,
    }
    exit_decision: ExitDecision = {
        "asset_lane": "major",
        "decision": "exit_trailing_arm",
        "decision_reason_code": "TRAILING_ACTIVATION_THRESHOLD_HIT",
        "confidence": 0.82,
        "rationale_summary": "Position is in profit and can arm trailing logic.",
        "telegram_summary": "Trailing has been armed for ETH.",
    }
    execution_request: ExitExecutionRequest = {
        "asset_lane": "major",
        "position_id": "pos-1",
        "side": "sell",
        "chain": "xlayer",
        "wallet_address": "0xabc",
        "from_token": "ETH",
        "to_token": "USDC",
        "readable_amount": "0.16",
        "slippage_pct": 0.5,
    }
    state: ExitGraphState = {
        "messages": [],
        "action_type": "scheduled_exit_evaluation",
        "user_id": "u1",
        "position_id": "pos-1",
        "cycle_id": "cycle-1",
        "position_snapshot": position_snapshot,
        "trailing_state": trailing_state,
        "exit_market_snapshot": None,
        "exit_ta_snapshot": None,
        "strategy_profile": None,
        "exit_decision": exit_decision,
        "policy_gate_result": {"passed": True, "action": "execute", "failure_codes": [], "summary": "ok"},
        "execution_request": execution_request,
        "execution_result": None,
        "telegram_summary": "Trailing has been armed for ETH.",
    }

    assert state["exit_decision"]["decision"] == "exit_trailing_arm"
    assert state["execution_request"]["side"] == "sell"


def test_inmemory_position_repositories_support_exit_records() -> None:
    positions = InMemoryPositionRepository()
    evaluations = InMemoryPositionExitEvaluationRepository()

    positions.save(
        PositionRecord(
            position_id="pos-2",
            user_id="u2",
            source_id="src2",
            asset_lane="regular",
            chain="ethereum",
            symbol="PEPE",
            token_contract_address="0xpepe",
            wallet_address="0xwallet",
            entry_price_usd=0.00001,
            entry_amount_usd=150.0,
            current_price_usd=0.000012,
        )
    )
    open_positions = positions.list_open_positions()
    assert len(open_positions) == 1
    assert open_positions[0].position_id == "pos-2"

    evaluation = evaluations.save(
        PositionExitEvaluationRecord(
            position_id="pos-2",
            cycle_id="cycle-2",
            decision="hold",
            decision_reason_code="TRAILING_NOT_ARMED",
            evaluation={"decision": "hold"},
        )
    )
    assert evaluation.position_id == "pos-2"
    assert evaluation.created_at
