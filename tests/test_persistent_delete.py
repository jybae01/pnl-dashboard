from __future__ import annotations

from collections import deque
from types import SimpleNamespace

import pytest

from forecast.bff.errors import ApiErrorCode, BffError
from forecast.bff.persistent_delete import (
    PersistentDeleteGatewayError,
    PersistentDeleteService,
    SupabasePersistentDeleteGateway,
)


MODEL_1 = "11111111-1111-4111-8111-111111111111"
MODEL_2 = "22222222-2222-4222-8222-222222222222"
JOB_1 = "33333333-3333-4333-8333-333333333333"


class Sessions:
    def require_admin(self, session_id: str) -> None:
        if session_id != "admin":
            raise BffError(ApiErrorCode.FORBIDDEN, "Admin access is required")


def prepared(
    resource_id: str,
    *,
    resource_type: str = "model",
    status: str = "READY_FOR_STORAGE",
    owner_model_id: str | None = None,
    path: str | None = "canonical",
    references=None,
    replayed: bool = False,
):
    owner = owner_model_id or resource_id
    if path == "canonical":
        path = (
            f"models/{resource_id}/source.xlsx"
            if resource_type == "model"
            else f"models/{owner}/jobs/{resource_id}/result.xlsx"
        )
    return {
        "delete_status": status,
        "storage_bucket": "pnl-models" if path else None,
        "storage_path": path,
        "owner_model_id": owner,
        "reference_counts": references or {},
        "idempotent_replayed": replayed,
    }


class Gateway:
    def __init__(
        self,
        model_values=(),
        analysis_values=(),
        lookup_values=(),
        recoverable=(),
        storage_required_values=(),
    ):
        self.models = deque(model_values)
        self.analyses = deque(analysis_values)
        self.lookups = deque(lookup_values)
        self.recoverable = tuple(recoverable)
        self.storage_requirements = deque(storage_required_values)
        self.storage_deleted = []
        self.completed = []
        self.failures = []
        self.events = []
        self.storage_failure = False
        self.complete_failure = False

    def prepare_model_delete(self, model_id):
        value = self.models.popleft()
        return value(model_id) if callable(value) else value

    def prepare_analysis_delete(self, job_id):
        value = self.analyses.popleft()
        return value(job_id) if callable(value) else value

    def lookup_delete(self, resource_type, resource_id):
        value = self.lookups.popleft()
        return value(resource_type, resource_id) if callable(value) else value

    def list_recoverable(self, resource_type):
        return self.recoverable

    def storage_required(self, resource_type, resource_id):
        if not self.storage_requirements:
            return False
        value = self.storage_requirements.popleft()
        return value(resource_type, resource_id) if callable(value) else value

    def delete_storage_object(self, bucket, path):
        if self.storage_failure:
            raise PersistentDeleteGatewayError("storage failed")
        self.storage_deleted.append((bucket, path))
        self.events.append("storage_absence_verified")

    def complete_delete(self, resource_type, resource_id):
        if self.complete_failure:
            raise PersistentDeleteGatewayError("complete response lost")
        self.completed.append((resource_type, resource_id))
        self.events.append("receipt_complete")

    def record_cleanup_failure(self, resource_type, resource_id, error_code):
        self.failures.append((resource_type, resource_id, error_code))
        self.events.append("cleanup_required")


def test_model_batch_deletes_owned_storage_and_reports_blocked_reference_counts():
    gateway = Gateway(model_values=[
        prepared(MODEL_1),
        prepared(MODEL_2, status="BLOCKED_IN_USE", path=None, references={"analysis_jobs": 2}),
    ])
    result = PersistentDeleteService(Sessions(), gateway).delete_models(
        "admin", [MODEL_1, MODEL_2]
    )

    assert (result.requested_count, result.deleted_count, result.blocked_count, result.failed_count) == (2, 1, 1, 0)
    assert gateway.storage_deleted == [("pnl-models", f"models/{MODEL_1}/source.xlsx")]
    assert gateway.completed == [("model", MODEL_1)]
    assert gateway.events == ["storage_absence_verified", "receipt_complete"]
    assert result.items[1].reason == "MODEL_IN_USE"
    assert result.items[1].reference_counts == {"analysis_jobs": 2}


