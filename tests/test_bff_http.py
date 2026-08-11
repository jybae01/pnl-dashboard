from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import tempfile
from pathlib import Path
from io import BytesIO
from openpyxl import Workbook, load_workbook

import pytest
from fastapi.testclient import TestClient

from forecast.bff.application import (
    AnalysisModelListService,
    AnalysisSubmissionService,
    JobQueryService,
    ResultQueryService,
    TrustedBffApplication,
)
from forecast.bff.auth import AccessCodeSessionService
from forecast.bff.gateway import (
    GatewayIdempotencyConflictError,
    GatewayValidationError,
    SubmissionRecord,
)
from forecast.bff.http import HttpBffSettings, InMemoryLoginRateLimiter, create_http_bff
from forecast.bff.evidence_history import EvidenceArtifact
from forecast.analysis_export import MIME_XLSX
from forecast.provenance import ResultProvenance


BASE = "11111111-1111-4111-8111-111111111111"
COMP = "22222222-2222-4222-8222-222222222222"
JOB = "33333333-3333-4333-8333-333333333333"
RESULT = "44444444-4444-4444-8444-444444444444"
PROVENANCE = ResultProvenance("engine", "mapping", "a" * 64, "1")


class Gateway:
    def __init__(self):
        self.requests = {}
        self.job_status = "pending"
        self.available = True
        self.model_published = True

    def submit_analysis(self, **values):
        if not self.model_published:
            raise GatewayValidationError("analysis models must be published")
        key = (values["idempotency_actor"], values["idempotency_key"])
        fingerprint = tuple(values[name] for name in (
            "baseline_model_id", "comparison_model_id", "start_month", "end_month",
            "baseline_sales_fx", "comparison_sales_fx",
        ))
        if key in self.requests:
            if self.requests[key] != fingerprint:
                raise GatewayIdempotencyConflictError("collision")
            return SubmissionRecord(JOB, self.job_status, True)
        self.requests[key] = fingerprint
        return SubmissionRecord(JOB, self.job_status, False)

    def get_job_status(self, _job_id):
        return {
            "job_id": JOB, "status": self.job_status,
            "baseline_model_id": BASE, "comparison_model_id": COMP,
            "start_month": 1, "end_month": 6, "attempt": 1, "max_attempts": 3,
            "created_at": "2026-08-11T00:00:00Z", "heartbeat_at": None,
            "completed_at": "2026-08-11T00:01:00Z" if self.job_status == "completed" else None,
            "result_id": RESULT if self.job_status == "completed" else None,
            "error_code": "worker_execution_failed" if self.job_status == "failed" else None,
            "error_message": "SECRET postgres traceback / storage/path.xlsx",
            "claim_token": "must-never-leak", "queue_message_id": 99,
        }

    def get_admin_result_preview(self, _result_id):
        return result_row(is_published=False, published_at=None)

    def get_viewer_result(self, _result_id, **_kwargs):
        return result_row() if self.available else None

    def validate_result_availability(self, _result_id, **_kwargs):
        return self.available


def result_row(**overrides):
    row = {
        "result_id": RESULT, "job_id": JOB, "analysis_view": {"summary": {"status": "PASS"}},
        "baseline_model_id": BASE, "comparison_model_id": COMP,
        "baseline_workbook_sha256": "b" * 64, "comparison_workbook_sha256": "c" * 64,
        "engine_version": "engine", "mapping_version": "mapping", "mapping_hash": "a" * 64,
        "result_schema_version": "1", "is_published": True, "is_default": False,
        "published_at": "2026-08-11T00:01:00Z", "created_at": "2026-08-11T00:01:00Z",
    }
    row.update(overrides)
    return row


@dataclass
class Fixture:
    client: TestClient
    gateway: Gateway

    def login(self, code="admin-code"):
        response = self.client.post("/api/session/login", json={"access_code": code})
        assert response.status_code == 200
        return response

    @property
    def csrf(self):
        return self.client.cookies.get("pnl_csrf")


