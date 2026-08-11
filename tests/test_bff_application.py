from __future__ import annotations

import threading
from dataclasses import asdict

import pytest

from forecast.bff import (
    AccessCodeSessionService,
    AnalysisSubmissionService,
    AnalysisSubmitRequest,
    ApiErrorCode,
    BffError,
    JobQueryService,
    ResultQueryService,
    SubmissionRecord,
)
from forecast.bff.gateway import GatewayIdempotencyConflictError, GatewayTransientError
from forecast.provenance import ResultProvenance


BASE_ID = "11111111-1111-4111-8111-111111111111"
COMPARISON_ID = "22222222-2222-4222-8222-222222222222"
RESULT_ID = "33333333-3333-4333-8333-333333333333"
JOB_ID = "44444444-4444-4444-8444-444444444444"
PROVENANCE = ResultProvenance("engine-2", "mapping-2", "c" * 64, "1")


def make_sessions():
    service = AccessCodeSessionService(
        viewer_code="viewer-secret",
        admin_code="admin-secret",
        actor_namespace_secret="stable-server-only-actor-namespace",
        ttl_seconds=3600,
    )
    return service, service.login("admin-secret"), service.login("viewer-secret")


def request(**overrides):
    values = {
        "baseline_model_id": BASE_ID,
        "comparison_model_id": COMPARISON_ID,
        "start_month": 1,
        "end_month": 6,
        "baseline_sales_fx": 1480.0,
        "comparison_sales_fx": 1500.0,
        "idempotency_key": "analysis-2026-01",
    }
    values.update(overrides)
    return AnalysisSubmitRequest(**values)


class InMemoryGateway:
    def __init__(self):
        self._lock = threading.Lock()
        self.jobs = {}
        self.created = 0
        self.job_row = None
        self.result_row = None
        self.availability = {
            "result_published": True,
            "base_published": True,
            "comparison_published": True,
            "sha_match": True,
            "mapping_valid": True,
            "provenance_match": True,
        }

    def submit_analysis(self, **values):
        key = (values["idempotency_actor"], values["idempotency_key"])
        fingerprint = tuple(
            values[name]
            for name in (
                "baseline_model_id", "comparison_model_id", "start_month", "end_month",
                "baseline_sales_fx", "comparison_sales_fx", "provenance", "max_attempts",
            )
        )
        with self._lock:
            existing = self.jobs.get(key)
            if existing:
                if existing[0] != fingerprint:
                    raise GatewayIdempotencyConflictError("collision")
                return SubmissionRecord(JOB_ID, "pending", True)
            self.jobs[key] = (fingerprint, JOB_ID)
            self.created += 1
            return SubmissionRecord(JOB_ID, "pending", False)

    def get_job_status(self, _job_id):
        return self.job_row

    def get_admin_result_preview(self, _result_id):
        return self.result_row

    def get_viewer_result(self, _result_id, **_kwargs):
        return self.result_row if all(self.availability.values()) else None

    def validate_result_availability(self, _result_id, **_kwargs):
        return self.result_row is not None and all(self.availability.values())


class TimeoutAfterCommitGateway(InMemoryGateway):
    def __init__(self):
        super().__init__()
        self.timeout_once = True

    def submit_analysis(self, **values):
        record = super().submit_analysis(**values)
        if self.timeout_once:
            self.timeout_once = False
            raise GatewayTransientError("response lost")
        return record


def result_row(**overrides):
    row = {
        "result_id": RESULT_ID,
        "job_id": JOB_ID,
        "analysis_view": {"summary": {"status": "PASS"}},
        "baseline_model_id": BASE_ID,
        "comparison_model_id": COMPARISON_ID,
        "baseline_workbook_sha256": "a" * 64,
        "comparison_workbook_sha256": "b" * 64,
        "engine_version": "engine-2",
        "mapping_version": "mapping-2",
        "mapping_hash": "c" * 64,
        "result_schema_version": "1",
        "is_published": True,
        "is_default": False,
        "published_at": "2026-08-11T00:00:00+00:00",
        "created_at": "2026-08-11T00:00:00+00:00",
    }
    row.update(overrides)
    return row


