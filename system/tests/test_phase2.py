from app.agents.wallet_command import WalletCommandAgent, WalletCommandOutput
from app.agents.wallet_onboarding import WalletOnboardingAgent
from app.agents.decision import DecisionAgent
from app.agents.enrichment import EnrichmentAgent
from app.agents.exit import ExitAgent
from app.agents.follow_profiling import FollowProfilingAgent
from app.agents.parsing import ParsingAgent
from app.agents.trade_style_override import TradeStyleOverrideAgent
from app.adapters.scraper.client import ScraperClient, ScraperHistoricalProfileRequest, ScraperRegistrationRequest
from app.persistence.repositories import (
    FollowedSourceRecord,
    InMemoryFollowedSourceRepository,
    InMemoryPositionRepository,
    InMemorySourceMessageRepository,
    InMemoryStrategyProfileSessionRepository,
    InMemoryStrategyProfileRepository,
    InMemoryWorkflowRunRepository,
    InMemoryWalletSessionRepository,
    PositionRecord,
)
from app.schemas.commands import CommandEnvelope
from app.schemas.webhook import ScraperFollowProfileWebhookPayload, ScraperWebhookPayload
from app.services.signal_intake import SignalIntakeGraphService
from app.services.exit_flow import ExitGraphService
from app.services.follow_command import FollowCommandService
from app.services.source_registry import SourceRegistryService
from app.services.strategy_profiles import StrategyProfileService
from app.services.telegram_commands import TelegramCommandRouter
from app.services.trade_style_setup import TradeStyleSetupService
from app.services.wallet_command_flow import WalletCommandGraphService
from app.services.wallet_onboarding import WalletOnboardingService
from app.services.webhook_intake import WebhookAuthError, WebhookIntakeService
from app.services.workflow_runtime import (
    ExitWorkflowQueueService,
    ExitWorkflowRuntime,
    PositionMonitorScheduler,
    SignalWorkflowQueueService,
    SignalWorkflowRuntime,
)


class FakeScraperClient(ScraperClient):
    def request_channel_profile(self, request: ScraperHistoricalProfileRequest) -> dict:
        return {
            "ok": True,
            "profile_job_id": f"profile:{request.source_id}",
            "channel_name": request.channel_name,
            "status": "profiling_pending",
        }

    def register_channel(self, request: ScraperRegistrationRequest) -> dict:
        return {
            "ok": True,
            "scraper_subscription_id": f"sub:{request.source_id}",
            "channel_name": request.channel_name,
            "status": "registered",
        }

    def unregister_channel(self, *, source_id: str, channel_name: str) -> dict:
        return {"ok": True, "status": "unregistered", "source_id": source_id}


class FakeWalletCommandBackend:
    def handle(self, *, user_id: str, command_name: str, raw_text: str) -> WalletCommandOutput:
        if command_name == "start":
            return WalletCommandOutput(
                command="start",
                message="Wallet readiness loaded via okx-agentic-wallet.",
                payload={"logged_in": True, "address_count": 2, "skill": "okx-agentic-wallet"},
            )
        if command_name == "status":
            return WalletCommandOutput(
                command="status",
                message="Wallet status loaded via okx-agentic-wallet.",
                payload={"logged_in": True, "skill": "okx-agentic-wallet"},
            )
        if command_name == "portfolio":
            return WalletCommandOutput(
                command="portfolio",
                message="Portfolio loaded via wallet command agent.",
                payload={"positions": [], "skill": "okx-agentic-wallet"},
            )
        return WalletCommandOutput(
            command="history",
            message="History loaded via wallet command agent.",
            payload={"events": [], "skill": "okx-agentic-wallet"},
        )