def make_fixture(*, limiter=None, clock=None) -> Fixture:
    sessions = AccessCodeSessionService(
        viewer_code="viewer-code", admin_code="admin-code",
        actor_namespace_secret="actor-namespace-secret-at-least-32-chars", ttl_seconds=3600,
        clock=clock,
    )
    gateway = Gateway()
    repository = SimpleNamespace(list=lambda: [
        SimpleNamespace(id=BASE, name="Base", model_type="PLAN", year=2026,
                        start_month=1, end_month=12, is_published=True,
                        is_default=True, workbook_sha256="b" * 64),
        SimpleNamespace(id=COMP, name="Comparison", model_type="ACTUAL", year=2026,
                        start_month=1, end_month=12, is_published=True,
                        is_default=False, workbook_sha256="c" * 64),
    ])
    app_service = TrustedBffApplication(
        sessions,
        AnalysisSubmissionService(sessions, gateway, PROVENANCE),
        JobQueryService(sessions, gateway),
        ResultQueryService(sessions, gateway, supported_result_schema_versions=("1",)),
        AnalysisModelListService(sessions, repository),
        evidence=FakeEvidence(),
        history=FakeHistory(),
        presentation=FakePresentation(),
        pnl_dashboard=FakePnlDashboard(),
        forecast_generation=FakeForecast(),
    )
    app = create_http_bff(
        app_service,
        settings=HttpBffSettings(environment="test", csrf_secret="csrf-secret-at-least-32-characters"),
        rate_limiter=limiter,
    )
    return Fixture(TestClient(app), gateway)


class FakeEvidence:
    last_root = None
    def admin_download(self, _session, result_id):
        return self._artifact(result_id)

    def viewer_download(self, _session, result_id):
        return self._artifact(result_id)

    @staticmethod
    def _artifact(result_id):
        root = Path(tempfile.mkdtemp(prefix="test-evidence-"))
        FakeEvidence.last_root = root
        path = root / "evidence.xlsx"
        workbook = Workbook()
        workbook.active["A1"] = result_id
        workbook.save(path)
        return EvidenceArtifact(path, f"손익분석_근거_{result_id[:8]}.xlsx", MIME_XLSX, root)


class FakePnlDashboard:
    def viewer_read(self, _session):
        return {"result_id": RESULT, "job_id": JOB, "dto_version": "1"}


class FakeForecast:
    def generate(self, _session, request):
        return {
            "generation_id": JOB, "model_id": COMP, "display_name": request.name,
            "model_year": request.model_year, "start_month": request.start_month,
            "end_month": request.end_month, "is_published": False, "is_default": False,
            "workbook_sha256": "d" * 64, "idempotency_replayed": False,
            "execution_mode": "SYNCHRONOUS", "dto_version": "1",
        }


class FakeHistory:
    def list_admin(self, _session, **_kwargs):
        return {
            "items": [{
                "job_id": JOB, "result_id": RESULT, "status": "COMPLETED",
                "baseline_model_id": BASE, "baseline_model_name": "Base",
                "comparison_model_id": COMP, "comparison_model_name": "Comparison",
                "start_month": 1, "end_month": 6, "attempt": 1, "max_attempts": 3,
                "created_at": "2026-08-11T00:00:00Z", "completed_at": "2026-08-11T00:01:00Z",
                "error_code": None, "error_message": None, "is_published": False,
            }],
            "next_before_created_at": None, "next_before_job_id": None, "dto_version": "1",
        }


class FakePresentation:
    def admin_read(self, _session, result_id):
        return {"identity": {"result_id": result_id}, "scope": "admin", "dto_version": "1"}

    def viewer_read(self, _session, result_id):
        return {"identity": {"result_id": result_id}, "scope": "viewer", "dto_version": "1"}


@pytest.mark.parametrize("code,role", [("viewer-code", "viewer"), ("admin-code", "admin")])
def test_login_issues_opaque_cookie_without_body_secret(code, role):
    fx = make_fixture()
    response = fx.login(code)
    assert response.json()["role"] == role and response.json()["authenticated"] is True
    assert "session_id" not in response.text and code not in response.text
    cookies = response.headers.get_list("set-cookie")
    assert any("pnl_session=" in value and "HttpOnly" in value and "SameSite=strict" in value for value in cookies)
    assert any("pnl_csrf=" in value and "HttpOnly" not in value for value in cookies)


def test_invalid_and_malformed_session_are_rejected_and_rate_limited_generically():
    limiter = InMemoryLoginRateLimiter(max_attempts=2, window_seconds=60)
    fx = make_fixture(limiter=limiter)
    assert fx.client.post("/api/session/login", json={"access_code": "bad"}).status_code == 401
    locked = fx.client.post("/api/session/login", json={"access_code": "bad2"})
    assert locked.status_code == 429 and "Retry-After" in locked.headers
    limited = fx.client.post("/api/session/login", json={"access_code": "admin-code"})
    assert limited.status_code == 429 and "Retry-After" in limited.headers
    fx.client.cookies.set("pnl_session", "short")
    assert fx.client.get("/api/session").status_code == 401


