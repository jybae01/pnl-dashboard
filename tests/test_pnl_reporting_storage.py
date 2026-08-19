from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from forecast.bff.pnl_reporting_ingestion import (
    PnlReportingFinalizeError,
    PnlReportingFinalizeUncertainError,
    PnlReportingReservation,
    PnlReportingSourceIntegrityError,
    PnlReportingStorageError,
    SupabasePnlReportingGateway,
)


DATASET_ID = "11111111-1111-4111-8111-111111111111"
INGESTION_ID = "22222222-2222-4222-8222-222222222222"
LEASE = "33333333-3333-4333-8333-333333333333"


class Response:
    def __init__(self, data):
        self.data = data


class StorageBucket:
    def __init__(self):
        self.objects = {}
        self.upload_calls = []
        self.fail_upload = False
        self.store_before_upload_error = False
        self.fail_download = False
        self.fail_remove = False
        self.fail_list = False
        self.leave_after_remove = False

    def upload(self, *, path, file, file_options):
        payload = file.read()
        self.upload_calls.append((path, payload, dict(file_options)))
        if self.fail_upload:
            if self.store_before_upload_error:
                self.objects[path] = payload
            raise OSError("upload response lost")
        if path in self.objects:
            raise OSError("duplicate object")
        self.objects[path] = payload

    def download(self, path):
        if self.fail_download:
            raise OSError("download unavailable")
        if path not in self.objects:
            raise OSError("not found")
        return self.objects[path]

    def remove(self, paths):
        if self.fail_remove:
            raise OSError("remove unavailable")
        if not self.leave_after_remove:
            for path in paths:
                self.objects.pop(path, None)

    def list(self, parent, options):
        if self.fail_list:
            raise OSError("list unavailable")
        prefix = parent + "/"
        return [
            {"name": path[len(prefix):]}
            for path in self.objects
            if path.startswith(prefix) and options["search"] in path
        ]


class Storage:
    def __init__(self, bucket):
        self.bucket = bucket
        self.names = []

    def from_(self, name):
        self.names.append(name)
        return self.bucket


class RpcCall:
    def __init__(self, client, name, args):
        self.client = client
        self.name = name
        self.args = args

    def execute(self):
        self.client.calls.append((self.name, dict(self.args)))
        outcome = self.client.outcomes.get(self.name)
        if isinstance(outcome, Exception):
            raise outcome
        if callable(outcome):
            outcome = outcome()
        return Response(outcome)


class Client:
    def __init__(self):
        self.bucket = StorageBucket()
        self.storage = Storage(self.bucket)
        self.calls = []
        self.outcomes = {}

    def rpc(self, name, args):
        return RpcCall(self, name, args)


def reservation(payload: bytes) -> PnlReportingReservation:
    return PnlReportingReservation(
        ingestion_id=INGESTION_ID,
        dataset_id=DATASET_ID,
        status="RESERVED",
        lease_token=LEASE,
        source_sha256=hashlib.sha256(payload).hexdigest(),
    )


def completed(payload: bytes):
    return {
        "datasetId": DATASET_ID,
        "datasetType": "PLAN",
        "reportingYear": 2026,
        "actualThroughMonth": None,
        "templateVersion": "PNL_REPORTING_V1",
        "sourceSha256": hashlib.sha256(payload).hexdigest(),
        "uploadedAt": "2026-08-19T00:00:00+00:00",
        "warnings": [],
        "supersededDatasetId": None,
        "replayed": False,
    }


def test_private_storage_uses_canonical_path_upsert_false_and_exact_bytes(tmp_path):
    payload = b"exact-workbook-bytes"
    source = tmp_path / "user-name.xlsx"
    source.write_bytes(payload)
    client = Client()
    gateway = SupabasePnlReportingGateway(client)
    item = reservation(payload)
    gateway.upload_source(item, source)
    gateway.verify_source(item)
    assert client.storage.names == ["pnl-models", "pnl-models"]
    path, stored, options = client.bucket.upload_calls[0]
    assert path == f"reporting/{DATASET_ID}/source.xlsx"
    assert stored == payload
    assert options["upsert"] == "false"
    assert "user-name" not in path