class FakeWalletOnboardingBackend:
    def handle(self, *, user_id: str, raw_text: str, phase: str, locale: str):
        text = raw_text.strip()
        if phase == "start":
            return type(
                "Obj",
                (),
                {
                    "message": "You need to log in with your email first before adding a wallet. What is your email address?",
                    "payload": {"logged_in": False},
                    "model_dump": lambda self=None: {
                        "phase": "awaiting_email",
                        "message": "You need to log in with your email first before adding a wallet. What is your email address?",
                        "payload": {"logged_in": False},
                    },
                },
            )()
        if phase == "awaiting_email":
            return type(
                "Obj",
                (),
                {
                    "message": f"A verification code has been sent to {text}. Please check your inbox and tell me the code.",
                    "payload": {"logged_in": False, "email": text},
                    "model_dump": lambda self=None: {
                        "phase": "awaiting_otp",
                        "message": f"A verification code has been sent to {text}. Please check your inbox and tell me the code.",
                        "payload": {"logged_in": False, "email": text},
                    },
                },
            )()
        return type(
            "Obj",
            (),
            {
                "message": "Wallet created successfully!\nEVM Address: 0xabc\nSolana Address: So1abc",
                "payload": {"logged_in": True, "wallet_evm_address": "0xabc", "wallet_sol_address": "So1abc"},
                "model_dump": lambda self=None: {
                    "phase": "ready",
                    "message": "Wallet created successfully!\nEVM Address: 0xabc\nSolana Address: So1abc",
                    "payload": {"logged_in": True, "wallet_evm_address": "0xabc", "wallet_sol_address": "So1abc"},
                },
            },
        )()


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
        if ta_snapshot["hard_take_profit_hit"]:
            return {
                "asset_lane": position_snapshot["asset_lane"],
                "decision": "exit_hard",
                "decision_reason_code": "TAKE_PROFIT_HIT",
                "confidence": 0.9,
                "rationale_summary": "Take profit threshold hit.",
                "telegram_summary": "Take profit exit for position.",
            }
        return {
            "asset_lane": position_snapshot["asset_lane"],
            "decision": "hold",
            "decision_reason_code": "NO_EXIT_TRIGGER",
            "confidence": 0.8,
            "rationale_summary": "No exit trigger hit.",
            "telegram_summary": "Position remains open.",
        }


class FakeExitExecutionRunner:
    def execute(self, request):
        return {
            "position_id": request["position_id"],
            "success": True,
            "execution_id": f"exec:{request['position_id']}",
            "approve_tx_hash": None,
            "swap_tx_hash": "0xtx",
            "realized_output_amount": "505.0",
            "realized_output_symbol": request["to_token"],
            "error_code": None,
            "error_message": None,
        }


class FakeFollowProfilingBackend:
    def profile(self, *, user_id: str, source_id: str, channel_name: str, messages):
        return {
            "extracted_call_count": 6,
            "evaluated_call_count": 5,
            "win_rate_1d_pct": 60.0,
            "median_return_1d_pct": 8.5,
            "average_return_1d_pct": 6.2,
            "suggested_conviction": "medium",
            "profiling_summary": f"{channel_name} has decent 1-day follow-through.",
            "notable_patterns": ["Strong on majors", "Noisy on microcaps"],
        }


class FakeTradeStyleOverrideBackend:
    def parse_override(self, *, raw_text: str, current_profile: dict):
        text = raw_text.lower()
        patch = {}
        if "max amount per trade" in text and "250" in text:
            patch["max_amount_per_trade_usd"] = 250
        if "disable regular" in text:
            patch["regular_token_lane_enabled"] = False
        return type(
            "Obj",
            (),
            {
                "patch": __import__("app.schemas.strategy", fromlist=["StrategyProfilePatch"]).StrategyProfilePatch(**patch),
                "change_summary": "Parsed override request.",
            },
        )()


def build_router() -> TelegramCommandRouter:
    strategy_repo = InMemoryStrategyProfileRepository()
    strategy_session_repo = InMemoryStrategyProfileSessionRepository()
    source_repo = InMemoryFollowedSourceRepository()
    position_repo = InMemoryPositionRepository()
    strategy_service = StrategyProfileService(strategy_repo)
    strategy_service.get_or_create("u1")
    source_service = SourceRegistryService(source_repo, FakeScraperClient())
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
    return TelegramCommandRouter(
        strategy_profiles=strategy_service,
        source_registry=source_service,
        callback_url="https://bot.example.com/webhooks/scraper/messages",
        callback_secret="secret",
        wallet_command_agent=WalletCommandAgent(backend=FakeWalletCommandBackend()),
        wallet_command_graph=WalletCommandGraphService(
            wallet_command_agent=WalletCommandAgent(backend=FakeWalletCommandBackend()),
            strategy_profiles=strategy_service,
            source_repository=source_repo,
            position_repository=position_repo,
        ),
        wallet_onboarding_service=WalletOnboardingService(
            agent=WalletOnboardingAgent(backend=FakeWalletOnboardingBackend()),
            repository=InMemoryWalletSessionRepository(),
        ),
        follow_command_service=FollowCommandService(
            repository=source_repo,
            scraper_client=FakeScraperClient(),
            source_registry=source_service,
            profiling_agent=FollowProfilingAgent(backend=FakeFollowProfilingBackend()),
            notification_service=None,
            callback_url="https://bot.example.com/webhooks/scraper/follow-profile",
            callback_secret="secret",
        ),
        trade_style_setup_service=TradeStyleSetupService(
            strategy_profiles=strategy_service,
            repository=strategy_session_repo,
            override_agent=TradeStyleOverrideAgent(backend=FakeTradeStyleOverrideBackend()),
        ),
    )