def test_expired_http_session_is_rejected():
    now = [datetime(2026, 8, 11, tzinfo=timezone.utc)]
    fx = make_fixture(clock=lambda: now[0]); fx.login()
    now[0] += timedelta(hours=2)
    assert fx.client.get("/api/session").status_code == 401


def test_csrf_logout_and_viewer_admin_capability_boundary():
    fx = make_fixture()
    fx.login("viewer-code")
    assert fx.client.get("/api/models").status_code == 403
    assert fx.client.post("/api/session/logout").status_code == 403
    assert fx.client.post("/api/session/logout", headers={"X-CSRF-Token": "wrong"}).status_code == 403
    assert fx.client.post("/api/session/logout", headers={"X-CSRF-Token": fx.csrf}).status_code == 200
    assert fx.client.get("/api/session").status_code == 401


def test_model_list_submit_idempotency_collision_and_unpublished_rejection():
    fx = make_fixture(); fx.login()
    assert len(fx.client.get("/api/models").json()["models"]) == 2
    body = {
        "baseline_model_id": BASE, "comparison_model_id": COMP,
        "start_month": 1, "end_month": 6,
        "baseline_sales_fx": 1480, "comparison_sales_fx": 1500,
        "idempotency_key": "logical-action-1",
    }
    assert fx.client.post("/api/analyses", json=body).status_code == 403
    assert fx.client.post("/api/analyses", json=body, headers={"X-CSRF-Token": "wrong"}).status_code == 403
    first = fx.client.post("/api/analyses", json=body, headers={"X-CSRF-Token": fx.csrf})
    replay = fx.client.post("/api/analyses", json=body, headers={"X-CSRF-Token": fx.csrf})
    assert first.status_code == replay.status_code == 200
    assert replay.json()["idempotency_replayed"] is True
    conflict = fx.client.post("/api/analyses", json={**body, "end_month": 7}, headers={"X-CSRF-Token": fx.csrf})
    assert conflict.status_code == 409 and conflict.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    fx.gateway.model_published = False
    denied = fx.client.post("/api/analyses", json={**body, "idempotency_key": "new"}, headers={"X-CSRF-Token": fx.csrf})
    assert denied.status_code == 422


@pytest.mark.parametrize("field,value", [("start_month", True), ("end_month", 13), ("baseline_sales_fx", True), ("comparison_sales_fx", 0)])
def test_submit_strict_validation(field, value):
    fx = make_fixture(); fx.login()
    body = {"baseline_model_id": BASE, "comparison_model_id": COMP, "start_month": 1,
            "end_month": 6, "baseline_sales_fx": 1480, "comparison_sales_fx": 1500,
            "idempotency_key": "validation"}
    response = fx.client.post("/api/analyses", json={**body, field: value}, headers={"X-CSRF-Token": fx.csrf})
    assert response.status_code == 422 and response.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.parametrize("status", ["pending", "processing", "completed", "failed"])
def test_job_by_id_states_and_internal_fields_never_leak(status):
    fx = make_fixture(); fx.login(); fx.gateway.job_status = status
    response = fx.client.get(f"/api/jobs/{JOB}")
    assert response.status_code == 200 and response.json()["status"] == status.upper()
    assert "claim_token" not in response.text and "queue_message_id" not in response.text
    assert "postgres" not in response.text and "storage/path" not in response.text


def test_admin_preview_and_strict_viewer_result_are_separate():
    admin = make_fixture(); admin.login()
    preview = admin.client.get(f"/api/admin/results/{RESULT}")
    assert preview.status_code == 200 and preview.json()["is_published"] is False

    viewer = make_fixture(); viewer.login("viewer-code")
    assert viewer.client.get(f"/api/admin/results/{RESULT}").status_code == 403
    assert viewer.client.get(f"/api/viewer/results/{RESULT}").status_code == 200
    viewer.gateway.available = False
    hidden = viewer.client.get(f"/api/viewer/results/{RESULT}")
    assert hidden.status_code == 404 and hidden.json()["error"]["code"] == "RESULT_NOT_AVAILABLE"


