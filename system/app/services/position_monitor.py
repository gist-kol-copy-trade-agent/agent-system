from __future__ import annotations

from dataclasses import dataclass

from app.persistence.repositories import PositionRepository
from app.services.workflow_runtime import ExitWorkflowQueueService, ExitWorkflowRuntime, PositionMonitorScheduler


@dataclass(frozen=True)
class PositionMonitorRunResult:
    cycle_id: str
    position_ids: list[str]
    completed_threads: list[str]


class PositionMonitorService:
    def __init__(
        self,
        *,
        position_repository: PositionRepository,
        queue_service: ExitWorkflowQueueService,
        runtime: ExitWorkflowRuntime,
    ) -> None:
        self.scheduler = PositionMonitorScheduler(position_repository)
        self.position_repository = position_repository
        self.queue_service = queue_service
        self.runtime = runtime

    def run_cycle(self, *, cycle_id: str) -> PositionMonitorRunResult:
        tick = self.scheduler.create_tick(cycle_id=cycle_id)
        completed_threads: list[str] = []
        for position_id in tick.position_ids:
            position = self.position_repository.get_by_position_id(position_id)
            if position is None:
                continue
            workflow = self.queue_service.enqueue_position(position=position, cycle_id=cycle_id)
            self.runtime.invoke(workflow, cycle_id=cycle_id)
            completed_threads.append(workflow.thread_id)
        return PositionMonitorRunResult(
            cycle_id=cycle_id,
            position_ids=tick.position_ids,
            completed_threads=completed_threads,
        )