def test_trade_style_guided_setup_flow() -> None:
    router = build_router()
    start = router.handle(CommandEnvelope(user_id="u1", chat_id="c1", raw_text="/trade-style"))
    assert start.ok is True
    assert start.payload["phase"] == "awaiting_base_style"
    assert "choose your trading style" in start.message.lower()

    style = router.handle(CommandEnvelope(user_id="u1", chat_id="c1", raw_text="safe"))
    assert style.ok is True
    assert style.payload["phase"] == "awaiting_override_or_confirm"
    assert style.payload["draft_profile"]["base_style"] == "safe"
    assert style.payload["draft_profile"]["max_amount_per_trade_usd"] == 300

    override = router.handle(
        CommandEnvelope(user_id="u1", chat_id="c1", raw_text="set max amount per trade to 250")
    )
    assert override.ok is True
    assert override.payload["phase"] == "awaiting_override_or_confirm"
    assert override.payload["draft_profile"]["max_amount_per_trade_usd"] == 250

    confirm = router.handle(CommandEnvelope(user_id="u1", chat_id="c1", raw_text="confirm"))
    assert confirm.ok is True
    assert confirm.payload["phase"] == "ready"
    assert confirm.payload["profile"]["max_amount_per_trade_usd"] == 250


def test_follow_and_stop_commands() -> None:
    router = build_router()
    follow = router.handle(CommandEnvelope(user_id="u1", chat_id="c1", raw_text="/follow alpha_kol"))
    assert follow.ok is True
    assert follow.payload["status"] == "profiling_pending"
    assert follow.payload["profile_job_id"] == "profile:u1:alpha_kol"

    stop = router.handle(CommandEnvelope(user_id="u1", chat_id="c1", raw_text="/stop alpha_kol"))
    assert stop.ok is True
    assert stop.payload["status"] == "inactive"


def test_follow_profile_callback_then_yes_confirms_follow() -> None:
    source_repo = InMemoryFollowedSourceRepository()
    strategy_service = StrategyProfileService(InMemoryStrategyProfileRepository())
    scraper_client = FakeScraperClient()
    source_service = SourceRegistryService(source_repo, scraper_client)
    follow_service = FollowCommandService(
        repository=source_repo,
        scraper_client=scraper_client,
        source_registry=source_service,
        profiling_agent=FollowProfilingAgent(backend=FakeFollowProfilingBackend()),
        notification_service=None,
        callback_url="https://bot.example.com/webhooks/scraper/follow-profile",
        callback_secret="secret",
    )
    router = TelegramCommandRouter(
        strategy_profiles=strategy_service,
        source_registry=source_service,
        callback_url="https://bot.example.com/webhooks/scraper/messages",
        callback_secret="secret",
        wallet_command_agent=WalletCommandAgent(backend=FakeWalletCommandBackend()),
        wallet_onboarding_service=WalletOnboardingService(
            agent=WalletOnboardingAgent(backend=FakeWalletOnboardingBackend()),
            repository=InMemoryWalletSessionRepository(),
        ),
        follow_command_service=follow_service,
    )

    initial = router.handle(CommandEnvelope(user_id="u1", chat_id="c1", raw_text="/follow alpha_kol"))
    assert initial.payload["status"] == "profiling_pending"

    accepted = follow_service.accept_profile_callback(
        ScraperFollowProfileWebhookPayload(
            event_id="evt-follow-1",
            event_type="telegram.follow_profile.ready",
            source_id="u1:alpha_kol",
            user_id="u1",
            channel_name="alpha_kol",
            channel_url="https://t.me/alpha_kol",
            profile_job_id="profile:u1:alpha_kol",
            messages=[
                {
                    "message_id": "m1",
                    "message_text": "BUY ETH NOW",
                    "message_timestamp": "2026-01-01T00:00:00Z",
                    "message_url": "https://t.me/alpha_kol/1",
                }
            ],
            raw_payload={},
        )
    )
    assert accepted.status == "awaiting_confirmation"
    assert accepted.suggested_conviction == "medium"

    confirm = router.handle(CommandEnvelope(user_id="u1", chat_id="c1", raw_text="yes"))
    assert confirm.ok is True
    assert confirm.payload["status"] == "active"
    assert confirm.payload["scraper_subscription_id"] == "sub:u1:alpha_kol"


