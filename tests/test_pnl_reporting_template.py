from __future__ import annotations

import hashlib

import pytest
from fastapi.testclient import TestClient

from forecast.bff.application import TrustedBffApplication
from forecast.bff.auth import AccessCodeSessionService
from forecast.bff.errors import ApiErrorCode, BffError
from forecast.bff.factory import create_supabase_bff_application
from forecast.bff.http import HttpBffSettings, create_http_bff
from forecast.bff.pnl_reporting_template import (
    PNL_REPORTING_TEMPLATE_FILENAME,
    PNL_REPORTING_TEMPLATE_MEDIA_TYPE,
    PNL_REPORTING_TEMPLATE_RESOURCE,
    PNL_REPORTING_TEMPLATE_SHA256,
    PNL_REPORTING_TEMPLATE_SIZE,
    PnlReportingTemplateIntegrityError,
    PnlReportingTemplateService,
)
from forecast.provenance import ResultProvenance
from forecast.reporting import TEMPLATE_VERSION


APPROVED_SHA256 = "c11b72c7f4bb29cea6a5a626f354fab6d3ac38c82c6c726658e739faf8b37e3b"
INTEGRITY_ERROR = "P&L Reporting template resource integrity check failed"


def _sessions() -> AccessCodeSessionService:
    return AccessCodeSessionService(
        viewer_code="viewer-code",
        admin_code="admin-code",
        actor_namespace_secret="stable-template-actor-namespace-secret",
    )


def _client(template_service=None, *, raise_server_exceptions=True) -> TestClient:
    sessions = _sessions()
    application = TrustedBffApplication(
        sessions=sessions,
        submissions=object(),
        jobs=object(),
        results=object(),
        pnl_reporting_template=(
            template_service if template_service is not None
            else PnlReportingTemplateService(sessions)
        ),
    )
    return TestClient(
        create_http_bff(
            application,
            settings=HttpBffSettings(
                environment="test",
                csrf_secret="csrf-secret-at-least-32-characters",
            ),
        ),
        raise_server_exceptions=raise_server_exceptions,
    )


def _login(client: TestClient, code: str = "admin-code") -> None:
    response = client.post("/api/session/login", json={"access_code": code})
    assert response.status_code == 200


def test_approved_resource_and_service_are_exact_immutable_bytes():
    assert PNL_REPORTING_TEMPLATE_FILENAME == "PNL_REPORTING_TEMPLATE_V1.xlsx"
    assert TEMPLATE_VERSION == "PNL_REPORTING_V1"
    assert PNL_REPORTING_TEMPLATE_SIZE == 20_686
    assert PNL_REPORTING_TEMPLATE_SHA256 == APPROVED_SHA256
    assert PNL_REPORTING_TEMPLATE_RESOURCE.name == PNL_REPORTING_TEMPLATE_FILENAME
    assert PNL_REPORTING_TEMPLATE_RESOURCE.is_file()

    content = PNL_REPORTING_TEMPLATE_RESOURCE.read_bytes()
    assert len(content) == PNL_REPORTING_TEMPLATE_SIZE
    assert hashlib.sha256(content).hexdigest() == APPROVED_SHA256

    sessions = _sessions()
    service = PnlReportingTemplateService(sessions)
    admin = sessions.login("admin-code")
    artifact = service.admin_download(admin.session_id)
    assert artifact.content == content
    assert artifact.filename == PNL_REPORTING_TEMPLATE_FILENAME
    assert artifact.media_type == PNL_REPORTING_TEMPLATE_MEDIA_TYPE
    assert artifact.size == PNL_REPORTING_TEMPLATE_SIZE
    assert artifact.sha256 == APPROVED_SHA256
    assert service.admin_download(admin.session_id) is artifact

    viewer = sessions.login("viewer-code")
    with pytest.raises(BffError) as denied:
        service.admin_download(viewer.session_id)
    assert denied.value.code is ApiErrorCode.FORBIDDEN


