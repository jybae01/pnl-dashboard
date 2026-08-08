from __future__ import annotations

from typing import Any

from .persistence.contracts import (
    CalculationJobQueue,
    CalculationResultWrite,
    ClaimedJob,
    JobStatus,
)


class WorkerJobControl:
    """Control-plane methods for a future independent Python worker.

    This class deliberately has no polling loop and imports neither Streamlit
    nor the calculation engine.  Phase 2 will supply the executor that parses
    the workbook, calls the deterministic engine and invokes these transitions.
    """

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