def test_start_email_otp_wallet_onboarding_flow() -> None:
    router = build_router()

    start = router.handle(CommandEnvelope(user_id="u1", chat_id="c1", raw_text="/start"))
    assert start.ok is True
    assert start.command == "start"
    assert "email address" in start.message.lower()

    email = router.handle(CommandEnvelope(user_id="u1", chat_id="c1", raw_text="user@example.com"))
    assert email.ok is True
    assert "verification code" in email.message.lower()

    otp = router.handle(CommandEnvelope(user_id="u1", chat_id="c1", raw_text="123456"))
    assert otp.ok is True
    assert "Wallet created successfully!" in otp.message
    assert otp.payload["phase"] == "ready"
    assert otp.payload["wallet_evm_address"] == "0xabc"


def test_status_route_via_wallet_command_agent() -> None:
    router = build_router()

    status = router.handle(CommandEnvelope(user_id="u1", chat_id="c1", raw_text="/status"))
    assert status.ok is True
    assert status.command == "status"
    assert status.payload["skill"] == "okx-agentic-wallet"
    assert status.payload["followed_source_count"] == 1
    assert status.payload["active_position_count"] == 1


def test_portfolio_and_history_route_via_wallet_command_agent() -> None:
    router = build_router()

    portfolio = router.handle(CommandEnvelope(user_id="u1", chat_id="c1", raw_text="/portfolio"))
    assert portfolio.ok is True
    assert portfolio.command == "portfolio"
    assert portfolio.payload["skill"] == "okx-agentic-wallet"
    assert portfolio.payload["active_position_count"] == 1

    history = router.handle(CommandEnvelope(user_id="u1", chat_id="c1", raw_text="/history 7d"))
    assert history.ok is True
    assert history.command == "history"
    assert history.payload["skill"] == "okx-agentic-wallet"
    assert history.payload["completed_trade_count"] == 1


def test_webhook_signature_and_dedupe() -> None:
    intake = WebhookIntakeService(InMemorySourceMessageRepository())
    body = b'{"event":"x"}'
    sig = intake.build_signature(body=body, timestamp="123", secret="secret")
    intake.verify_signature(body=body, timestamp="123", secret="secret", provided_signature=sig)

    payload = ScraperWebhookPayload(
        event_id="evt1",
        event_type="telegram.message.new",
        source_id="src1",
        channel_name="alpha_kol",
        message_id="m1",
        message_text="buy eth",
        message_timestamp="2026-01-01T00:00:00Z",
        raw_payload={},
    )
    accepted = intake.accept_event(payload)
    assert accepted is not None
    assert accepted.thread_id == "signal:evt1"
    assert intake.accept_event(payload) is None


def test_webhook_bad_signature_raises() -> None:
    intake = WebhookIntakeService(InMemorySourceMessageRepository())
    try:
        intake.verify_signature(body=b"x", timestamp="1", secret="secret", provided_signature="bad")
    except WebhookAuthError:
        assert True
        return
    assert False, "expected WebhookAuthError"


