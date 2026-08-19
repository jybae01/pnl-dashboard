from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

from fastapi.testclient import TestClient

from forecast.bff.application import TrustedBffApplication
from forecast.bff.auth import AccessCodeSessionService
from forecast.bff.errors import ApiErrorCode, BffError
from forecast.bff.http import HttpBffSettings, create_http_bff
from forecast.bff.pnl_reporting_ingestion import (
    PnlReportingUploadResponse,
    PnlReportingValidationFailure,
)
from forecast.reporting import DatasetType


class Ingestion:
    def __init__(self):
        self.calls = []
        self.paths = []

    def ingest(self, session, request, source):
        path = Path(source)
        self.paths.append(path)
        assert path.is_file()
        payload = path.read_bytes()
        self.calls.append((session, request, payload))
        if request.actual_through_month is not None and not 1 <= request.actual_through_month <= 12:
            raise BffError(
                ApiErrorCode.VALIDATION_ERROR,
                "P&L Reporting upload request is invalid",
                field_errors={"actual_through_month": "must be an integer from 1 to 12"},
            )
        if request.original_filename in {"invalid.xlsx", "future.xlsx"}:
            code = (
                "ACTUAL_FUTURE_VALUE_PRESENT"
                if request.original_filename == "future.xlsx"
                else "PLAN_MONTH_MISSING"
            )
            raise PnlReportingValidationFailure({
                "status": "INVALID",
                "errorCount": 1,
                "warningCount": 0,
                "truncated": False,
                "errors": [{
                    "severity": "BLOCKING",
                    "errorCode": code,
                    "sheet": "01_월별손익",
                    "rowKey": "rev_product",
                    "month": 7 if code == "ACTUAL_FUTURE_VALUE_PRESENT" else 1,
                    "message": "Workbook 값이 입력 계약과 일치하지 않습니다.",
                }],
                "warnings": [],
            })
        replayed = request.idempotency_key == "replay"
        return PnlReportingUploadResponse(
            dataset_id=str(uuid.uuid5(uuid.NAMESPACE_URL, request.idempotency_key)),
            dataset_type=request.dataset_type,
            reporting_year=request.reporting_year,
            actual_through_month=request.actual_through_month,
            template_version="PNL_REPORTING_V1",
            source_sha256=hashlib.sha256(payload).hexdigest(),
            uploaded_at="2026-08-19T00:00:00+00:00",
            warnings=(),
            superseded_dataset_id=None,
            replayed=replayed,
        )


def fixture():
    sessions = AccessCodeSessionService(
        viewer_code="viewer",
        admin_code="admin",
        actor_namespace_secret="stable-actor-namespace-secret-32chars",
        ttl_seconds=3600,
    )
    ingestion = Ingestion()
    application = TrustedBffApplication(
        sessions=sessions,
        submissions=object(),
        jobs=object(),
        results=object(),
        pnl_reporting_ingestion=ingestion,
    )
    app = create_http_bff(
        application,
        settings=HttpBffSettings(
            environment="test",
            csrf_secret="csrf-secret-at-least-32-characters",
        ),
    )
    return TestClient(app), ingestion


def login(client, code="admin"):
    response = client.post("/api/session/login", json={"access_code": code})
    assert response.status_code == 200
    return client.cookies.get("pnl_csrf")


def post_plan(client, csrf, *, name="plan.xlsx", key="plan-1", fields=None):
    data = {"reporting_year": "2026", "idempotency_key": key}
    data.update(fields or {})
    return client.post(
        "/api/admin/pnl-reporting/plan",
        data=data,
        files={"file": (name, b"plan-source", "application/octet-stream")},
        headers={"X-CSRF-Token": csrf} if csrf else {},
    )


def post_actual(client, csrf, *, name="actual.xlsx", key="actual-1", through="6"):
    data = {
        "reporting_year": "2026",
        "actual_through_month": through,
        "idempotency_key": key,
    }
    return client.post(
        "/api/admin/pnl-reporting/actual",
        data=data,
        files={"file": (name, b"actual-source", "application/octet-stream")},
        headers={"X-CSRF-Token": csrf} if csrf else {},
    )


