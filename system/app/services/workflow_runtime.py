from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.graphs.runtime import build_thread_id
from app.persistence.repositories import PositionRecord, PositionRepository, WorkflowRunRecord, WorkflowRunRepository
from app.schemas.webhook import ScraperWebhookPayload
from app.services.exit_flow import ExitFlowRequest, ExitGraphService
from app.services.signal_intake import SignalIntakeGraphService, SignalIntakeRequest
from app.services.webhook_intake import AcceptedWebhookEvent


@dataclass(frozen=True)
class EnqueuedWorkflow:
    thread_id: str
    workflow_type: str
    payload: ScraperWebhookPayload | PositionRecord


class SignalWorkflowQueueService:
    def __init__(self, workflow_repository: WorkflowRunRepository) -> None:
        self.workflow_repository = workflow_repository

    def enqueue_signal(self, event: AcceptedWebhookEvent) -> EnqueuedWorkflow:
        self.workflow_repository.save(
            WorkflowRunRecord(
                thread_id=event.thread_id,
                workflow_type="signal-intake",
                related_signal_id=event.payload.event_id,
                related_position_id=None,
                status="pending",
                last_node="webhook_received",
            )
        )
        return EnqueuedWorkflow(thread_id=event.thread_id, workflow_type="signal-intake", payload=event.payload)


class SignalWorkflowRuntime:
    def __init__(self, workflow_repository: WorkflowRunRepository, signal_graph: SignalIntakeGraphService) -> None:
        self.workflow_repository = workflow_repository
        self.signal_graph = signal_graph

    def invoke(self, workflow: EnqueuedWorkflow) -> dict[str, Any]:
        user_id = workflow.payload.source_id.split(":", 1)[0] if ":" in workflow.payload.source_id else workflow.payload.source_id
        self.workflow_repository.save(
            WorkflowRunRecord(
                thread_id=workflow.thread_id,
                workflow_type=workflow.workflow_type,
                related_signal_id=workflow.payload.event_id,
                related_position_id=None,
                status="running",
                last_node="signal_graph_started",
            )
        )
        try:
            state = self.signal_graph.run(
                SignalIntakeRequest(
                    user_id=user_id,
                    source_id=workflow.payload.source_id,
                    message_id=workflow.payload.message_id,
                    message_text=workflow.payload.message_text,
                ),
                thread_id=workflow.thread_id,
            )
        except Exception as exc:
            self.workflow_repository.save(
                WorkflowRunRecord(
                    thread_id=workflow.thread_id,
                    workflow_type=workflow.workflow_type,
                    related_signal_id=workflow.payload.event_id,
                    related_position_id=None,
                    status="failed",
                    last_node="signal_graph_failed",
                    run_metadata={"error": type(exc).__name__, "message": str(exc)},
                )
            )
            raise
        self.workflow_repository.save(
            WorkflowRunRecord(
                thread_id=workflow.thread_id,
                workflow_type=workflow.workflow_type,
                related_signal_id=workflow.payload.event_id,
                related_position_id=None,
                status="completed",
                last_node=_infer_signal_last_node(state),
            )
        )
        return state


@dataclass(frozen=True)
class ExitEvaluationTick:
    cycle_id: str
    position_ids: list[str]


class PositionMonitorScheduler:
    def __init__(self, position_repository: PositionRepository) -> None:
        self.position_repository = position_repository

    def create_tick(self, *, cycle_id: str) -> ExitEvaluationTick:
        position_ids = [record.position_id for record in self.position_repository.list_open_positions()]
        return ExitEvaluationTick(cycle_id=cycle_id, position_ids=position_ids)


class ExitWorkflowQueueService:
    def __init__(self, workflow_repository: WorkflowRunRepository) -> None:
        self.workflow_repository = workflow_repository

    def enqueue_position(self, *, position: PositionRecord, cycle_id: str) -> EnqueuedWorkflow:
        thread_id = build_thread_id("position", f"{position.position_id}:exit:{cycle_id}")
        self.workflow_repository.save(
            WorkflowRunRecord(
                thread_id=thread_id,
                workflow_type="position-exit",
                related_signal_id=None,
                related_position_id=position.position_id,
                status="pending",
                last_node="exit_scheduler_tick",
            )
        )
        return EnqueuedWorkflow(thread_id=thread_id, workflow_type="position-exit", payload=position)


class ExitWorkflowRuntime:
    def __init__(self, workflow_repository: WorkflowRunRepository, exit_graph: ExitGraphService) -> None:
        self.workflow_repository = workflow_repository
        self.exit_graph = exit_graph

    def invoke(self, workflow: EnqueuedWorkflow, *, cycle_id: str) -> dict[str, Any]:
        if not isinstance(workflow.payload, PositionRecord):
            raise TypeError("Exit workflow payload must be a PositionRecord.")

        position = workflow.payload
        self.workflow_repository.save(
            WorkflowRunRecord(
                thread_id=workflow.thread_id,
                workflow_type=workflow.workflow_type,
                related_signal_id=None,
                related_position_id=position.position_id,
                status="running",
                last_node="exit_graph_started",
            )
        )
        try:
            state = self.exit_graph.run(
                ExitFlowRequest(
                    user_id=position.user_id,
                    position_id=position.position_id,
                    cycle_id=cycle_id,
                    position_record=position,
                ),
                thread_id=workflow.thread_id,
            )
        except Exception as exc:
            self.workflow_repository.save(
                WorkflowRunRecord(
                    thread_id=workflow.thread_id,
                    workflow_type=workflow.workflow_type,
                    related_signal_id=None,
                    related_position_id=position.position_id,
                    status="failed",
                    last_node="exit_graph_failed",
                    run_metadata={"error": type(exc).__name__, "message": str(exc), "cycle_id": cycle_id},
                )
            )
            raise
        self.workflow_repository.save(
            WorkflowRunRecord(
                thread_id=workflow.thread_id,
                workflow_type=workflow.workflow_type,
                related_signal_id=None,
                related_position_id=position.position_id,
                status="completed",
                last_node=_infer_exit_last_node(state),
            )
        )
        return state


def _infer_signal_last_node(state: dict[str, Any]) -> str:
    if state.get("execution_result") is not None:
        return "notify_telegram"
    if state.get("policy_gate_result") is not None:
        return "apply_policy_gate"
    if state.get("trade_decision") is not None:
        return "decision"
    if state.get("ta_snapshot") is not None:
        return "compute_ta"
    if state.get("wallet_snapshot") is not None:
        return "enrich_context"
    if state.get("strategy_profile") is not None:
        return "load_strategy_profile"
    if state.get("resolved_asset") is not None:
        return "resolve_target_asset"
    if state.get("parsed_signal") is not None:
        return "parse_signal"
    return "ingest_signal"


def _infer_exit_last_node(state: dict[str, Any]) -> str:
    if state.get("execution_result") is not None:
        return "notify_telegram"
    if state.get("policy_gate_result") is not None:
        action = (state.get("policy_gate_result") or {}).get("action")
        return "persist_evaluation" if action in {"hold", "persist_trailing", "block"} else "apply_exit_policy_gate"
    if state.get("exit_decision") is not None:
        return "exit_decision"
    if state.get("exit_ta_snapshot") is not None:
        return "compute_exit_ta"
    if state.get("exit_market_snapshot") is not None:
        return "load_market_context"
    if state.get("strategy_profile") is not None:
        return "load_strategy_profile"
    if state.get("position_snapshot") is not None:
        return "load_position"
    return "load_position"
