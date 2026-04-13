from app.agents.decision import DecisionAgent
from app.agents.parsing import ParsingAgent
from app.persistence.repositories import InMemoryStrategyProfileRepository
from app.services.signal_intake import SignalIntakeGraphService, SignalIntakeRequest
from app.services.strategy_profiles import StrategyProfileService


def build_service() -> SignalIntakeGraphService:
    strategy_service = StrategyProfileService(InMemoryStrategyProfileRepository())
    from tests.test_decision_agent import FakeDecisionBackend
    from tests.test_parsing_agent import FakeParsingBackend

    return SignalIntakeGraphService(
        parsing_agent=ParsingAgent(backend=FakeParsingBackend()),
        strategy_profiles=strategy_service,
        decision_agent=DecisionAgent(backend=FakeDecisionBackend()),
    )


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