def test_analysis_delete_preserves_owner_identity_and_blocks_non_terminal():
    gateway = Gateway(analysis_values=[
        prepared(JOB_1, resource_type="analysis", owner_model_id=MODEL_2),
        prepared(MODEL_1, resource_type="analysis", owner_model_id=MODEL_2,
                 status="BLOCKED_NON_TERMINAL", path=None, references={"status": "processing"}),
    ])
    result = PersistentDeleteService(Sessions(), gateway).delete_analyses(
        "admin", [JOB_1, MODEL_1]
    )

    assert result.deleted_count == 1
    assert result.blocked_count == 1
    assert gateway.storage_deleted == [
        ("pnl-models", f"models/{MODEL_2}/jobs/{JOB_1}/result.xlsx")
    ]
    assert result.items[1].reason == "NON_TERMINAL_ANALYSIS_DELETE_BLOCKED"


def test_storage_failure_is_explicit_and_same_id_retry_is_idempotent():
    gateway = Gateway(model_values=[
        prepared(MODEL_1),
        prepared(MODEL_1, replayed=True),
    ])
    service = PersistentDeleteService(Sessions(), gateway)
    gateway.storage_failure = True
    first = service.delete_models("admin", [MODEL_1])
    assert first.items[0].status == "CLEANUP_REQUIRED"
    assert first.cleanup_required_count == 1
    assert gateway.failures == [("model", MODEL_1, "STORAGE_CLEANUP_FAILED")]

    gateway.storage_failure = False
    second = service.delete_models("admin", [MODEL_1])
    assert second.items[0].status == "DELETED"
    assert second.items[0].idempotent_replayed is True
    assert gateway.completed == [("model", MODEL_1)]


def test_already_complete_receipt_is_deleted_idempotent_success_without_storage_call():
    gateway = Gateway(model_values=[
        prepared(MODEL_1, status="DELETED", replayed=True),
    ])
    result = PersistentDeleteService(Sessions(), gateway).delete_models("admin", [MODEL_1])
    assert result.deleted_count == 1
    assert result.items[0].reason == "ALREADY_DELETED"
    assert gateway.storage_deleted == []


@pytest.mark.parametrize("ids", [[], ["not-a-uuid"], [MODEL_1, MODEL_1]])
def test_delete_batch_rejects_empty_invalid_or_duplicate_ids(ids):
    with pytest.raises(BffError) as caught:
        PersistentDeleteService(Sessions(), Gateway()).delete_models("admin", ids)
    assert caught.value.code == ApiErrorCode.VALIDATION_ERROR


def test_viewer_is_rejected_before_persistence_is_called():
    gateway = Gateway(model_values=[prepared(MODEL_1)])
    with pytest.raises(BffError) as caught:
        PersistentDeleteService(Sessions(), gateway).delete_models("viewer", [MODEL_1])
    assert caught.value.code == ApiErrorCode.FORBIDDEN
    assert len(gateway.models) == 1


def test_authoritative_path_mismatch_fails_closed_without_storage_delete():
    gateway = Gateway(model_values=[prepared(MODEL_1, path=f"models/{MODEL_2}/source.xlsx")])
    result = PersistentDeleteService(Sessions(), gateway).delete_models("admin", [MODEL_1])
    assert result.items[0].status == "CLEANUP_REQUIRED"
    assert gateway.storage_deleted == []
    assert gateway.completed == []


def test_model_prepare_missing_required_storage_provenance_stays_uncertain():
    malformed = prepared(MODEL_1, path=None)
    gateway = Gateway(model_values=[malformed], lookup_values=[malformed])
    result = PersistentDeleteService(Sessions(), gateway).delete_models("admin", [MODEL_1])
    assert result.items[0].status == "PREPARE_UNCERTAIN"
    assert result.items[0].reason == "DELETE_PREPARE_UNCERTAIN"
    assert gateway.storage_deleted == []
    assert gateway.completed == []


def test_analysis_without_an_owned_storage_object_can_complete():
    gateway = Gateway(
        analysis_values=[prepared(JOB_1, resource_type="analysis", path=None)]
    )
    result = PersistentDeleteService(Sessions(), gateway).delete_analyses("admin", [JOB_1])
    assert result.items[0].status == "DELETED"
    assert gateway.storage_deleted == []
    assert gateway.completed == [("analysis", JOB_1)]


