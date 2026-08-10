from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from forecast.persistence.contracts import CalculationJob, ClaimedJob, JobStatus
from forecast.provenance import mapping_hash
from forecast.storage import ModelMeta
from forecast.worker_runtime import (
    DeterministicComparisonExecutor,
    InputIntegrityMismatchError,
    InputProvenanceUnresolvedError,
    WorkerRunner,
)


class PinnedModels:
    def __init__(self, base, comparison, paths):
        self.models = {base.id: base, comparison.id: comparison}
        self.paths = paths
        self.default_lookups = 0

    def get(self, model_id):
        return self.models[model_id]

    def get_default(self, **_kwargs):
        self.default_lookups += 1
        raise AssertionError("durable worker must not resolve a runtime default")

    def path(self, model_id):
        return self.paths[model_id]


def meta(model_id: str) -> ModelMeta:
    return ModelMeta(
        id=model_id,
        name=model_id,
        model_type="plan",
        year=2026,
        start_month=1,
        end_month=12,
        created_date="2026-01-01",
        version="V1",
        confirmed=True,
        file_name="model.xlsx",
        uploaded_at="now",
    )


def durable_claim(mapping_path, base_path, comparison_path):
    mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
    job = CalculationJob(
        id="job-1",
        model_id="comparison",
        status=JobStatus.PROCESSING,
        storage_bucket="pnl-models",
        storage_path="models/comparison/source.xlsx",
        engine_version="engine-1",
        mapping_version="mapping-1",
        mapping_hash=mapping_hash(mapping),
        result_schema_version="1",
        baseline_model_id="baseline",
        comparison_model_id="comparison",
        baseline_workbook_sha256=hashlib.sha256(base_path.read_bytes()).hexdigest(),
        comparison_workbook_sha256=hashlib.sha256(comparison_path.read_bytes()).hexdigest(),
        claim_token="claim-1",
    )
    return ClaimedJob(job=job, claim_token="claim-1")


@pytest.fixture
def pinned(tmp_path):
    base_path = tmp_path / "base.xlsx"
    comparison_path = tmp_path / "comparison.xlsx"
    base_path.write_bytes(b"base workbook bytes")
    comparison_path.write_bytes(b"comparison workbook bytes")
    mapping_path = Path(__file__).resolve().parents[1] / "config/model_mapping.json"
    models = PinnedModels(
        meta("baseline"),
        meta("comparison"),
        {"baseline": base_path, "comparison": comparison_path},
    )
    claim = durable_claim(mapping_path, base_path, comparison_path)
    return models, mapping_path, claim


def test_baseline_sha_mismatch_rejects_without_default_lookup(pinned):
    models, mapping_path, claim = pinned
    claim = ClaimedJob(
        job=replace(claim.job, baseline_workbook_sha256="0" * 64),
        claim_token=claim.claim_token,
    )
    executor = DeterministicComparisonExecutor(models, mapping_path)
    with pytest.raises(InputIntegrityMismatchError, match="baseline workbook"):
        executor.execute(claim)
    assert models.default_lookups == 0


def test_comparison_sha_mismatch_rejects_without_default_lookup(pinned):
    models, mapping_path, claim = pinned
    claim = ClaimedJob(
        job=replace(claim.job, comparison_workbook_sha256="0" * 64),
        claim_token=claim.claim_token,
    )
    executor = DeterministicComparisonExecutor(models, mapping_path)
    with pytest.raises(InputIntegrityMismatchError, match="comparison workbook"):
        executor.execute(claim)
    assert models.default_lookups == 0


def test_supabase_worker_rejects_unresolved_legacy_job(pinned):
    models, mapping_path, claim = pinned
    unresolved = replace(
        claim.job,
        baseline_model_id=None,
        comparison_model_id=None,
        baseline_workbook_sha256=None,
        comparison_workbook_sha256=None,
    )
    executor = DeterministicComparisonExecutor(models, mapping_path)
    with pytest.raises(InputProvenanceUnresolvedError, match="resubmit"):
        executor.execute(ClaimedJob(job=unresolved, claim_token="claim-1"))
    assert models.default_lookups == 0


class RecordingControl:
    def __init__(self, claim):
        self.pending_claim = claim
        self.completed = False
        self.failure = None

    def claim(self, *, lease_seconds):
        claim, self.pending_claim = self.pending_claim, None
        return claim

    def heartbeat(self, claim, *, lease_seconds):
        return True

    def complete(self, claim, result):
        self.completed = True
        return "result-1"

    def fail(self, claim, exc, **details):
        self.failure = details
        return JobStatus.FAILED


def test_integrity_mismatch_fails_job_without_result_creation(pinned):
    models, mapping_path, claim = pinned
    claim = ClaimedJob(
        job=replace(claim.job, baseline_workbook_sha256="0" * 64),
        claim_token=claim.claim_token,
    )
    control = RecordingControl(claim)
    runner = WorkerRunner(
        control,
        DeterministicComparisonExecutor(models, mapping_path),
        lease_seconds=2,
        poll_seconds=0,
    )

    outcome = runner.run_once()

    assert outcome.status is JobStatus.FAILED
    assert control.completed is False
    assert control.failure["error_code"] == "INPUT_INTEGRITY_MISMATCH"
    assert control.failure["error_detail"]["input_side"] == "baseline"
    assert control.failure["retryable"] is False
