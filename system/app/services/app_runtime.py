from __future__ import annotations

from dataclasses import dataclass

from app.adapters.scraper.client import ScraperClient, ScraperRegistrationRequest
from app.adapters.telegram.client import TelegramClient
from app.agents.decision import DecisionAgent
from app.agents.exit import ExitAgent
from app.agents.follow_profiling import FollowProfilingAgent
from app.agents.history import HistoryAgent
from app.agents.parsing import ParsingAgent
from app.agents.position_tracker import PositionTrackerAgent
from app.agents.trade_style_override import TradeStyleOverrideAgent
from app.agents.wallet_agent import WalletAgent
from app.persistence.repositories import (
    SQLAlchemyFollowedSourceRepository,
    SQLAlchemyPositionEventRepository,
    SQLAlchemyPositionExitEvaluationRepository,
    SQLAlchemyPositionRepository,
    SQLAlchemySourceMessageRepository,
    SQLAlchemyStrategyProfileSessionRepository,
    SQLAlchemyStrategyProfileRepository,
    SQLAlchemyTelegramNotificationRepository,
    SQLAlchemyTradeExecutionRepository,
    SQLAlchemyWalletSessionRepository,
    SQLAlchemyWorkflowRunRepository,
)
from app.persistence.session import build_session_factory, create_all
from app.config.settings import ensure_openai_runtime_env
from app.services.exit_flow import ExitGraphService
from app.services.follow_command import FollowCommandService
from app.services.notifications import NotificationService, RecordingTelegramClient
from app.services.position_monitor import PositionMonitorService
from app.services.readiness import RuntimeReadinessService
from app.services.signal_intake import SignalIntakeGraphService
from app.services.source_registry import SourceRegistryService
from app.services.strategy_profiles import StrategyProfileService
from app.services.telegram_commands import TelegramCommandRouter
from app.services.trade_style_setup import TradeStyleSetupService
from app.services.wallet_command_flow import WalletCommandGraphService
from app.services.wallet_service import WalletService
from app.services.webhook_intake import WebhookIntakeService
from app.services.workflow_runtime import (
    ExitWorkflowQueueService,
    ExitWorkflowRuntime,
    SignalWorkflowQueueService,
    SignalWorkflowRuntime,
)


class NoopScraperClient(ScraperClient):
    def request_channel_profile(self, request) -> dict:
        return {
            "ok": True,
            "profile_job_id": f"profile:{request.source_id}",
            "channel_name": request.channel_name,
            "status": "profiling_pending",
        }

    def register_channel(self, request: ScraperRegistrationRequest) -> dict:
        return {
            "ok": True,
            "scraper_subscription_id": f"noop:{request.source_id}",
            "channel_name": request.channel_name,
            "status": "registered",
        }

    def unregister_channel(self, *, source_id: str, channel_name: str) -> dict:
        return {"ok": True, "status": "unregistered", "source_id": source_id, "channel_name": channel_name}


@dataclass
class ApplicationRuntime:
    strategy_profiles: StrategyProfileService
    source_registry: SourceRegistryService
    follow_command_service: FollowCommandService
    telegram_router: TelegramCommandRouter
    webhook_intake: WebhookIntakeService
    signal_queue: SignalWorkflowQueueService
    signal_runtime: SignalWorkflowRuntime
    exit_queue: ExitWorkflowQueueService
    exit_runtime: ExitWorkflowRuntime
    position_monitor: PositionMonitorService
    notification_service: NotificationService
    readiness: RuntimeReadinessService


