from __future__ import annotations

import json
import hashlib
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Protocol

from .ai_analysis import build_fact_pack
from .comparison import GenericComparisonEngine, PeriodOption
from .persistence.contracts import (
    CalculationResultWrite,
    ClaimedJob,
    JobStatus,
    ModelRepository,
)
from .preflight import ExcelPreflightValidator, PreflightValidationError
from .presentation.analysis_view import build_analysis_view
from .provenance import mapping_hash
from .worker import WorkerJobControl


class WorkerExecutor(Protocol):
    def execute(
        self,
        claim: ClaimedJob,
        *,
        heartbeat: Callable[[], None] | None = None,
    ) -> CalculationResultWrite: ...


class LeaseLostError(RuntimeError):
    pass


class InputProvenanceUnresolvedError(ValueError):
    pass


class InputIntegrityMismatchError(ValueError):
    def __init__(self, side: str, expected_sha256: str, actual_sha256: str):
        self.side = side
        self.expected_sha256 = expected_sha256
        self.actual_sha256 = actual_sha256
        super().__init__(f"{side} workbook SHA-256 does not match the claimed job")


@dataclass(frozen=True)
class AnalysisRequest:
    baseline_model_id: str | None = None
    months: tuple[int, ...] = ()
    baseline_sales_fx: float = 1480.0
    comparison_sales_fx: float = 1480.0

    @classmethod
    def parse(cls, value: dict[str, Any] | None) -> "AnalysisRequest":
        payload = dict(value or {})
        raw_months = payload.get("months") or ()
        try:
            months = tuple(int(month) for month in raw_months)
        except (TypeError, ValueError) as exc:
            raise ValueError("analysis_request.months must contain integers") from exc
        if months:
            if len(set(months)) != len(months) or any(month < 1 or month > 12 for month in months):
                raise ValueError("analysis_request.months must be unique values from 1 through 12")
            months = tuple(sorted(months))
            if months != tuple(range(months[0], months[-1] + 1)):
                raise ValueError("analysis_request.months must be contiguous")
        baseline_fx = float(payload.get("baseline_sales_fx", 1480.0))
        comparison_fx = float(payload.get("comparison_sales_fx", 1480.0))
        if baseline_fx <= 0 or comparison_fx <= 0:
            raise ValueError("sales FX values must be positive")
        # Legacy publish/make_default keys are intentionally accepted and
        # ignored.  A worker is a calculation capability, never a publication
        # authority; publication is a separate Admin action.
        baseline_id = payload.get("baseline_model_id")
        return cls(
            baseline_model_id=str(baseline_id) if baseline_id else None,
            months=months,
            baseline_sales_fx=baseline_fx,
            comparison_sales_fx=comparison_fx,
        )