def test_analysis_missing_path_cannot_complete_when_receipt_requires_storage():
    gateway = Gateway(
        analysis_values=[prepared(JOB_1, resource_type="analysis", path=None)],
        storage_required_values=[True],
    )
    result = PersistentDeleteService(Sessions(), gateway).delete_analyses("admin", [JOB_1])
    assert result.items[0].status == "CLEANUP_REQUIRED"
    assert result.items[0].reason == "DELETE_STORAGE_PROVENANCE_UNCERTAIN"
    assert gateway.storage_deleted == []
    assert gateway.completed == []


def test_analysis_missing_path_stays_retryable_when_requirement_lookup_fails():
    def unavailable(_resource_type, _resource_id):
        raise TimeoutError("receipt requirement lookup unavailable")

    gateway = Gateway(
        analysis_values=[prepared(JOB_1, resource_type="analysis", path=None)],
        storage_required_values=[unavailable],
    )
    result = PersistentDeleteService(Sessions(), gateway).delete_analyses("admin", [JOB_1])
    assert result.items[0].status == "CLEANUP_REQUIRED"
    assert result.items[0].reason == "DELETE_STORAGE_PROVENANCE_UNCERTAIN"
    assert gateway.completed == []


class RpcResult:
    def __init__(self, data): self.data = data
    def execute(self): return self


class StorageBucket:
    def __init__(self):
        self.removed = []
        self.remaining = []
        self.remove_error = None
        self.list_error = None
        self.list_response = None
    def remove(self, paths):
        self.removed.append(paths)
        if self.remove_error:
            raise self.remove_error
        return []
    def list(self, parent, options):
        if self.list_error:
            raise self.list_error
        if self.list_response is not None:
            return self.list_response
        offset = options.get("offset", 0)
        limit = options.get("limit", 100)
        return self.remaining[offset:offset + limit]


class StorageFailure(RuntimeError):
    def __init__(self, message, status):
        super().__init__(message)
        self.status = status


class SupabaseClient:
    def __init__(self):
        self.bucket = StorageBucket()
        self.storage = SimpleNamespace(from_=lambda name: self.bucket)
    def rpc(self, name, params):
        return RpcResult([prepared(MODEL_1)])


def test_supabase_gateway_reads_receipt_storage_requirement_as_boolean():
    client = SimpleNamespace(rpc=lambda _name, _params: RpcResult(True))
    gateway = SupabasePersistentDeleteGateway(client)
    assert gateway.storage_required("analysis", JOB_1) is True


def test_supabase_gateway_rejects_malformed_storage_requirement():
    client = SimpleNamespace(rpc=lambda _name, _params: RpcResult("true"))
    gateway = SupabasePersistentDeleteGateway(client)
    with pytest.raises(PersistentDeleteGatewayError, match="invalid data"):
        gateway.storage_required("analysis", JOB_1)


def test_supabase_gateway_uses_storage_remove_and_verifies_exact_object_absence():
    client = SupabaseClient()
    gateway = SupabasePersistentDeleteGateway(client)
    path = f"models/{MODEL_1}/source.xlsx"
    gateway.delete_storage_object("pnl-models", path)
    assert client.bucket.removed == [[path]]

    client.bucket.remaining = [{"name": "another-model.xlsx"}]
    gateway.delete_storage_object("pnl-models", path)
    client.bucket.remaining = [{"name": "source.xlsx"}]
    with pytest.raises(PersistentDeleteGatewayError):
        gateway.delete_storage_object("pnl-models", path)


def test_supabase_gateway_keeps_unknown_remove_response_loss_retryable_even_when_absent():
    client = SupabaseClient()
    gateway = SupabasePersistentDeleteGateway(client)
    path = f"models/{MODEL_1}/source.xlsx"
    client.bucket.remove_error = TimeoutError("response lost")
    with pytest.raises(PersistentDeleteGatewayError, match="outcome is uncertain"):
        gateway.delete_storage_object("pnl-models", path)

    client.bucket.remaining = [{"name": "source.xlsx"}]
    with pytest.raises(PersistentDeleteGatewayError):
        gateway.delete_storage_object("pnl-models", path)