def test_first_submit_creates_and_replay_returns_same_job():
    sessions, admin, _viewer = make_sessions()
    gateway = InMemoryGateway()
    service = AnalysisSubmissionService(sessions, gateway, PROVENANCE)

    first = service.submit(admin.session_id, request())
    second = service.submit(admin.session_id, request())

    assert first.job_id == second.job_id == JOB_ID
    assert first.idempotency_replayed is False
    assert second.idempotency_replayed is True
    assert gateway.created == 1


def test_same_key_different_payload_is_explicit_conflict():
    sessions, admin, _viewer = make_sessions()
    service = AnalysisSubmissionService(sessions, InMemoryGateway(), PROVENANCE)
    service.submit(admin.session_id, request())

    with pytest.raises(BffError) as caught:
        service.submit(admin.session_id, request(end_month=7))
    assert caught.value.code is ApiErrorCode.IDEMPOTENCY_CONFLICT


def test_timeout_after_commit_then_retry_returns_original_job():
    sessions, admin, _viewer = make_sessions()
    gateway = TimeoutAfterCommitGateway()
    service = AnalysisSubmissionService(sessions, gateway, PROVENANCE)

    with pytest.raises(BffError) as caught:
        service.submit(admin.session_id, request())
    assert caught.value.code is ApiErrorCode.TRANSIENT_SYSTEM_ERROR

    replay = service.submit(admin.session_id, request())
    assert replay.job_id == JOB_ID and replay.idempotency_replayed
    assert gateway.created == 1


