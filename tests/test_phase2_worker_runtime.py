from __future__ import annotations

import time
from types import SimpleNamespace

import pytest

import forecast.worker_cli as worker_cli
from forecast.persistence.contracts import CalculationResultWrite, JobStatus
from forecast.persistence.local import LocalCalculationJobRepository
from forecast.provenance import ResultProvenance
from forecast.presentation.viewer_dashboard import InvalidCompletedResult, persisted_analysis_view
from forecast.worker import WorkerJobControl
from forecast.worker_cli import parser as worker_cli_parser
from forecast.worker_runtime import AnalysisRequest, WorkerRunner


PROVENANCE = ResultProvenance("engine-2", "mapping-2", "a" * 64, "2")


def test_worker_cli_defaults_to_local_backend():
    assert worker_cli_parser().parse_args([]).backend == "local"


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


class FailingExecutor:
    def execute(self, claim, *, heartbeat=None):
        raise ValueError("controlled failure")


class RetryableExecutor:
    def execute(self, claim, *, heartbeat=None):
        raise OSError("controlled retryable failure")


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
    assert stored["is_published"] is False
    assert stored["is_default"] is False
    assert stored["published_at"] is None
    assert persisted_analysis_view(stored["result"]) == stored["result"]["analysis_view"]


def test_legacy_analysis_publication_flags_are_accepted_but_ignored():
    request = AnalysisRequest.parse({"publish": False, "make_default": True})
    assert not hasattr(request, "publish")
    assert not hasattr(request, "make_default")


def test_worker_renews_short_lease_while_executor_runs(tmp_path):
    queue = _enqueue(tmp_path)
    runner = WorkerRunner(
        WorkerJobControl(queue, "worker-test"), SlowExecutor(),
        lease_seconds=1, poll_seconds=0,
    )
    outcome = runner.run_once()
    assert outcome.status is JobStatus.COMPLETED


@pytest.mark.parametrize(
    ("executor", "expected_status"),
    [
        (SuccessfulExecutor(), JobStatus.COMPLETED),
        (FailingExecutor(), JobStatus.FAILED),
        (RetryableExecutor(), JobStatus.PENDING),
    ],
)
def test_worker_runs_cleanup_after_claim_is_settled(tmp_path, executor, expected_status):
    queue = _enqueue(tmp_path)
    cleanups = []

    def observe_cleanup(outcome):
        cleanups.append((outcome.status, queue.get(outcome.job_id).status))

    runner = WorkerRunner(
        WorkerJobControl(queue, "worker-test"), executor,
        lease_seconds=2, poll_seconds=0,
        after_job=observe_cleanup,
    )

    outcome = runner.run_once()

    assert outcome.claimed
    assert outcome.status is expected_status
    assert cleanups == [(expected_status, expected_status)]


def test_worker_does_not_run_after_job_cleanup_without_a_claim(tmp_path):
    cleanups = []
    runner = WorkerRunner(
        WorkerJobControl(LocalCalculationJobRepository(tmp_path), "worker-test"),
        SuccessfulExecutor(),
        lease_seconds=2,
        poll_seconds=0,
        after_job=lambda outcome: cleanups.append(outcome.status),
    )

    assert not runner.run_once().claimed
    assert cleanups == []


def test_after_job_cleanup_failure_does_not_resettle_completed_job(tmp_path):
    queue = _enqueue(tmp_path)
    runner = WorkerRunner(
        WorkerJobControl(queue, "worker-test"),
        SuccessfulExecutor(),
        lease_seconds=2,
        poll_seconds=0,
        after_job=lambda _outcome: (_ for _ in ()).throw(OSError("cache cleanup failed")),
    )

    with pytest.raises(OSError, match="cache cleanup failed"):
        runner.run_once()

    assert queue.claim_next("worker-second") is None


def test_supabase_worker_cli_clears_cache_at_startup_and_after_job(monkeypatch):
    events = []

    class Models:
        def clear_cache(self):
            events.append("clear")

    bundle = SimpleNamespace(models=Models(), jobs=object(), backend="supabase")
    monkeypatch.setattr(worker_cli, "create_repository_bundle", lambda *_args, **_kwargs: bundle)
    monkeypatch.setattr(worker_cli, "WorkerJobControl", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(
        worker_cli,
        "DeterministicComparisonExecutor",
        lambda *_args, **_kwargs: object(),
    )

    class Runner:
        def __init__(self, *_args, after_job=None, **_kwargs):
            events.append("runner")
            self.after_job = after_job

        def run_once(self):
            self.after_job(SimpleNamespace(status=JobStatus.COMPLETED))

    monkeypatch.setattr(worker_cli, "WorkerRunner", Runner)

    assert worker_cli.main(["--backend", "supabase", "--once"]) == 0
    assert events == ["clear", "runner", "clear"]


def test_viewer_rejects_raw_or_unmaterialized_result():
    with pytest.raises(InvalidCompletedResult):
        persisted_analysis_view({"payload_type": "comparison_analysis"})