def test_webhook_enqueue_and_runtime_invocation() -> None:
    message_repo = InMemorySourceMessageRepository()
    workflow_repo = InMemoryWorkflowRunRepository()
    intake = WebhookIntakeService(message_repo)
    queue = SignalWorkflowQueueService(workflow_repo)

    strategy_service = StrategyProfileService(InMemoryStrategyProfileRepository())
    from tests.test_decision_agent import FakeDecisionBackend
    from tests.test_enrichment_agent import FakeEnrichmentBackend
    from tests.test_parsing_agent import FakeParsingBackend

    runtime = SignalWorkflowRuntime(
        workflow_repo,
        SignalIntakeGraphService(
            parsing_agent=ParsingAgent(backend=FakeParsingBackend()),
            strategy_profiles=strategy_service,
            enrichment_agent=EnrichmentAgent(backend=FakeEnrichmentBackend()),
            decision_agent=DecisionAgent(backend=FakeDecisionBackend()),
        ),
    )

    payload = ScraperWebhookPayload(
        event_id="evt2",
        event_type="telegram.message.new",
        source_id="u1:alpha_kol",
        channel_name="alpha_kol",
        message_id="m2",
        message_text="Buy ETH now on X Layer",
        message_timestamp="2026-01-01T00:00:00Z",
        raw_payload={},
    )
    accepted = intake.accept_event(payload)
    assert accepted is not None
    workflow = queue.enqueue_signal(accepted)
    state = runtime.invoke(workflow)

    assert workflow.thread_id == "signal:evt2"
    assert state["parsed_signal"]["message_type"] == "trade_call"
    assert state["policy_gate_result"]["action"] in {"execute", "skip", "block"}


def test_signal_workflow_runtime_marks_failed_runs() -> None:
    message_repo = InMemorySourceMessageRepository()
    workflow_repo = InMemoryWorkflowRunRepository()
    intake = WebhookIntakeService(message_repo)
    queue = SignalWorkflowQueueService(workflow_repo)

    class FailingSignalGraph:
        def run(self, *args, **kwargs):
            raise RuntimeError("boom")

    runtime = SignalWorkflowRuntime(workflow_repo, FailingSignalGraph())  # type: ignore[arg-type]

    payload = ScraperWebhookPayload(
        event_id="evt-fail",
        event_type="telegram.message.new",
        source_id="u1:alpha_kol",
        channel_name="alpha_kol",
        message_id="m-fail",
        message_text="Buy ETH now on X Layer",
        message_timestamp="2026-01-01T00:00:00Z",
        raw_payload={},
    )
    accepted = intake.accept_event(payload)
    assert accepted is not None
    workflow = queue.enqueue_signal(accepted)

    try:
        runtime.invoke(workflow)
    except RuntimeError as exc:
        assert str(exc) == "boom"
    else:
        assert False, "expected runtime failure"

    stored = workflow_repo._records[workflow.thread_id]
    assert stored.status == "failed"
    assert stored.last_node == "signal_graph_failed"
    assert stored.run_metadata == {"error": "RuntimeError", "message": "boom"}


def test_position_scheduler_enqueue_and_exit_runtime_invocation() -> None:
    workflow_repo = InMemoryWorkflowRunRepository()
    position_repo = InMemoryPositionRepository()
    strategy_service = StrategyProfileService(InMemoryStrategyProfileRepository())

    position_repo.save(
        PositionRecord(
            position_id="pos-1",
            user_id="u1",
            source_id="u1:alpha_kol",
            asset_lane="major",
            chain="xlayer",
            symbol="ETH",
            token_contract_address=None,
            wallet_address="0xabc",
            entry_price_usd=3000.0,
            entry_amount_usd=500.0,
            current_price_usd=3200.0,
            peak_price_since_open_usd=3210.0,
            trailing_state={"armed": False, "trailing_drawdown_pct": 4.0},
        )
    )

    scheduler = PositionMonitorScheduler(position_repo)
    tick = scheduler.create_tick(cycle_id="cycle-1")
    assert tick.position_ids == ["pos-1"]

    queue = ExitWorkflowQueueService(workflow_repo)
    workflow = queue.enqueue_position(position=position_repo.get_by_position_id("pos-1"), cycle_id=tick.cycle_id)  # type: ignore[arg-type]
    runtime = ExitWorkflowRuntime(
        workflow_repo,
        ExitGraphService(
            strategy_profiles=strategy_service,
            position_repository=position_repo,
            exit_agent=ExitAgent(backend=FakeExitBackend()),
            execution_runner=FakeExitExecutionRunner(),
        ),
    )
    state = runtime.invoke(workflow, cycle_id=tick.cycle_id)

    assert workflow.thread_id == "position:pos-1:exit:cycle-1"
    assert state["action_type"] == "scheduled_exit_evaluation"
    assert state["position_snapshot"]["position_id"] == "pos-1"
    assert state["strategy_profile"]["trailing_enabled"] is True