def test_plan_and_actual_admin_uploads_are_explicit_201_contracts_and_clean_temp_files():
    client, ingestion = fixture()
    csrf = login(client)
    plan = post_plan(client, csrf)
    actual = post_actual(client, csrf)
    assert plan.status_code == 201 and actual.status_code == 201
    assert plan.json()["datasetType"] == "PLAN"
    assert plan.json()["actualThroughMonth"] is None
    assert actual.json()["datasetType"] == "ACTUAL"
    assert actual.json()["actualThroughMonth"] == 6
    assert plan.json()["replayed"] is False
    assert "source_path" not in plan.text and "pnl-models" not in plan.text
    assert [call[1].dataset_type for call in ingestion.calls] == [
        DatasetType.PLAN,
        DatasetType.ACTUAL,
    ]
    assert all(not path.exists() for path in ingestion.paths)


def test_completed_replay_returns_200_without_exposing_private_storage_provenance():
    client, _ = fixture()
    csrf = login(client)
    response = post_plan(client, csrf, key="replay")
    assert response.status_code == 200
    assert response.json()["replayed"] is True
    assert "reporting/" not in response.text and "pnl-models" not in response.text


def test_uploads_require_admin_session_and_csrf():
    client, ingestion = fixture()
    assert post_plan(client, None).status_code == 401
    viewer_csrf = login(client, "viewer")
    assert post_plan(client, viewer_csrf).status_code == 403

    client, ingestion = fixture()
    login(client)
    assert post_plan(client, None).status_code == 403
    assert ingestion.calls == []


def test_plan_rejects_actual_through_field_instead_of_ignoring_it():
    client, ingestion = fixture()
    csrf = login(client)
    response = post_plan(client, csrf, fields={"actual_through_month": "6"})
    assert response.status_code == 422
    assert response.json()["error"]["field_errors"] == {
        "actual_through_month": "must not be provided for PLAN"
    }
    assert ingestion.calls == []
    empty = post_plan(client, csrf, fields={"actual_through_month": ""}, key="empty-through")
    assert empty.status_code == 422
    assert ingestion.calls == []


def test_actual_through_is_required_and_must_be_one_to_twelve():
    client, _ = fixture()
    csrf = login(client)
    missing = client.post(
        "/api/admin/pnl-reporting/actual",
        data={"reporting_year": "2026", "idempotency_key": "actual"},
        files={"file": ("actual.xlsx", b"actual-source")},
        headers={"X-CSRF-Token": csrf},
    )
    assert missing.status_code == 422
    assert post_actual(client, csrf, through="0", key="zero-through").status_code == 422
    assert post_actual(client, csrf, through="13", key="late-through").status_code == 422
    assert post_actual(client, csrf, through="6", key="valid-through").status_code == 201


def test_structured_validation_response_is_safe_and_exact():
    client, ingestion = fixture()
    csrf = login(client)
    response = post_plan(client, csrf, name="invalid.xlsx")
    assert response.status_code == 422
    assert response.json() == {
        "status": "INVALID",
        "errorCount": 1,
        "warningCount": 0,
        "truncated": False,
        "errors": [{
            "severity": "BLOCKING",
            "errorCode": "PLAN_MONTH_MISSING",
            "sheet": "01_월별손익",
            "rowKey": "rev_product",
            "month": 1,
            "message": "Workbook 값이 입력 계약과 일치하지 않습니다.",
        }],
        "warnings": [],
    }
    assert "traceback" not in response.text.lower()
    assert "source_path" not in response.text and "pnl-models" not in response.text
    assert len(ingestion.calls) == 1


def test_actual_future_value_is_422_while_zero_actual_value_is_accepted():
    client, _ = fixture()
    csrf = login(client)
    future = post_actual(client, csrf, name="future.xlsx", key="future", through="6")
    zero = post_actual(client, csrf, name="zero.xlsx", key="zero-value", through="6")
    assert future.status_code == 422
    assert future.json()["errors"][0]["errorCode"] == "ACTUAL_FUTURE_VALUE_PRESENT"
    assert zero.status_code == 201


def test_template_endpoint_remains_deferred():
    client, _ = fixture()
    csrf = login(client)
    assert client.get("/api/admin/pnl-reporting/template").status_code == 404
    assert csrf
