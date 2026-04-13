from app.agents.exit import ExitAgent
from app.agents.position_tracker import PositionTrackerAgent
from app.agents.swap_execution import SwapExecutionAgent
from app.persistence.repositories import (
    InMemoryPositionExitEvaluationRepository,
    InMemoryPositionEventRepository,
    InMemoryPositionRepository,
    InMemoryStrategyProfileRepository,
    InMemoryTelegramNotificationRepository,
    InMemoryTradeExecutionRepository,
    PositionRecord,
)
from app.services.exit_flow import ExitFlowRequest, ExitGraphService, OnchainOSSwapExitExecutionRunner
from app.services.notifications import NotificationService, RecordingTelegramClient
from app.services.strategy_profiles import StrategyProfileService


class HoldExitBackend:
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
            "confidence": 0.7,
            "rationale_summary": "No exit trigger.",
            "telegram_summary": "Hold position.",
        }


class TrailingArmExitBackend:
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
            "decision": "exit_trailing_arm",
            "decision_reason_code": "TRAILING_ACTIVATION_THRESHOLD_HIT",
            "confidence": 0.82,
            "rationale_summary": "Arm trailing.",
            "telegram_summary": "Trailing armed.",
        }


class FireExitBackend:
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
            "decision": "exit_trailing_fire",
            "decision_reason_code": "TRAILING_DRAWDOWN_HIT",
            "confidence": 0.88,
            "rationale_summary": "Fire trailing exit.",
            "telegram_summary": "Trailing exit fired.",
        }


class HardExitBackend:
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
            "decision": "exit_hard",
            "decision_reason_code": "MAX_HOLDING_TIME_HIT",
            "confidence": 0.91,
            "rationale_summary": "Max holding time exceeded.",
            "telegram_summary": "Hard exit fired.",
        }


class FakeSwapExecutionBackend:
    def execute(self, *, intent):
        return {
            "execution_request": {
                "asset_lane": intent["asset_lane"],
                "position_id": intent["position_id"],
                "side": intent["side"],
                "chain": intent["chain"],
                "wallet_address": intent["wallet_address"],
                "from_token": intent["from_token"],
                "to_token": intent["to_token"],
                "readable_amount": intent["readable_amount"],
                "slippage_pct": intent["slippage_pct"],
            },
            "execution_result": {
                "position_id": intent["position_id"],
                "success": True,
                "execution_id": f"exec:{intent['position_id']}",
                "approve_tx_hash": None,
                "swap_tx_hash": "0xexit",
                "realized_output_amount": "100.0",
                "realized_output_symbol": intent["to_token"],
                "error_code": None,
                "error_message": None,
            },
        }


class FakePositionTrackerBackend:
    def __init__(self, *, current_price=110.0, liquidity_usd=250000.0, quote_price_impact_pct=0.4):
        self.current_price = current_price
        self.liquidity_usd = liquidity_usd
        self.quote_price_impact_pct = quote_price_impact_pct

    def track_position(self, *, position_snapshot, strategy_profile):
        return {
            "position_tracking_snapshot": {
                "symbol": position_snapshot["symbol"],
                "chain": position_snapshot["chain"],
                "current_price_usd": self.current_price,
                "unrealized_pnl_pct": ((self.current_price - position_snapshot["entry_price_usd"]) / position_snapshot["entry_price_usd"]) * 100,
                "realized_pnl_pct": None,
                "position_value_usd": position_snapshot["entry_amount_usd"] * (self.current_price / position_snapshot["entry_price_usd"]),
                "cost_basis_usd": position_snapshot["entry_amount_usd"],
                "liquidity_usd": self.liquidity_usd,
                "volume_24h_usd": 500000.0,
                "quote_available": True,
                "quote_price_impact_pct": self.quote_price_impact_pct,
                "kline_window": [{"close": self.current_price * 0.97}, {"close": self.current_price}],
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


def build_service(backend, *, trailing_state=None, current_price=110.0, exit_market_price=110.0):
    position_repo = InMemoryPositionRepository()
    eval_repo = InMemoryPositionExitEvaluationRepository()
    execution_repo = InMemoryTradeExecutionRepository()
    position_event_repo = InMemoryPositionEventRepository()
    notification_repo = InMemoryTelegramNotificationRepository()
    notification_service = NotificationService(
        telegram_client=RecordingTelegramClient(),
        notification_repository=notification_repo,
    )
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
            entry_token_amount=1.0,
            current_price_usd=current_price,
            peak_price_since_open_usd=120.0,
            trailing_state=trailing_state or {"armed": False, "trailing_drawdown_pct": 4.0},
            opened_at="2026-04-10T00:00:00Z",
        )
    )
    service = ExitGraphService(
        strategy_profiles=strategy_service,
        exit_agent=ExitAgent(backend=backend),
        position_tracker_agent=PositionTrackerAgent(backend=FakePositionTrackerBackend(current_price=exit_market_price)),
        policy_engine=None,
        position_repository=position_repo,
        evaluation_repository=eval_repo,
        execution_repository=execution_repo,
        position_event_repository=position_event_repo,
        notification_service=notification_service,
        swap_execution_agent=SwapExecutionAgent(backend=FakeSwapExecutionBackend()),
    )
    return service, position_repo, eval_repo, execution_repo, position_event_repo, notification_repo


