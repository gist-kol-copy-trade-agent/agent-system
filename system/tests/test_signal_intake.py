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
from tests.test_decision_agent import FakeDecisionBackend
from tests.test_enrichment_agent import FakeEnrichmentBackend
from tests.test_parsing_agent import FakeParsingBackend


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
                "explorer_url": "https://explorer.example/tx/0xbuy",
                "approval_explorer_url": None,
                "execution_price": 3200.0,
                "effective_price_impact_pct": 0.4,
                "route_summary": "USDC -> ETH on xlayer",
                "receipt_message_long": "Swap filled successfully on X Layer.",
                "error_code": None,
                "error_message": None,
            },
        }


class MissingKlineEnrichmentBackend:
    def enrich(
        self,
        *,
        parsed_signal,
        resolved_asset,
        strategy_profile,
        wallet_context_hints=None,
    ):
        return {
            "wallet_snapshot": {
                "logged_in": True,
                "account_id": "acct-1",
                "account_name": "Test Wallet",
                "target_chain": resolved_asset["target_execution_chain"],
                "wallet_address": "0xmajor",
                "available_balance_usd": 1200.0,
                "available_balance_token": None,
                "policy_single_tx_limit_usd": None,
                "policy_daily_trade_limit_usd": None,
                "policy_daily_trade_used_usd": None,
            },
            "market_snapshot": {
                "asset_lane": resolved_asset["asset_lane"],
                "chain": resolved_asset["target_execution_chain"],
                "spot_price_usd": 3200.0,
                "market_cap_usd": None,
                "liquidity_usd": None,
                "volume_24h_usd": 500000.0,
                "price_change_24h_pct": 4.2,
                "kline_window": [],
                "quote_available": True,
                "quote_price_impact_pct": 0.4,
            },
            "risk_snapshot": {
                "asset_lane": resolved_asset["asset_lane"],
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
                "risk_summary": "No risk scan.",
            },
            "signal_overlay": None,
        }


def build_service(*, parsing_backend=None) -> SignalIntakeGraphService:
    strategy_service = StrategyProfileService(InMemoryStrategyProfileRepository())
    execution_repo = InMemoryTradeExecutionRepository()
    position_repo = InMemoryPositionRepository()
    position_event_repo = InMemoryPositionEventRepository()
    notification_repo = InMemoryTelegramNotificationRepository()
    service = SignalIntakeGraphService(
        parsing_agent=ParsingAgent(backend=parsing_backend or FakeParsingBackend()),
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
    assert result["parse_explanation"]["title"] == "Signal parsed"
    assert result["parse_explanation"]["key_metrics"]["message_type"] == "trade_call"
    assert result["resolved_asset"]["asset_lane"] == "major"
    assert result["resolved_asset"]["target_execution_chain"] == "xlayer"
    assert result["resolved_asset"]["approved_major_mapping"] == "xlayer:WETH"
    assert result["risk_snapshot"]["risk_scan_required"] is False
    assert result["policy_gate_result"]["action"] == "execute"
    assert result["policy_gate_result"]["passed"] is True
    assert result["execution_request"]["side"] == "buy"
    assert result["execution_result"]["success"] is True
    assert result["execution_receipt_explanation"]["summary"] == "Buy execution succeeded."
    assert [item["stage"] for item in result["execution_trace"]] == [
        "parse",
        "enrichment",
        "decision",
        "policy_gate",
    ]
    assert len(service._test_execution_repo._records) == 1  # type: ignore[attr-defined]
    assert len(service._test_position_event_repo._records) == 1  # type: ignore[attr-defined]
    assert len(service._test_notification_repo._records) == 5  # type: ignore[attr-defined]
    assert service._test_notification_repo._records[0].notification_type == "progress:parse"  # type: ignore[attr-defined]
    assert "🔎 Signal Parsed" in service._test_notification_repo._records[0].message_text  # type: ignore[attr-defined]
    assert "Asset: ETH" in service._test_notification_repo._records[0].message_text  # type: ignore[attr-defined]
    assert "Action: execute" in service._test_notification_repo._records[2].message_text  # type: ignore[attr-defined]
    assert "Passed: True" in service._test_notification_repo._records[3].message_text  # type: ignore[attr-defined]
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
    assert len(result["execution_trace"]) == 4


def test_signal_intake_blocks_ambiguous_regular_token_without_contract() -> None:
    class AmbiguousRegularParsingBackend:
        def parse(self, *, source_id: str, message_id: str, message_text: str, media_blobs=None):
            return {
                "source_id": source_id,
                "message_id": message_id,
                "message_type": "trade_call",
                "is_actionable": True,
                "raw_symbol": "PEPE",
                "raw_contract_address": None,
                "raw_chain_hint": "ethereum",
                "entry_reference_text": "entry now",
                "target_reference_text": None,
                "stop_reference_text": None,
                "urgency": "high",
                "resolved_symbol": "PEPE",
                "resolved_contract_address": None,
                "resolved_chain": "ethereum",
                "resolved_token_name": None,
                "resolved_decimals": None,
                "confidence": 0.7,
                "reasoning_summary": "classified as trade_call but without exact token identity",
            }

    service = build_service(parsing_backend=AmbiguousRegularParsingBackend())
    result = service.run(
        SignalIntakeRequest(
            user_id="u1",
            source_id="src1",
            message_id="sig-ambiguous-1",
            message_text="Buy PEPE now on ethereum",
        )
    )
    assert result["trade_decision"]["decision"] == "block"
    assert result["trade_decision"]["decision_reason_code"] == "TOKEN_AMBIGUOUS"
    assert result["execution_result"] is None
    assert result["resolved_asset"]["asset_lane"] == "regular"


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
    assert [item["stage"] for item in result["execution_trace"]] == ["parse"]
    assert len(service._test_notification_repo._records) == 2  # type: ignore[attr-defined]
    assert service._test_notification_repo._records[-1].notification_type == "trade_execution"  # type: ignore[attr-defined]
    assert "Signal ignored because it is not a tradeable call." in service._test_notification_repo._records[-1].message_text  # type: ignore[attr-defined]


def test_signal_intake_blocks_when_enrichment_does_not_return_kline_window() -> None:
    strategy_service = StrategyProfileService(InMemoryStrategyProfileRepository())
    service = SignalIntakeGraphService(
        parsing_agent=ParsingAgent(backend=FakeParsingBackend()),
        strategy_profiles=strategy_service,
        enrichment_agent=EnrichmentAgent(backend=MissingKlineEnrichmentBackend()),
        decision_agent=DecisionAgent(backend=FakeDecisionBackend()),
        swap_execution_agent=SwapExecutionAgent(backend=FakeSwapExecutionBackend()),
        execution_repository=InMemoryTradeExecutionRepository(),
        position_repository=InMemoryPositionRepository(),
        position_event_repository=InMemoryPositionEventRepository(),
        notification_service=NotificationService(
            telegram_client=RecordingTelegramClient(),
            notification_repository=InMemoryTelegramNotificationRepository(),
        ),
    )

    result = service.run(
        SignalIntakeRequest(
            user_id="u1",
            source_id="src1",
            message_id="sig-major-missing-kline",
            message_text="Buy ETH now on X Layer. Entry around 3200.",
        )
    )

    assert result["trade_decision"]["decision"] == "block"
    assert result["trade_decision"]["decision_reason_code"] == "MARKET_KLINE_MISSING"
    assert result["policy_gate_result"]["action"] == "block"
    assert result["execution_result"] is None