def test_supabase_gateway_accepts_explicit_not_found_retry_after_exact_absence():
    client = SupabaseClient()
    gateway = SupabasePersistentDeleteGateway(client)
    path = f"models/{MODEL_1}/source.xlsx"
    client.bucket.remove_error = StorageFailure("not found", 404)
    gateway.delete_storage_object("pnl-models", path)


@pytest.mark.parametrize("status", [403, 500])
def test_supabase_gateway_fails_closed_on_storage_auth_or_server_error(status):
    client = SupabaseClient()
    gateway = SupabasePersistentDeleteGateway(client)
    path = f"models/{MODEL_1}/source.xlsx"
    client.bucket.remove_error = StorageFailure("remove failed", status)
    with pytest.raises(PersistentDeleteGatewayError, match="outcome is uncertain"):
        gateway.delete_storage_object("pnl-models", path)


@pytest.mark.parametrize("status", [403, 500])
def test_supabase_gateway_requires_authoritative_list_absence(status):
    client = SupabaseClient()
    gateway = SupabasePersistentDeleteGateway(client)
    path = f"models/{MODEL_1}/source.xlsx"
    client.bucket.list_error = StorageFailure("list failed", status)
    with pytest.raises(PersistentDeleteGatewayError, match="verification failed"):
        gateway.delete_storage_object("pnl-models", path)


@pytest.mark.parametrize(
    "malformed",
    [None, "not-a-list", [{}], [{"unexpected": "shape"}] * 1000],
)
def test_supabase_gateway_fails_closed_on_malformed_or_unbounded_list(malformed):
    client = SupabaseClient()
    gateway = SupabasePersistentDeleteGateway(client)
    path = f"models/{MODEL_1}/source.xlsx"
    client.bucket.list_response = malformed if malformed is not None else {"name": "bad"}
    with pytest.raises(PersistentDeleteGatewayError, match="verification failed"):
        gateway.delete_storage_object("pnl-models", path)


@pytest.mark.parametrize("prepare_failure", [
    TimeoutError("timeout after dispatch"),
    ConnectionError("connection lost after dispatch"),
])
def test_post_commit_prepare_transport_loss_recovers_receipt_and_completes(prepare_failure):
    def fail(_resource_id):
        raise prepare_failure

    gateway = Gateway(
        model_values=[fail],
        lookup_values=[prepared(MODEL_1, status="CLEANUP_REQUIRED", replayed=True)],
    )
    result = PersistentDeleteService(Sessions(), gateway).delete_models("admin", [MODEL_1])

    assert result.items[0].status == "DELETED"
    assert result.items[0].idempotent_replayed is True
    assert gateway.storage_deleted == [("pnl-models", f"models/{MODEL_1}/source.xlsx")]
    assert gateway.completed == [("model", MODEL_1)]


def test_malformed_prepare_response_after_commit_uses_authoritative_receipt():
    gateway = Gateway(
        model_values=[{"delete_status": "broken"}],
        lookup_values=[prepared(MODEL_1, status="CLEANUP_REQUIRED", replayed=True)],
    )
    result = PersistentDeleteService(Sessions(), gateway).delete_models("admin", [MODEL_1])
    assert result.items[0].status == "DELETED"


def test_receipt_lookup_outage_is_prepare_uncertain_not_permanent_failure():
    def prepare_timeout(_resource_id):
        raise TimeoutError

    def lookup_timeout(_resource_type, _resource_id):
        raise TimeoutError

    gateway = Gateway(model_values=[prepare_timeout], lookup_values=[lookup_timeout])
    result = PersistentDeleteService(Sessions(), gateway).delete_models("admin", [MODEL_1])
    assert result.items[0].status == "PREPARE_UNCERTAIN"
    assert result.items[0].reason == "DELETE_PREPARE_UNCERTAIN"
    assert result.uncertain_count == 1
    assert result.failed_count == 0


def test_authoritative_not_committed_remains_prepare_failure():
    def prepare_timeout(_resource_id):
        raise TimeoutError

    gateway = Gateway(
        model_values=[prepare_timeout],
        lookup_values=[prepared(MODEL_1, status="NOT_COMMITTED", path=None)],
    )
    result = PersistentDeleteService(Sessions(), gateway).delete_models("admin", [MODEL_1])
    assert result.items[0].status == "FAILED"
    assert result.items[0].reason == "DELETE_PREPARE_FAILED"


