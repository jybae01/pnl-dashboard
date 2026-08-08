from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from forecast.persistence import CalculationResultWrite, JobStatus
from forecast.persistence.local import LocalCalculationJobRepository
from forecast.provenance import ResultProvenance
from forecast.worker import WorkerJobControl


class Phase1JobQueueTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.queue = LocalCalculationJobRepository(self.temporary.name)
        self.provenance = ResultProvenance(
            engine_version="1.1.0",
            mapping_version="analysis-v1.0.0",
            mapping_hash="b" * 64,
            result_schema_version="1",
        )

    def tearDown(self):
        self.temporary.cleanup()

    def enqueue(self, *, max_attempts: int = 3):
        return self.queue.enqueue(
            model_id="model-1",
            storage_bucket="pnl-models",
            storage_path="models/model-1/source.xlsx",
            provenance=self.provenance,
            created_by="user-1",
            max_attempts=max_attempts,
        )

    def test_claim_heartbeat_and_complete_are_explicit_control_plane_steps(self):
        pending = self.enqueue()
        worker = WorkerJobControl(self.queue, "worker-a")

        claim = worker.claim(lease_seconds=60)

        self.assertIsNotNone(claim)
        self.assertEqual(claim.job.id, pending.id)
        self.assertEqual(claim.job.status, JobStatus.PROCESSING)
        self.assertEqual(claim.job.attempt, 1)
        self.assertTrue(worker.heartbeat(claim, lease_seconds=120))

        result_id = worker.complete(
            claim,
            CalculationResultWrite(payload={"operating_profit": 123}, provenance=self.provenance),
        )

        self.assertTrue(result_id)
        self.assertEqual(self.queue.get(pending.id).status, JobStatus.COMPLETED)
        saved = json.loads(
            (Path(self.temporary.name) / "calculation_results" / f"{pending.id}.json")
            .read_text(encoding="utf-8")
        )
        self.assertEqual(saved["engine_version"], "1.1.0")
        self.assertEqual(saved["mapping_hash"], "b" * 64)

    def test_retryable_failure_returns_to_pending_then_terminal_failure_stops(self):
        pending = self.enqueue(max_attempts=2)
        worker = WorkerJobControl(self.queue, "worker-a")
        first = worker.claim()
        self.assertEqual(worker.fail(first, "temporary", retryable=True), JobStatus.PENDING)

        second = worker.claim()
        self.assertEqual(second.job.attempt, 2)
        self.assertEqual(worker.fail(second, "permanent", error_code="invalid_workbook"), JobStatus.FAILED)
        failed = self.queue.get(pending.id)
        self.assertEqual(failed.error_code, "invalid_workbook")
        self.assertIsNone(worker.claim())

    def test_completion_rejects_provenance_drift(self):
        self.enqueue()
        claim = WorkerJobControl(self.queue, "worker-a").claim()
        changed = ResultProvenance(
            engine_version="1.1.1",
            mapping_version=self.provenance.mapping_version,
            mapping_hash=self.provenance.mapping_hash,
            result_schema_version=self.provenance.result_schema_version,
        )

        with self.assertRaisesRegex(ValueError, "provenance"):
            self.queue.complete(claim, CalculationResultWrite(payload={}, provenance=changed))


if __name__ == "__main__":
    unittest.main()