def build_application_runtime(
    *,
    callback_url: str,
    callback_secret: str,
    scraper_client: ScraperClient | None = None,
    telegram_client: TelegramClient | None = None,
) -> ApplicationRuntime:
    ensure_openai_runtime_env()
    create_all()
    session_factory = build_session_factory()

    strategy_repo = SQLAlchemyStrategyProfileRepository(session_factory)
    source_repo = SQLAlchemyFollowedSourceRepository(session_factory)
    message_repo = SQLAlchemySourceMessageRepository(session_factory)
    workflow_repo = SQLAlchemyWorkflowRunRepository(session_factory)
    position_repo = SQLAlchemyPositionRepository(session_factory)
    position_eval_repo = SQLAlchemyPositionExitEvaluationRepository(session_factory)
    execution_repo = SQLAlchemyTradeExecutionRepository(session_factory)
    position_event_repo = SQLAlchemyPositionEventRepository(session_factory)
    notification_repo = SQLAlchemyTelegramNotificationRepository(session_factory)
    wallet_session_repo = SQLAlchemyWalletSessionRepository(session_factory)
    strategy_profile_session_repo = SQLAlchemyStrategyProfileSessionRepository(session_factory)

    strategy_profiles = StrategyProfileService(strategy_repo)
    source_registry = SourceRegistryService(source_repo, scraper_client or NoopScraperClient())
    notification_service = NotificationService(
        telegram_client=telegram_client or RecordingTelegramClient(),
        notification_repository=notification_repo,
    )
    follow_command_service = FollowCommandService(
        repository=source_repo,
        scraper_client=scraper_client or NoopScraperClient(),
        source_registry=source_registry,
        profiling_agent=FollowProfilingAgent(),
        notification_service=notification_service,
        callback_url=callback_url.replace("/messages", "/follow-profile"),
        callback_secret=callback_secret,
    )
    trade_style_setup_service = TradeStyleSetupService(
        strategy_profiles=strategy_profiles,
        repository=strategy_profile_session_repo,
        override_agent=TradeStyleOverrideAgent(),
    )

    signal_graph = SignalIntakeGraphService(
        parsing_agent=ParsingAgent(),
        strategy_profiles=strategy_profiles,
        enrichment_agent=None,
        decision_agent=DecisionAgent(),
        execution_repository=execution_repo,
        position_repository=position_repo,
        position_event_repository=position_event_repo,
        wallet_session_repository=wallet_session_repo,
        notification_service=notification_service,
    )
    exit_graph = ExitGraphService(
        strategy_profiles=strategy_profiles,
        exit_agent=ExitAgent(),
        position_tracker_agent=PositionTrackerAgent(),
        position_repository=position_repo,
        evaluation_repository=position_eval_repo,
        execution_repository=execution_repo,
        position_event_repository=position_event_repo,
        wallet_session_repository=wallet_session_repo,
        notification_service=notification_service,
    )

    signal_queue = SignalWorkflowQueueService(workflow_repo)
    signal_runtime = SignalWorkflowRuntime(workflow_repo, signal_graph)
    exit_queue = ExitWorkflowQueueService(workflow_repo)
    exit_runtime = ExitWorkflowRuntime(workflow_repo, exit_graph)
    position_monitor = PositionMonitorService(
        position_repository=position_repo,
        queue_service=exit_queue,
        runtime=exit_runtime,
    )
    telegram_router = TelegramCommandRouter(
        strategy_profiles=strategy_profiles,
        source_registry=source_registry,
        callback_url=callback_url,
        callback_secret=callback_secret,
        wallet_command_graph=WalletCommandGraphService(
            position_tracker_agent=PositionTrackerAgent(),
            history_agent=HistoryAgent(),
            strategy_profiles=strategy_profiles,
            source_repository=source_repo,
            position_repository=position_repo,
            wallet_session_repository=wallet_session_repo,
        ),
        wallet_service=WalletService(
            agent=WalletAgent(),
            repository=wallet_session_repo,
        ),
        follow_command_service=follow_command_service,
        trade_style_setup_service=trade_style_setup_service,
    )
    webhook_intake = WebhookIntakeService(message_repo)
    readiness = RuntimeReadinessService()

    return ApplicationRuntime(
        strategy_profiles=strategy_profiles,
        source_registry=source_registry,
        follow_command_service=follow_command_service,
        telegram_router=telegram_router,
        webhook_intake=webhook_intake,
        signal_queue=signal_queue,
        signal_runtime=signal_runtime,
        exit_queue=exit_queue,
        exit_runtime=exit_runtime,
        position_monitor=position_monitor,
        notification_service=notification_service,
        readiness=readiness,
    )