def test_presentation_http_routes_keep_admin_and_viewer_capabilities_separate():
    admin = make_fixture(); admin.login()
    preview = admin.client.get(f"/api/admin/results/{RESULT}/presentation")
    assert preview.status_code == 200 and preview.json()["scope"] == "admin"
    assert "claim_token" not in preview.text and "workbook_path" not in preview.text

    viewer = make_fixture(); viewer.login("viewer-code")
    assert viewer.client.get(f"/api/admin/results/{RESULT}/presentation").status_code == 403
    visible = viewer.client.get(f"/api/viewer/results/{RESULT}/presentation")
    assert visible.status_code == 200 and visible.json()["scope"] == "viewer"


def test_production_requires_secure_cookie_and_shared_rate_limiter():
    fx = make_fixture()
    with pytest.raises(ValueError, match="Secure"):
        HttpBffSettings(environment="production", csrf_secret="csrf-secret-at-least-32-characters")
    with pytest.raises(ValueError, match="shared login rate limiter"):
        create_http_bff(
            fx.client.app.state if False else make_application_only(),
            settings=HttpBffSettings(environment="production", cookie_secure=True, csrf_secret="csrf-secret-at-least-32-characters"),
        )


def make_application_only():
    sessions = AccessCodeSessionService(viewer_code="v", admin_code="a", actor_namespace_secret="x" * 32)
    gateway = Gateway()
    return TrustedBffApplication(
        sessions, AnalysisSubmissionService(sessions, gateway, PROVENANCE),
        JobQueryService(sessions, gateway), ResultQueryService(sessions, gateway, supported_result_schema_versions=("1",)),
    )


def test_evidence_http_streams_xlsx_and_history_is_admin_only():
    admin = make_fixture(); admin.login()
    evidence = admin.client.get(f"/api/admin/results/{RESULT}/evidence")
    assert evidence.status_code == 200
    assert evidence.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert "attachment" in evidence.headers["content-disposition"]
    assert evidence.content.startswith(b"PK")
    assert load_workbook(BytesIO(evidence.content)).active["A1"].value == RESULT
    assert FakeEvidence.last_root is not None and not FakeEvidence.last_root.exists()
    history = admin.client.get("/api/admin/calculation-history?limit=20")
    assert history.status_code == 200
    assert history.json()["items"][0]["result_id"] == RESULT
    assert "claim_token" not in history.text and "queue_message_id" not in history.text

    viewer = make_fixture(); viewer.login("viewer-code")
    assert viewer.client.get("/api/admin/calculation-history").status_code == 403
    assert viewer.client.get(f"/api/admin/results/{RESULT}/evidence").status_code == 403
    assert viewer.client.get(f"/api/viewer/results/{RESULT}/evidence").status_code == 200


def test_pnl_dashboard_is_viewer_capability_with_no_store_and_no_internal_fields():
    anonymous = make_fixture()
    assert anonymous.client.get("/api/viewer/pnl-dashboard").status_code == 401
    viewer = make_fixture(); viewer.login("viewer-code")
    response = viewer.client.get("/api/viewer/pnl-dashboard")
    assert response.status_code == 200
    assert response.headers["cache-control"].startswith("no-store")
    assert response.json() == {"result_id": RESULT, "job_id": JOB, "dto_version": "1"}
    assert "claim_token" not in response.text and "storage_path" not in response.text


def test_forecast_http_is_admin_csrf_protected_and_returns_only_safe_draft_dto():
    body = {
        "base_model_id": BASE, "name": "2026 Forecast", "model_year": 2026,
        "version": "V1", "start_month": 7, "end_month": 7,
        "months": [{"month": 7, "sales": [], "production": []}],
        "idempotency_key": "forecast-key",
    }
    anonymous = make_fixture()
    assert anonymous.client.post("/api/admin/forecasts", json=body).status_code == 401
    viewer = make_fixture(); viewer.login("viewer-code")
    assert viewer.client.post("/api/admin/forecasts", json=body,
        headers={"X-CSRF-Token": viewer.csrf}).status_code == 403
    admin = make_fixture(); admin.login()
    assert admin.client.post("/api/admin/forecasts", json=body).status_code == 403
    response = admin.client.post("/api/admin/forecasts", json=body,
        headers={"X-CSRF-Token": admin.csrf})
    assert response.status_code == 200
    assert response.json()["is_published"] is False
    assert response.json()["is_default"] is False
    assert "workbook_path" not in response.text and "service_role" not in response.text