class DeterministicComparisonExecutor:
    """Downloads two immutable models and persists one calculation-only JSONB.

    Pre-flight is a hard gate. Presentation and AI payloads are built here in
    the worker so the Viewer only renders stored JSONB and never recalculates.
    """

    def __init__(
        self,
        models: ModelRepository,
        mapping_path: str | Path,
        *,
        allow_legacy_local_inputs: bool = False,
    ):
        self.models = models
        self.mapping_path = Path(mapping_path)
        self.allow_legacy_local_inputs = allow_legacy_local_inputs
        self.mapping = json.loads(self.mapping_path.read_text(encoding="utf-8"))
        self.preflight = ExcelPreflightValidator(self.mapping)

    def execute(
        self,
        claim: ClaimedJob,
        *,
        heartbeat: Callable[[], None] | None = None,
    ) -> CalculationResultWrite:
        request = AnalysisRequest.parse(claim.job.analysis_request)
        current_hash = mapping_hash(self.mapping)
        if current_hash != claim.job.mapping_hash:
            raise ValueError(
                "worker mapping_hash does not match the mapping pinned to the claimed job"
            )

        durable_inputs = (
            claim.job.baseline_model_id,
            claim.job.comparison_model_id,
            claim.job.baseline_workbook_sha256,
            claim.job.comparison_workbook_sha256,
        )
        if any(durable_inputs):
            if not all(durable_inputs):
                raise InputProvenanceUnresolvedError(
                    "durable job input provenance is incomplete; resubmit the job"
                )
            if claim.job.model_id != claim.job.comparison_model_id:
                raise InputProvenanceUnresolvedError(
                    "legacy model_id must equal comparison_model_id"
                )
            comparison_meta = self.models.get(claim.job.comparison_model_id)
            baseline_meta = self.models.get(claim.job.baseline_model_id)
        else:
            # Explicitly isolated compatibility path for local Phase 1/2 jobs.
            # Supabase durable jobs are created by create_durable_calculation_job
            # and always take the pinned branch above.
            if not self.allow_legacy_local_inputs:
                raise InputProvenanceUnresolvedError(
                    "job has no durable input provenance; resubmit the job"
                )
            comparison_meta = self.models.get(claim.job.model_id)
            baseline_meta = (
                self.models.get(request.baseline_model_id)
                if request.baseline_model_id
                else self.models.get_default(
                    year=comparison_meta.year,
                    exclude_model_id=comparison_meta.id,
                )
            )
        if baseline_meta.id == comparison_meta.id:
            raise ValueError("baseline and comparison models must be different")
        if heartbeat:
            heartbeat()

        baseline_path = self.models.path(baseline_meta.id)
        comparison_path = self.models.path(comparison_meta.id)
        if all(durable_inputs):
            baseline_hash = hashlib.sha256(baseline_path.read_bytes()).hexdigest()
            comparison_hash = hashlib.sha256(comparison_path.read_bytes()).hexdigest()
            if baseline_hash != claim.job.baseline_workbook_sha256:
                raise InputIntegrityMismatchError(
                    "baseline", claim.job.baseline_workbook_sha256, baseline_hash
                )
            if comparison_hash != claim.job.comparison_workbook_sha256:
                raise InputIntegrityMismatchError(
                    "comparison", claim.job.comparison_workbook_sha256, comparison_hash
                )
        baseline_report = self.preflight.require(
            baseline_path, expected_year=baseline_meta.year
        )
        comparison_report = self.preflight.require(
            comparison_path, expected_year=comparison_meta.year
        )
        if heartbeat:
            heartbeat()

        engine = GenericComparisonEngine(self.mapping_path)
        common = engine.common_months(baseline_meta, comparison_meta)
        months = request.months or common
        if not months or not set(months).issubset(set(common)):
            raise ValueError("analysis months are not shared by baseline and comparison models")
        period = PeriodOption(
            key=f"R{baseline_meta.year}_{months[0]:02d}_{months[-1]:02d}",
            label=(f"{months[0]}월" if len(months) == 1 else f"{months[0]}~{months[-1]}월"),
            months=tuple(months),
            period_type="월" if len(months) == 1 else "선택기간",
        )
        calculated = engine.compare(
            baseline_meta,
            baseline_path,
            comparison_meta,
            comparison_path,
            period,
            baseline_sales_fx=request.baseline_sales_fx,
            comparison_sales_fx=request.comparison_sales_fx,
        )
        result = asdict(calculated)
        view = build_analysis_view(result)
        fact_pack = build_fact_pack(
            result,
            baseline_sales_fx=request.baseline_sales_fx,
            comparison_sales_fx=request.comparison_sales_fx,
            analysis_view=view,
        )
        if heartbeat:
            heartbeat()

        payload = {
            "payload_type": "comparison_analysis",
            "payload_schema_version": claim.job.result_schema_version,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "comparison_result": result,
            "analysis_view": view,
            "fact_pack": fact_pack,
            "preflight": {
                "baseline": baseline_report.as_dict(),
                "comparison": comparison_report.as_dict(),
            },
        }
        return CalculationResultWrite(
            payload=payload,
            provenance=claim.job.provenance,
        )


@dataclass(frozen=True)
class WorkerRunResult:
    claimed: bool
    job_id: str | None = None
    status: JobStatus | None = None
    result_id: str | None = None


