from __future__ import annotations

import time

import pytest

from forecast.persistence.contracts import CalculationResultWrite, JobStatus
from forecast.persistence.local import LocalCalculationJobRepository
from forecast.provenance import ResultProvenance
from forecast.presentation.viewer_dashboard import InvalidCompletedResult, persisted_analysis_view
from forecast.worker import WorkerJobControl
from forecast.worker_runtime import AnalysisRequest, WorkerRunner


PROVENANCE = ResultProvenance("engine-2", "mapping-2", "a" * 64, "2")


class SuccessfulExecutor:
    def execute(self, claim, *, heartbeat=None):
        if heartbeat:
            heartbeat()
        return CalculationResultWrite(
            payload={
                "payload_type": "comparison_analysis",
                "analysis_view": {
                    key: {} for key in (
                        "metadata", "summary", "sales", "material", "manufacturing", "sga"
                    )
                },
            },
            provenance=claim.job.provenance,
            publish=True,
            make_default=True,
        )


class SlowExecutor(SuccessfulExecutor):
    def execute(self, claim, *, heartbeat=None):
        time.sleep(0.12)
        return super().execute(claim, heartbeat=heartbeat)


def _enqueue(tmp_path):
    queue = LocalCalculationJobRepository(tmp_path)
    queue.enqueue(
        model_id="model-1",
        storage_bucket="pnl-models",
        storage_path="models/model-1/source.xlsx",
        provenance=PROVENANCE,
        analysis_request={"publish": True, "make_default": True},
    )
    return queue


def test_analysis_request_rejects_non_contiguous_months():
    with pytest.raises(ValueError, match="contiguous"):
        AnalysisRequest.parse({"months": [1, 3]})


def test_local_worker_completes_and_viewer_reads_only_persisted_view(tmp_path):
    queue = _enqueue(tmp_path)
    runner = WorkerRunner(
        WorkerJobControl(queue, "worker-test"), SuccessfulExecutor(),
        lease_seconds=2, poll_seconds=0,
    )

    outcome = runner.run_once()

    assert outcome.status is JobStatus.COMPLETED
    row = next(tmp_path.joinpath("calculation_results").glob("*.json"))
    import json
    stored = json.loads(row.read_text(encoding="utf-8"))
    assert persisted_analysis_view(stored["result"]) == stored["result"]["analysis_view"]


def test_worker_renews_short_lease_while_executor_runs(tmp_path):
    queue = _enqueue(tmp_path)
    runner = WorkerRunner(
        WorkerJobControl(queue, "worker-test"), SlowExecutor(),
        lease_seconds=1, poll_seconds=0,
    )
    outcome = runner.run_once()
    assert outcome.status is JobStatus.COMPLETED


def test_viewer_rejects_raw_or_unmaterialized_result():
    with pytest.raises(InvalidCompletedResult):
        persisted_analysis_view({"payload_type": "comparison_analysis"})

