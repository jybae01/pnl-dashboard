from __future__ import annotations

from typing import Any

from .persistence.contracts import (
    CalculationJobQueue,
    CalculationResultWrite,
    ClaimedJob,
    JobStatus,
)


class WorkerJobControl:
    """Queue control plane used only by the independent Python worker."""

    def __init__(self, queue: CalculationJobQueue, worker_id: str):
        if not worker_id.strip():
            raise ValueError("worker_id is required")
        self.queue = queue
        self.worker_id = worker_id

    def claim(self, *, lease_seconds: int = 300) -> ClaimedJob | None:
        return self.queue.claim_next(self.worker_id, lease_seconds=lease_seconds)

    def heartbeat(self, claim: ClaimedJob, *, lease_seconds: int = 300) -> bool:
        return self.queue.heartbeat(claim, lease_seconds=lease_seconds)

    def complete(self, claim: ClaimedJob, result: CalculationResultWrite) -> str:
        return self.queue.complete(claim, result)

    def fail(
        self,
        claim: ClaimedJob,
        error: BaseException | str,
        *,
        error_code: str = "calculation_failed",
        error_detail: dict[str, Any] | None = None,
        retryable: bool = False,
    ) -> JobStatus:
        return self.queue.fail(
            claim,
            error_code=error_code,
            error_message=str(error),
            error_detail=error_detail,
            retryable=retryable,
        )

    def archive(self, claim: ClaimedJob) -> bool:
        return self.queue.archive(claim)

    def delete_message(self, claim: ClaimedJob) -> bool:
        return self.queue.delete_message(claim)