class LeaseHeartbeat:
    """Refresh a pgmq visibility timeout until calculation is ready to commit."""

    def __init__(
        self,
        control: WorkerJobControl,
        claim: ClaimedJob,
        *,
        lease_seconds: int,
        interval_seconds: float | None = None,
    ):
        self.control = control
        self.claim = claim
        self.lease_seconds = lease_seconds
        self.interval_seconds = interval_seconds or max(0.1, lease_seconds / 3)
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._error: BaseException | None = None
        self._thread = threading.Thread(
            target=self._run,
            name=f"pnl-heartbeat-{claim.job.id}",
            daemon=True,
        )

    def start(self) -> None:
        self.beat()
        self._thread.start()

    def beat(self) -> None:
        with self._lock:
            if self._error is not None:
                raise LeaseLostError(str(self._error)) from self._error
            accepted = self.control.heartbeat(
                self.claim, lease_seconds=self.lease_seconds
            )
            if not accepted:
                self._error = LeaseLostError(
                    f"lease lost for calculation job {self.claim.job.id}"
                )
                self._stop.set()
                raise self._error

    def stop(self) -> None:
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(timeout=max(1.0, self.interval_seconds * 2))

    def raise_if_failed(self) -> None:
        if self._error is not None:
            raise LeaseLostError(str(self._error)) from self._error

    def _run(self) -> None:
        while not self._stop.wait(self.interval_seconds):
            try:
                self.beat()
            except BaseException as exc:
                self._error = exc
                self._stop.set()
                return


class WorkerRunner:
    """Single-process independent worker with an interruptible pull loop."""

    def __init__(
        self,
        control: WorkerJobControl,
        executor: WorkerExecutor,
        *,
        lease_seconds: int = 300,
        poll_seconds: float = 2.0,
        stop_event: threading.Event | None = None,
    ):
        if lease_seconds < 1 or poll_seconds < 0:
            raise ValueError("lease_seconds must be positive and poll_seconds non-negative")
        self.control = control
        self.executor = executor
        self.lease_seconds = lease_seconds
        self.poll_seconds = poll_seconds
        self.stop_event = stop_event or threading.Event()

    def run_once(self) -> WorkerRunResult:
        claim = self.control.claim(lease_seconds=self.lease_seconds)
        if claim is None:
            return WorkerRunResult(claimed=False)

        lease = LeaseHeartbeat(
            self.control,
            claim,
            lease_seconds=self.lease_seconds,
        )
        try:
            lease.start()
            result = self.executor.execute(claim, heartbeat=lease.beat)
            # Stop and join before completion so no heartbeat races a terminal
            # status transition.
            lease.stop()
            lease.raise_if_failed()
            result_id = self.control.complete(claim, result)
            return WorkerRunResult(
                claimed=True,
                job_id=claim.job.id,
                status=JobStatus.COMPLETED,
                result_id=result_id,
            )
        except (KeyboardInterrupt, SystemExit):
            lease.stop()
            raise
        except BaseException as exc:
            lease.stop()
            retryable = isinstance(exc, (OSError, TimeoutError, ConnectionError))
            error_code = (
                "INPUT_INTEGRITY_MISMATCH"
                if isinstance(exc, InputIntegrityMismatchError)
                else "INPUT_PROVENANCE_UNRESOLVED"
                if isinstance(exc, InputProvenanceUnresolvedError)
                else "preflight_failed"
                if isinstance(exc, PreflightValidationError)
                else "worker_execution_failed"
            )
            detail = (
                {
                    "input_side": exc.side,
                    "expected_sha256": exc.expected_sha256,
                    "actual_sha256": exc.actual_sha256,
                }
                if isinstance(exc, InputIntegrityMismatchError)
                else {"preflight": exc.report.as_dict()}
                if isinstance(exc, PreflightValidationError)
                else {"exception_type": type(exc).__name__}
            )
            status = self.control.fail(
                claim,
                exc,
                error_code=error_code,
                error_detail=detail,
                retryable=retryable,
            )
            return WorkerRunResult(claimed=True, job_id=claim.job.id, status=status)

    def run_forever(self, *, max_jobs: int | None = None) -> int:
        processed = 0
        while not self.stop_event.is_set():
            outcome = self.run_once()
            if outcome.claimed:
                processed += 1
                if max_jobs is not None and processed >= max_jobs:
                    break
                continue
            self.stop_event.wait(self.poll_seconds)
        return processed
