from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from forecast.bff.application import TrustedBffApplication
from forecast.bff.auth import AccessCodeSessionService
from forecast.bff.dto import (
    AdminModelListResponse,
    AdminModelResponse,
    ModelPublicationResponse,
    ModelUploadResponse,
)
from forecast.bff.http import HttpBffSettings, create_http_bff
from forecast.bff.model_ingestion import MAX_WORKBOOK_BYTES


MODEL_ID = "11111111-1111-4111-8111-111111111111"
SHA = "a" * 64


def model(*, published=False):
    return AdminModelResponse(
        model_id=MODEL_ID, display_name="Actual", model_type="ACTUAL", model_year=2026,
        start_month=1, end_month=12, version="V1", file_name="actual.xlsx",
        workbook_sha256=SHA, has_workbook_sha256=True,
        is_published=published, is_default=False,
        uploaded_at="2026-08-11T00:00:00Z",
    )


class Management:
    def list_models(self, _session):
        return AdminModelListResponse(models=(model(),))


class Ingestion:
    def __init__(self):
        self.path = None
        self.path_existed_during_call = False

    def ingest(self, _session, request, source):
        self.path = Path(source)
        self.path_existed_during_call = self.path.is_file()
        assert request.file_name == "actual.xlsx"
        return ModelUploadResponse(model=model(), idempotency_replayed=False)


class Publication:
    def set_publication(self, _session, _model_id, **values):
        assert values == {"is_published": True, "is_default": False}
        return ModelPublicationResponse(model=model(published=True))


def fixture():
    sessions = AccessCodeSessionService(
        viewer_code="viewer", admin_code="admin",
        actor_namespace_secret="stable-actor-namespace-secret-32chars", ttl_seconds=3600,
    )
    ingestion = Ingestion()
    application = TrustedBffApplication(
        sessions=sessions,
        submissions=object(), jobs=object(), results=object(),
        model_management=Management(), model_ingestion=ingestion,
        model_publication=Publication(),
    )
    app = create_http_bff(
        application,
        settings=HttpBffSettings(environment="test", csrf_secret="csrf-secret-at-least-32-characters"),
    )
    return TestClient(app), ingestion


def login(client, code="admin"):
    response = client.post("/api/session/login", json={"access_code": code})
    assert response.status_code == 200
    return client.cookies.get("pnl_csrf")


def fields():
    return {
        "name": "Actual", "model_type": "ACTUAL", "model_year": "2026",
        "version": "V1", "idempotency_key": "upload-1",
    }


def test_admin_multipart_upload_uses_csrf_safe_dto_and_cleans_temp_file():
    client, ingestion = fixture()
    csrf = login(client)
    response = client.post(
        "/api/admin/models", data=fields(),
        files={"file": ("actual.xlsx", b"exact-upload-bytes", "application/octet-stream")},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 200
    assert response.json()["model"]["is_published"] is False
    assert "workbook_path" not in response.text and "pnl-models" not in response.text
    assert ingestion.path_existed_during_call is True
    assert ingestion.path is not None and not ingestion.path.exists()


def test_upload_requires_admin_and_csrf_and_rejects_non_xlsx():
    client, _ = fixture()
    response = client.post("/api/admin/models", data=fields(), files={"file": ("actual.xlsx", b"x")})
    assert response.status_code == 401
    csrf = login(client, "viewer")
    denied = client.post(
        "/api/admin/models", data=fields(), files={"file": ("actual.xlsx", b"x")},
        headers={"X-CSRF-Token": csrf},
    )
    assert denied.status_code == 403

    client, _ = fixture(); login(client)
    csrf = client.cookies.get("pnl_csrf")
    missing_csrf = client.post(
        "/api/admin/models", data=fields(), files={"file": ("actual.xlsx", b"x")}
    )
    assert missing_csrf.status_code == 403
    invalid = client.post(
        "/api/admin/models", data=fields(), files={"file": ("actual.csv", b"x")},
        headers={"X-CSRF-Token": csrf},
    )
    assert invalid.status_code == 422


def test_declared_oversize_is_rejected_before_multipart_application_handler():
    client, ingestion = fixture(); csrf = login(client)
    response = client.post(
        "/api/admin/models", data=fields(), files={"file": ("actual.xlsx", b"x")},
        headers={"X-CSRF-Token": csrf, "Content-Length": str(MAX_WORKBOOK_BYTES + 1024 * 1024 + 1)},
    )
    assert response.status_code == 413, response.text
    assert ingestion.path is None


def test_chunked_upload_is_capped_before_multipart_application_handler():
    client, ingestion = fixture(); csrf = login(client)

    def oversized_chunks():
        yield (
            b"--bounded-upload\r\n"
            b'Content-Disposition: form-data; name="file"; filename="actual.xlsx"\r\n'
            b"Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet\r\n\r\n"
        )
        for _ in range(52):
            yield b"x" * (1024 * 1024)
        yield b"\r\n--bounded-upload--\r\n"

    response = client.post(
        "/api/admin/models",
        content=oversized_chunks(),
        headers={
            "X-CSRF-Token": csrf,
            "Content-Type": "multipart/form-data; boundary=bounded-upload",
        },
    )
    assert response.status_code == 413, response.text
    assert ingestion.path is None


def test_management_list_and_publication_are_admin_only_and_publication_is_csrf_protected():
    client, _ = fixture(); csrf = login(client)
    listed = client.get("/api/admin/models")
    assert listed.status_code == 200 and listed.json()["models"][0]["is_published"] is False
    published = client.post(
        f"/api/admin/models/{MODEL_ID}/publication",
        json={"is_published": True, "is_default": False},
        headers={"X-CSRF-Token": csrf},
    )
    assert published.status_code == 200 and published.json()["model"]["is_published"] is True
    no_csrf = client.post(
        f"/api/admin/models/{MODEL_ID}/publication",
        json={"is_published": True, "is_default": False},
    )
    assert no_csrf.status_code == 403