def test_concurrent_duplicate_attempt_creates_one_job():
    sessions, admin, _viewer = make_sessions()
    gateway = InMemoryGateway()
    service = AnalysisSubmissionService(sessions, gateway, PROVENANCE)
    responses = []

    threads = [
        threading.Thread(
            target=lambda: responses.append(service.submit(admin.session_id, request()))
        )
        for _ in range(8)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert gateway.created == 1
    assert {item.job_id for item in responses} == {JOB_ID}
    assert sum(not item.idempotency_replayed for item in responses) == 1


@pytest.mark.parametrize("field,value", [
    ("baseline_model_id", "not-uuid"),
    ("comparison_model_id", BASE_ID),
    ("start_month", 0),
    ("end_month", 13),
    ("baseline_sales_fx", 0),
    ("comparison_sales_fx", float("nan")),
    ("idempotency_key", None),
])
def test_submit_validation_rejects_invalid_contract(field, value):
    sessions, admin, _viewer = make_sessions()
    service = AnalysisSubmissionService(sessions, InMemoryGateway(), PROVENANCE)

    with pytest.raises(BffError) as caught:
        service.submit(admin.session_id, request(**{field: value}))
    assert caught.value.code is ApiErrorCode.VALIDATION_ERROR


def test_job_by_id_all_states_and_no_internal_fields():
    sessions, admin, _viewer = make_sessions()
    gateway = InMemoryGateway()
    service = JobQueryService(sessions, gateway)
    for status in ("pending", "processing", "completed", "failed"):
        gateway.job_row = {
            "job_id": JOB_ID,
            "status": status,
            "baseline_model_id": BASE_ID,
            "comparison_model_id": COMPARISON_ID,
            "start_month": 1,
            "end_month": 6,
            "attempt": 1,
            "max_attempts": 3,
            "created_at": "2026-08-11T00:00:00+00:00",
            "heartbeat_at": None,
            "completed_at": None,
            "result_id": RESULT_ID if status == "completed" else None,
            "error_code": "worker_execution_failed" if status == "failed" else None,
            "claim_token": "must-not-leak",
            "queue_message_id": 99,
        }
        response = service.get_by_id(admin.session_id, JOB_ID)
        exposed = asdict(response)
        assert response.status == status.upper()
        assert "claim_token" not in exposed and "queue_message_id" not in exposed


def test_job_not_found_and_viewer_forbidden():
    sessions, admin, viewer = make_sessions()
    service = JobQueryService(sessions, InMemoryGateway())
    with pytest.raises(BffError) as missing:
        service.get_by_id(admin.session_id, JOB_ID)
    assert missing.value.code is ApiErrorCode.JOB_NOT_FOUND
    with pytest.raises(BffError) as forbidden:
        service.get_by_id(viewer.session_id, JOB_ID)
    assert forbidden.value.code is ApiErrorCode.FORBIDDEN


def test_admin_can_preview_unpublished_completed_result():
    sessions, admin, _viewer = make_sessions()
    gateway = InMemoryGateway()
    gateway.result_row = result_row(is_published=False, published_at=None)

    response = ResultQueryService(
        sessions, gateway, supported_result_schema_versions=("1",)
    ).admin_preview(admin.session_id, RESULT_ID)

    assert response.result_id == RESULT_ID
    assert response.is_published is False


def test_viewer_can_read_only_currently_available_published_result():
    sessions, _admin, viewer = make_sessions()
    gateway = InMemoryGateway()
    gateway.result_row = result_row()
    service = ResultQueryService(sessions, gateway, supported_result_schema_versions=("1",))

    assert service.validate_result_availability(viewer.session_id, RESULT_ID)
    assert service.viewer_read(viewer.session_id, RESULT_ID).result_id == RESULT_ID


@pytest.mark.parametrize("condition", [
    "result_published",
    "base_published",
    "comparison_published",
    "sha_match",
    "mapping_valid",
    "provenance_match",
])
def test_viewer_rejects_each_unavailable_condition(condition):
    sessions, _admin, viewer = make_sessions()
    gateway = InMemoryGateway()
    gateway.result_row = result_row()
    gateway.availability[condition] = False
    service = ResultQueryService(sessions, gateway, supported_result_schema_versions=("1",))

    assert service.validate_result_availability(viewer.session_id, RESULT_ID) is False
    with pytest.raises(BffError) as caught:
        service.viewer_read(viewer.session_id, RESULT_ID)
    assert caught.value.code is ApiErrorCode.RESULT_NOT_AVAILABLE


def test_base_republished_with_valid_provenance_restores_visibility():
    sessions, _admin, viewer = make_sessions()
    gateway = InMemoryGateway()
    gateway.result_row = result_row()
    gateway.availability["base_published"] = False
    service = ResultQueryService(sessions, gateway, supported_result_schema_versions=("1",))
    assert not service.validate_result_availability(viewer.session_id, RESULT_ID)

    gateway.availability["base_published"] = True
    assert service.validate_result_availability(viewer.session_id, RESULT_ID)
    assert service.viewer_read(viewer.session_id, RESULT_ID).result_id == RESULT_ID


def test_invalid_or_nonexistent_result_is_not_returned():
    sessions, admin, viewer = make_sessions()
    gateway = InMemoryGateway()
    service = ResultQueryService(sessions, gateway, supported_result_schema_versions=("1",))
    with pytest.raises(BffError) as missing:
        service.admin_preview(admin.session_id, RESULT_ID)
    assert missing.value.code is ApiErrorCode.RESULT_NOT_FOUND
    with pytest.raises(BffError) as unavailable:
        service.viewer_read(viewer.session_id, RESULT_ID)
    assert unavailable.value.code is ApiErrorCode.RESULT_NOT_AVAILABLE

    gateway.result_row = result_row(analysis_view="invalid")
    with pytest.raises(BffError) as invalid:
        service.admin_preview(admin.session_id, RESULT_ID)
    assert invalid.value.code is ApiErrorCode.INPUT_INTEGRITY_MISMATCH


def test_unsupported_result_schema_is_rejected_for_admin_and_viewer():
    sessions, admin, viewer = make_sessions()
    gateway = InMemoryGateway()
    gateway.result_row = result_row(result_schema_version="2")
    service = ResultQueryService(sessions, gateway, supported_result_schema_versions=("1",))

    with pytest.raises(BffError) as admin_error:
        service.admin_preview(admin.session_id, RESULT_ID)
    assert admin_error.value.code is ApiErrorCode.INPUT_INTEGRITY_MISMATCH
    with pytest.raises(BffError) as viewer_error:
        service.viewer_read(viewer.session_id, RESULT_ID)
    assert viewer_error.value.code is ApiErrorCode.INPUT_INTEGRITY_MISMATCH
