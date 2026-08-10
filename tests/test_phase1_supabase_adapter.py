from __future__ import annotations

import tempfile
import unittest
import hashlib

from forecast.persistence import CalculationResultWrite, JobStatus
from forecast.persistence.supabase import (
    SupabaseCalculationJobRepository,
    SupabaseModelRepositoryAdapter,
    SupabaseResultRepository,
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
        self.storage = FakeStorage()

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


class FakeBucket:
    def __init__(self, uploads):
        self.uploads = uploads

    def upload(self, path, content, options):
        self.uploads.append((path, content, options))


class FakeStorage:
    def __init__(self):
        self.uploads = []

    def from_(self, _bucket):
        return FakeBucket(self.uploads)


class ResultReadCall:
    def __init__(self, client):
        self.client = client

    def select(self, columns):
        self.client.read_filters.append(("select", columns))
        return self

    def eq(self, column, value):
        self.client.read_filters.append(("eq", column, value))
        return self

    def order(self, column, *, desc=False):
        self.client.read_filters.append(("order", column, desc))
        return self

    def limit(self, value):
        self.client.read_filters.append(("limit", value))
        return self

    def execute(self):
        return Response([])


class ResultReadSupabase:
    def __init__(self):
        self.calls = []

    def rpc(self, name, params):
        self.calls.append((name, params))
        return RpcCall([])


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
        "baseline_model_id": "model-base",
        "comparison_model_id": "model-1",
        "baseline_workbook_sha256": "a" * 64,
        "comparison_workbook_sha256": "b" * 64,
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
        self.assertNotIn("p_is_published", complete)
        self.assertNotIn("p_is_default", complete)

    def test_durable_enqueue_pins_explicit_base_and_comparison(self):
        self.client.responses["create_durable_calculation_job"] = job_row(
            id="job-enqueued",
            status="pending",
            upload_completed_at="now",
            claim_token=None,
        )
        job = self.queue.enqueue(
            baseline_model_id="model-base",
            comparison_model_id="model-1",
            provenance=self.provenance,
        )

        self.assertEqual(job.status, JobStatus.PENDING)
        self.assertIsNotNone(job.upload_completed_at)
        name, params = self.client.calls[-1]
        self.assertEqual(name, "create_durable_calculation_job")
        self.assertEqual(params["p_baseline_model_id"], "model-base")
        self.assertEqual(params["p_comparison_model_id"], "model-1")

    def test_durable_enqueue_rejects_missing_pins(self):
        with self.assertRaisesRegex(ValueError, "baseline_model_id"):
            self.queue.enqueue(
                baseline_model_id="",
                comparison_model_id="model-1",
                provenance=self.provenance,
            )
        with self.assertRaisesRegex(ValueError, "comparison_model_id"):
            self.queue.enqueue(
                baseline_model_id="model-base",
                comparison_model_id="",
                provenance=self.provenance,
            )

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

    def test_model_ingestion_records_hash_of_uploaded_bytes(self):
        content = b"exact workbook bytes"
        with tempfile.TemporaryDirectory() as directory:
            repository = SupabaseModelRepositoryAdapter(self.client, directory)
            model = repository.add(
                content,
                name="comparison",
                model_type="forecast",
                year=2026,
                period_types={"1": "actual"},
            )

        expected = hashlib.sha256(content).hexdigest()
        self.assertEqual(model.workbook_sha256, expected)
        self.assertEqual(self.client.inserted[-1]["workbook_sha256"], expected)
        self.assertEqual(self.client.storage.uploads[-1][1], content)

    def test_viewer_result_read_uses_narrow_provenance_validating_rpc(self):
        client = ResultReadSupabase()

        self.assertIsNone(SupabaseResultRepository(client).load_completed())

        self.assertEqual(client.calls, [("get_published_calculation_result", {})])


if __name__ == "__main__":
    unittest.main()
