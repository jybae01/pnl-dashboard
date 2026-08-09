from __future__ import annotations

import tempfile
import unittest

from forecast.persistence import CalculationResultWrite, JobStatus
from forecast.persistence.supabase import (
    SupabaseCalculationJobRepository,
    SupabaseModelRepositoryAdapter,
)
from forecast.provenance import ResultProvenance


class Response:
    def __init__(self, data):
        self.data = data


class RpcCall:
    def __init__(self, data):
        self.data = data

    def execute(self):
        return Response(self.data)


class FakeSupabase:
    def __init__(self):
        self.calls = []
        self.responses = {}
        self.inserted = []

    def rpc(self, name, params):
        self.calls.append((name, params))
        return RpcCall(self.responses[name])

    def table(self, _name):
        return InsertCall(self)


class InsertCall:
    def __init__(self, client):
        self.client = client
        self.row = None

    def insert(self, row):
        self.row = row
        return self

    def execute(self):
        self.client.inserted.append(self.row)
        saved = {**self.row, "id": "job-enqueued", "created_at": "now", "updated_at": "now"}
        return Response([saved])


def job_row(**overrides):
    row = {
        "id": "job-1",
        "model_id": "model-1",
        "status": "processing",
        "storage_bucket": "pnl-models",
        "storage_path": "models/model-1/source.xlsx",
        "engine_version": "1.1.0",
        "mapping_version": "analysis-v1.0.0",
        "mapping_hash": "c" * 64,
        "result_schema_version": "1",
        "attempt": 1,
        "max_attempts": 3,
        "claimed_by": "worker-a",
        "claim_token": "claim-1",
        "heartbeat_at": "2026-08-09T00:00:00+00:00",
        "lease_expires_at": "2026-08-09T00:05:00+00:00",
        "created_at": "2026-08-09T00:00:00+00:00",
        "updated_at": "2026-08-09T00:00:00+00:00",
    }
    row.update(overrides)
    return row


class Phase1SupabaseAdapterTests(unittest.TestCase):
    def setUp(self):
        self.client = FakeSupabase()
        self.queue = SupabaseCalculationJobRepository(self.client)
        self.provenance = ResultProvenance("1.1.0", "analysis-v1.0.0", "c" * 64, "1")

    def test_job_adapter_uses_guarded_claim_complete_and_fail_rpcs(self):
        self.client.responses["claim_calculation_job"] = [job_row()]
        self.client.responses["heartbeat_calculation_job"] = True
        self.client.responses["complete_calculation_job"] = "result-1"
        self.client.responses["fail_calculation_job"] = "failed"

        claim = self.queue.claim_next("worker-a")
        self.assertTrue(self.queue.heartbeat(claim))
        result_id = self.queue.complete(
            claim,
            CalculationResultWrite(payload={"operating_profit": 1}, provenance=self.provenance),
        )
        status = self.queue.fail(claim, error_code="x", error_message="y")

        self.assertEqual(result_id, "result-1")
        self.assertEqual(status, JobStatus.FAILED)
        self.assertEqual(
            [name for name, _params in self.client.calls],
            [
                "claim_calculation_job",
                "heartbeat_calculation_job",
                "complete_calculation_job",
                "fail_calculation_job",
            ],
        )
        complete = self.client.calls[2][1]
        self.assertEqual(complete["p_mapping_hash"], "c" * 64)
        self.assertEqual(complete["p_result_schema_version"], "1")

    def test_direct_enqueue_marks_an_already_uploaded_object_claimable(self):
        job = self.queue.enqueue(
            model_id="model-1",
            storage_bucket="pnl-models",
            storage_path="models/model-1/source.xlsx",
            provenance=self.provenance,
        )

        self.assertEqual(job.status, JobStatus.PENDING)
        self.assertIsNotNone(job.upload_completed_at)
        self.assertIsNotNone(self.client.inserted[0]["upload_completed_at"])

    def test_model_publication_uses_atomic_default_rpc(self):
        self.client.responses["set_model_publication"] = {
            "id": "model-1",
            "name": "model",
            "model_type": "plan",
            "model_year": 2026,
            "confirmed": True,
            "is_published": True,
            "is_default": True,
            "workbook_bucket": "pnl-models",
            "workbook_path": "models/model-1/source.xlsx",
        }
        with tempfile.TemporaryDirectory() as directory:
            repository = SupabaseModelRepositoryAdapter(self.client, directory)
            model = repository.set_publication("model-1", is_published=True, is_default=True)

        self.assertTrue(model.confirmed)
        self.assertTrue(model.is_default)
        self.assertEqual(self.client.calls[0][0], "set_model_publication")


if __name__ == "__main__":
    unittest.main()