def test_factory_wires_the_fail_closed_template_capability():
    application = create_supabase_bff_application(
        supabase_client=object(),
        viewer_code="viewer-code",
        admin_code="admin-code",
        actor_namespace_secret="stable-template-actor-namespace-secret",
        provenance=ResultProvenance("engine", "mapping", "a" * 64, "1"),
    )
    assert isinstance(application.pnl_reporting_template, PnlReportingTemplateService)


def test_admin_get_without_csrf_returns_exact_private_artifact():
    client = _client()
    _login(client)

    response = client.get("/api/admin/pnl-reporting/template")

    assert response.status_code == 200
    assert response.headers["content-type"] == PNL_REPORTING_TEMPLATE_MEDIA_TYPE
    assert response.headers["content-disposition"] == (
        'attachment; filename="PNL_REPORTING_TEMPLATE_V1.xlsx"; '
        "filename*=utf-8''PNL_REPORTING_TEMPLATE_V1.xlsx"
    )
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert len(response.content) == 20_686
    assert hashlib.sha256(response.content).hexdigest() == APPROVED_SHA256
    assert response.content == PNL_REPORTING_TEMPLATE_RESOURCE.read_bytes()


def test_template_get_requires_admin_but_not_csrf():
    anonymous = _client()
    response = anonymous.get("/api/admin/pnl-reporting/template")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == ApiErrorCode.AUTH_REQUIRED.value

    viewer = _client()
    _login(viewer, "viewer-code")
    response = viewer.get("/api/admin/pnl-reporting/template")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == ApiErrorCode.FORBIDDEN.value

    admin = _client()
    _login(admin)
    assert admin.cookies.get("pnl_csrf")
    # The authenticated GET succeeds without sending the CSRF header.
    assert admin.get("/api/admin/pnl-reporting/template").status_code == 200


@pytest.mark.parametrize("failure", ["missing", "wrong_size", "wrong_sha"])
def test_missing_wrong_size_and_wrong_sha_fail_closed_at_construction(tmp_path, failure):
    approved = PNL_REPORTING_TEMPLATE_RESOURCE.read_bytes()
    candidate = tmp_path / "private-resource-location" / PNL_REPORTING_TEMPLATE_FILENAME
    if failure != "missing":
        candidate.parent.mkdir()
        if failure == "wrong_size":
            candidate.write_bytes(approved[:-1])
        else:
            candidate.write_bytes(bytes([approved[0] ^ 1]) + approved[1:])

    with pytest.raises(PnlReportingTemplateIntegrityError) as raised:
        PnlReportingTemplateService(_sessions(), resource_path=candidate)

    assert str(raised.value) == INTEGRITY_ERROR
    assert str(candidate) not in str(raised.value)
    if candidate.exists():
        assert hashlib.sha256(candidate.read_bytes()).hexdigest() not in str(raised.value)


def test_relative_resource_override_is_rejected_without_cwd_lookup():
    with pytest.raises(PnlReportingTemplateIntegrityError) as raised:
        PnlReportingTemplateService(
            _sessions(),
            resource_path=PNL_REPORTING_TEMPLATE_FILENAME,
        )
    assert str(raised.value) == INTEGRITY_ERROR


def test_unexpected_runtime_failure_does_not_leak_internal_path_or_hash(tmp_path):
    secret_path = str(tmp_path / "private" / PNL_REPORTING_TEMPLATE_FILENAME)
    secret_hash = "f" * 64

    class FailingTemplateService:
        def admin_download(self, _session_id):
            raise RuntimeError(f"{secret_path} actual_sha={secret_hash}")

    client = _client(FailingTemplateService(), raise_server_exceptions=False)
    _login(client)
    response = client.get("/api/admin/pnl-reporting/template")

    assert response.status_code == 500
    assert response.json()["error"]["code"] == ApiErrorCode.TRANSIENT_SYSTEM_ERROR.value
    assert secret_path not in response.text
    assert secret_hash not in response.text
    assert "traceback" not in response.text.casefold()
