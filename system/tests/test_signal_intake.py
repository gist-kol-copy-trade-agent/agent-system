from app.agents.decision import DecisionAgent
from app.agents.enrichment import EnrichmentAgent
from app.agents.parsing import ParsingAgent
from app.agents.swap_execution import SwapExecutionAgent
from app.persistence.repositories import (
    InMemoryPositionEventRepository,
    InMemoryPositionRepository,
    InMemoryStrategyProfileRepository,
    InMemoryTelegramNotificationRepository,
    InMemoryTradeExecutionRepository,
)
from app.services.notifications import NotificationService, RecordingTelegramClient
from app.services.signal_intake import SignalIntakeGraphService, SignalIntakeRequest
from app.services.strategy_profiles import StrategyProfileService


class FakeSwapExecutionBackend:
    def execute(self, *, intent):
        return {
            "execution_request": {
                "asset_lane": intent["asset_lane"],
                "signal_id": intent["signal_id"],
                "side": intent["side"],
                "chain": intent["chain"],
                "wallet_address": intent["wallet_address"],
                "from_token": intent["from_token"],
                "to_token": intent["to_token"],
                "readable_amount": intent["readable_amount"],
                "slippage_pct": intent["slippage_pct"],
            },
            "execution_result": {
                "signal_id": intent["signal_id"],
                "success": True,
                "execution_id": f"exec:{intent['signal_id']}",
                "approve_tx_hash": None,
                "swap_tx_hash": "0xbuy",
                "received_token_amount": "25.0",
                "received_token_symbol": intent["to_token"],
                "error_code": None,
                "error_message": None,
            },
        }


def build_service() -> SignalIntakeGraphService:
    strategy_service = StrategyProfileService(InMemoryStrategyProfileRepository())
    execution_repo = InMemoryTradeExecutionRepository()
    position_repo = InMemoryPositionRepository()
    position_event_repo = InMemoryPositionEventRepository()
    notification_repo = InMemoryTelegramNotificationRepository()
    from tests.test_decision_agent import FakeDecisionBackend
    from tests.test_enrichment_agent import FakeEnrichmentBackend
    from tests.test_parsing_agent import FakeParsingBackend

    service = SignalIntakeGraphService(
        parsing_agent=ParsingAgent(backend=FakeParsingBackend()),
        strategy_profiles=strategy_service,
        enrichment_agent=EnrichmentAgent(backend=FakeEnrichmentBackend()),
        decision_agent=DecisionAgent(backend=FakeDecisionBackend()),
        swap_execution_agent=SwapExecutionAgent(backend=FakeSwapExecutionBackend()),
        execution_repository=execution_repo,
        position_repository=position_repo,
        position_event_repository=position_event_repo,
        notification_service=NotificationService(
            telegram_client=RecordingTelegramClient(),
            notification_repository=notification_repo,
        ),
    )
    service._test_execution_repo = execution_repo  # type: ignore[attr-defined]
    service._test_position_repo = position_repo  # type: ignore[attr-defined]
    service._test_position_event_repo = position_event_repo  # type: ignore[attr-defined]
    service._test_notification_repo = notification_repo  # type: ignore[attr-defined]
    return service


def test_signal_intake_major_lane_flow() -> None:
    service = build_service()
    result = service.run(
        SignalIntakeRequest(
            user_id="u1",
            source_id="src1",
            message_id="sig-major-1",
            message_text="Buy ETH now on X Layer. Entry around 3200.",
        )
    )
    assert result["parsed_signal"]["message_type"] == "trade_call"
    assert result["resolved_asset"]["asset_lane"] == "major"
    assert result["resolved_asset"]["target_execution_chain"] == "xlayer"
    assert result["risk_snapshot"]["risk_scan_required"] is False
    assert result["policy_gate_result"]["action"] == "execute"
    assert result["policy_gate_result"]["passed"] is True
    assert result["execution_request"]["side"] == "buy"
    assert result["execution_result"]["success"] is True
    assert len(service._test_execution_repo._records) == 1  # type: ignore[attr-defined]
    assert len(service._test_position_event_repo._records) == 1  # type: ignore[attr-defined]
    assert len(service._test_notification_repo._records) == 1  # type: ignore[attr-defined]
    assert service._test_position_repo.get_by_position_id("pos:sig-major-1") is not None  # type: ignore[attr-defined]


def test_signal_intake_regular_lane_flow() -> None:
    service = build_service()
    result = service.run(
        SignalIntakeRequest(
            user_id="u1",
            source_id="src1",
            message_id="sig-regular-1",
            message_text="Buy $PEPE on ethereum CA 0x6982508145454ce325ddbe47a25d4ec3d2311933 entry now",
        )
    )
    assert result["parsed_signal"]["message_type"] == "trade_call"
    assert result["resolved_asset"]["asset_lane"] == "regular"
    assert result["resolved_asset"]["resolved_signal_chain"] == "ethereum"
    assert result["risk_snapshot"]["risk_scan_required"] is True
    assert result["policy_gate_result"]["action"] == "execute"
    assert result["execution_result"]["success"] is True


def test_signal_intake_non_actionable_signal_skips() -> None:
    service = build_service()
    result = service.run(
        SignalIntakeRequest(
            user_id="u1",
            source_id="src1",
            message_id="sig-noise-1",
            message_text="GM everyone, market looks interesting today.",
        )
    )
    assert result["trade_decision"]["decision"] == "skip"
    assert result["trade_decision"]["decision_reason_code"] == "NON_ACTIONABLE_SIGNAL"