def test_exit_flow_hold_path() -> None:
    service, _, _, _, _, notification_repo = build_service(HoldExitBackend())
    state = service.run(
        ExitFlowRequest(
            user_id="u1",
            position_id="pos-1",
            cycle_id="cycle-hold",
            position_record=service.position_repository.get_by_position_id("pos-1"),  # type: ignore[arg-type]
        )
    )
    assert state["exit_decision"]["decision"] == "hold"
    assert state["policy_gate_result"]["action"] == "hold"
    assert state["execution_result"] is None
    assert [item["stage"] for item in state["execution_trace"]] == [
        "exit_ta",
        "exit_decision",
        "exit_policy_gate",
    ]
    assert len(notification_repo._records) == 3
    assert notification_repo._records[0].notification_type == "progress:exit_ta"
    assert "📉 Exit Monitoring" in notification_repo._records[0].message_text
    assert "Symbol: ETH" in notification_repo._records[0].message_text
    assert "Action: hold" in notification_repo._records[1].message_text


def test_exit_flow_trailing_arm_path_updates_state() -> None:
    service, position_repo, _, _, _, _ = build_service(TrailingArmExitBackend())
    state = service.run(
        ExitFlowRequest(
            user_id="u1",
            position_id="pos-1",
            cycle_id="cycle-arm",
            position_record=position_repo.get_by_position_id("pos-1"),  # type: ignore[arg-type]
        )
    )
    assert state["exit_decision"]["decision"] == "exit_trailing_arm"
    assert state["policy_gate_result"]["action"] == "persist_trailing"
    assert state["trailing_state"]["armed"] is True


def test_exit_flow_trailing_fire_executes_sell() -> None:
    service, position_repo, _, execution_repo, position_event_repo, notification_repo = build_service(
        FireExitBackend(),
        trailing_state={"armed": True, "peak_price_usd": 120.0, "trailing_drawdown_pct": 4.0},
        current_price=110.0,
    )
    state = service.run(
        ExitFlowRequest(
            user_id="u1",
            position_id="pos-1",
            cycle_id="cycle-fire",
            position_record=position_repo.get_by_position_id("pos-1"),  # type: ignore[arg-type]
        )
    )
    assert state["policy_gate_result"]["action"] == "execute"
    assert state["execution_request"]["side"] == "sell"
    assert state["execution_result"]["success"] is True
    assert len(state["execution_trace"]) == 3
    assert len(execution_repo._records) == 1
    assert len(position_event_repo._records) == 1
    assert len(notification_repo._records) == 4


def test_exit_flow_hard_exit_closes_position() -> None:
    service, position_repo, _, execution_repo, position_event_repo, notification_repo = build_service(HardExitBackend())
    state = service.run(
        ExitFlowRequest(
            user_id="u1",
            position_id="pos-1",
            cycle_id="cycle-hard",
            position_record=position_repo.get_by_position_id("pos-1"),  # type: ignore[arg-type]
        )
    )
    stored = position_repo.get_by_position_id("pos-1")
    assert state["exit_decision"]["decision"] == "exit_hard"
    assert state["execution_result"]["success"] is True
    assert stored is not None
    assert stored.status == "closed"
    assert len(execution_repo._records) == 1
    assert position_event_repo._records[0].event_type == "exit_execution_succeeded"
    assert notification_repo._records[-1].send_status == "sent"


def test_exit_flow_uses_refreshed_market_price_for_pnl() -> None:
    service, position_repo, _, _, _, _ = build_service(
        HoldExitBackend(),
        current_price=100.0,
        exit_market_price=125.0,
    )
    state = service.run(
        ExitFlowRequest(
            user_id="u1",
            position_id="pos-1",
            cycle_id="cycle-refresh",
            position_record=position_repo.get_by_position_id("pos-1"),  # type: ignore[arg-type]
        )
    )
    assert state["exit_market_snapshot"]["current_price_usd"] == 125.0
    assert state["exit_ta_snapshot"]["unrealized_pnl_pct"] == 25.0
    stored = position_repo.get_by_position_id("pos-1")
    assert stored is not None
    assert stored.current_price_usd == 125.0


def test_onchainos_swap_exit_execution_runner_normalizes_cli_result() -> None:
    class FakeMutatingRunner:
        def run(self, command: str):
            assert "onchainos swap execute" in command
            return {
                "ok": True,
                "payload": {
                    "data": {
                        "requestId": "req-1",
                        "approveTxHash": "0xapprove",
                        "swapTxHash": "0xswap",
                        "toAmount": "99.5",
                        "toTokenSymbol": "USDC",
                    }
                },
                "error": None,
            }

    runner = OnchainOSSwapExitExecutionRunner(runner=FakeMutatingRunner())
    result = runner.execute(
        {
            "position_id": "pos-1",
            "from_token": "ETH",
            "to_token": "USDC",
            "readable_amount": "1.0",
            "chain": "xlayer",
            "wallet_address": "0xabc",
            "slippage_pct": 0.5,
        }
    )
    assert result["success"] is True
    assert result["execution_id"] == "req-1"
    assert result["swap_tx_hash"] == "0xswap"