def test_cleanup_retry_uses_receipt_without_repeating_domain_prepare():
    gateway = Gateway(
        lookup_values=[
            prepared(MODEL_1, status="CLEANUP_REQUIRED", replayed=True),
            prepared(MODEL_1, status="CLEANUP_REQUIRED", replayed=True),
        ],
    )
    service = PersistentDeleteService(Sessions(), gateway)
    gateway.storage_failure = True
    first = service.retry_model_cleanup("admin", [MODEL_1])
    assert first.items[0].status == "CLEANUP_REQUIRED"
    gateway.storage_failure = False
    second = service.retry_model_cleanup("admin", [MODEL_1])
    assert second.items[0].status == "DELETED"
    assert not gateway.models


def test_complete_response_loss_rechecks_receipt_before_reporting_success():
    gateway = Gateway(
        model_values=[prepared(MODEL_1)],
        lookup_values=[prepared(MODEL_1, status="DELETED", replayed=True)],
    )
    gateway.complete_failure = True
    result = PersistentDeleteService(Sessions(), gateway).delete_models("admin", [MODEL_1])
    assert result.items[0].status == "DELETED"
    assert result.items[0].idempotent_replayed is True


def test_recovery_listing_exposes_receipts_without_storage_paths_in_result():
    row = {
        **prepared(MODEL_1, status="CLEANUP_REQUIRED", replayed=True),
        "resource_id": MODEL_1,
    }
    result = PersistentDeleteService(
        Sessions(), Gateway(recoverable=[row])
    ).list_model_recoveries("admin")
    assert result.cleanup_required_count == 1
    assert result.items[0].resource_id == MODEL_1


def test_default_or_published_resources_are_item_level_blocks_in_mixed_batch():
    gateway = Gateway(model_values=[
        prepared(MODEL_1),
        prepared(MODEL_2, status="BLOCKED_PROTECTED", path=None,
                 references={"publication_state": "default"}),
    ])
    result = PersistentDeleteService(Sessions(), gateway).delete_models(
        "admin", [MODEL_1, MODEL_2]
    )
    assert (result.deleted_count, result.blocked_count, result.failed_count) == (1, 1, 0)
    assert result.items[1].reason == "DELETE_PROTECTED_RESOURCE"


@pytest.mark.parametrize("publication_state", ["default", "published"])
def test_protected_model_state_is_explicit(publication_state):
    gateway = Gateway(model_values=[prepared(
        MODEL_1,
        status="BLOCKED_PROTECTED",
        path=None,
        references={"publication_state": publication_state},
    )])
    result = PersistentDeleteService(Sessions(), gateway).delete_models("admin", [MODEL_1])
    assert result.items[0].status == "BLOCKED_PROTECTED"
    assert result.items[0].reason == "DELETE_PROTECTED_RESOURCE"
    assert gateway.storage_deleted == []


@pytest.mark.parametrize("publication_state", ["default", "published"])
def test_protected_calculation_result_state_is_explicit(publication_state):
    gateway = Gateway(analysis_values=[prepared(
        JOB_1,
        resource_type="analysis",
        owner_model_id=MODEL_1,
        status="BLOCKED_PROTECTED",
        path=None,
        references={"publication_state": publication_state},
    )])
    result = PersistentDeleteService(Sessions(), gateway).delete_analyses("admin", [JOB_1])
    assert result.items[0].status == "BLOCKED_PROTECTED"
    assert result.items[0].reason == "DELETE_PROTECTED_RESOURCE"
    assert gateway.storage_deleted == []


def test_uncertain_item_does_not_hide_later_batch_success():
    def prepare_timeout(_resource_id):
        raise TimeoutError

    def lookup_timeout(_resource_type, _resource_id):
        raise TimeoutError

    gateway = Gateway(
        model_values=[prepare_timeout, prepared(MODEL_2)],
        lookup_values=[lookup_timeout],
    )
    result = PersistentDeleteService(Sessions(), gateway).delete_models(
        "admin", [MODEL_1, MODEL_2]
    )
    assert [item.status for item in result.items] == ["PREPARE_UNCERTAIN", "DELETED"]
    assert (result.deleted_count, result.uncertain_count, result.failed_count) == (1, 1, 0)