def test_upload_lost_response_is_accepted_only_when_readback_sha_is_exact(tmp_path):
    payload = b"exact-workbook-bytes"
    source = tmp_path / "source.xlsx"
    source.write_bytes(payload)
    client = Client()
    client.bucket.fail_upload = True
    client.bucket.store_before_upload_error = True
    gateway = SupabasePnlReportingGateway(client)
    gateway.upload_source(reservation(payload), source)

    client = Client()
    client.bucket.fail_upload = True
    gateway = SupabasePnlReportingGateway(client)
    with pytest.raises(PnlReportingStorageError):
        gateway.upload_source(reservation(payload), source)


def test_sha_mismatch_and_download_failure_are_distinct_safe_failures():
    payload = b"expected"
    client = Client()
    client.bucket.objects[f"reporting/{DATASET_ID}/source.xlsx"] = b"tampered"
    gateway = SupabasePnlReportingGateway(client)
    with pytest.raises(PnlReportingSourceIntegrityError):
        gateway.verify_source(reservation(payload))
    client.bucket.fail_download = True
    with pytest.raises(PnlReportingStorageError):
        gateway.verify_source(reservation(payload))


@pytest.mark.parametrize("mode", ["fail_remove", "fail_list", "leave_after_remove"])
def test_cleanup_requires_verified_absence(mode):
    payload = b"source"
    path = f"reporting/{DATASET_ID}/source.xlsx"
    client = Client()
    client.bucket.objects[path] = payload
    setattr(client.bucket, mode, True)
    gateway = SupabasePnlReportingGateway(client)
    with pytest.raises(PnlReportingStorageError):
        gateway.remove_source(reservation(payload))


def test_cleanup_success_removes_only_the_reserved_canonical_object():
    payload = b"source"
    path = f"reporting/{DATASET_ID}/source.xlsx"
    client = Client()
    client.bucket.objects[path] = payload
    client.bucket.objects["reporting/other/source.xlsx"] = b"other"
    gateway = SupabasePnlReportingGateway(client)
    gateway.remove_source(reservation(payload))
    assert path not in client.bucket.objects
    assert client.bucket.objects["reporting/other/source.xlsx"] == b"other"


def test_lost_finalize_response_requeries_completed_state_and_keeps_source():
    payload = b"source"
    path = f"reporting/{DATASET_ID}/source.xlsx"
    client = Client()
    client.bucket.objects[path] = payload
    client.outcomes["finalize_pnl_reporting_ingestion"] = OSError("response lost")
    client.outcomes["get_completed_pnl_reporting_ingestion"] = completed(payload)
    gateway = SupabasePnlReportingGateway(client)
    result = gateway.finalize(
        reservation(payload),
        canonical_payload={"dataset_type": "PLAN"},
        original_filename="source.xlsx",
        validation_summary={"warnings": []},
    )
    assert result["datasetId"] == DATASET_ID
    assert client.bucket.objects[path] == payload
    assert [name for name, _ in client.calls] == [
        "finalize_pnl_reporting_ingestion",
        "get_completed_pnl_reporting_ingestion",
    ]


def test_clear_uncommitted_finalize_failure_can_be_compensated_but_unknown_lookup_cannot():
    payload = b"source"
    client = Client()
    client.outcomes["finalize_pnl_reporting_ingestion"] = OSError("db failure")
    client.outcomes["get_completed_pnl_reporting_ingestion"] = None
    gateway = SupabasePnlReportingGateway(client)
    with pytest.raises(PnlReportingFinalizeError):
        gateway.finalize(
            reservation(payload), canonical_payload={}, original_filename="source.xlsx",
            validation_summary={},
        )

    client.outcomes["get_completed_pnl_reporting_ingestion"] = OSError("status unknown")
    with pytest.raises(PnlReportingFinalizeUncertainError):
        gateway.finalize(
            reservation(payload), canonical_payload={}, original_filename="source.xlsx",
            validation_summary={},
        )
