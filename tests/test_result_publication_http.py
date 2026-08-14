from __future__ import annotations

from dataclasses import dataclass, field

import pytest
from fastapi.testclient import TestClient

from forecast.bff.application import ResultPublicationService, TrustedBffApplication
from forecast.bff.auth import AccessCodeSessionService
from forecast.bff.gateway import GatewayTransientError, SupabaseBffApplicationGateway
from forecast.persistence.supabase import SupabaseResultPublicationRepository
from forecast.bff.http import HttpBffSettings, create_http_bff


RESULT_ID = "44444444-4444-4444-8444-444444444444"
CSRF_SECRET = "csrf-secret-at-least-32-characters"


@dataclass
class PublicationRepository:
    row: dict[str, object] | None = None
    error: Exception | None = None
    calls: list[tuple[str, bool, bool]] = field(default_factory=list)

    def set_publication(self, result_id: str, *, is_published: bool, is_default: bool = False):
        self.calls.append((result_id, is_published, is_default))
        if self.error is not None:
            raise self.error
        if self.row is None:
            raise KeyError(result_id)
        return dict(self.row)


def fixture(repository: PublicationRepository) -> TestClient:
    sessions = AccessCodeSessionService(
        viewer_code="viewer-code",
        admin_code="admin-code",
        actor_namespace_secret="actor-namespace-secret-at-least-32-chars",
        ttl_seconds=3600,
    )
    application = TrustedBffApplication(
        sessions=sessions,
        submissions=object(),
        jobs=object(),
        results=object(),
        result_publication=ResultPublicationService(sessions, repository),
    )
    return TestClient(
        create_http_bff(
            application,
            settings=HttpBffSettings(environment="test", csrf_secret=CSRF_SECRET),
        )
    )


def login(client: TestClient, code: str = "admin-code") -> str:
    response = client.post("/api/session/login", json={"access_code": code})
    assert response.status_code == 200, response.text
    csrf = client.cookies.get("pnl_csrf")
    assert csrf
    return csrf


def test_admin_result_publication_returns_narrow_metadata_and_forwards_flags():
    repository = PublicationRepository(row={
        "id": RESULT_ID,
        "is_published": True,
        "is_default": True,
        "published_at": "2026-08-14T00:00:00+00:00",
        "result": {"secret": "must-not-cross-boundary"},
        "engine_version": "internal-engine",
        "workbook_path": "models/secret/source.xlsx",
    })
    client = fixture(repository)
    csrf = login(client)

    response = client.post(
        f"/api/admin/results/{RESULT_ID}/publication",
        json={"is_published": True, "is_default": True},
        headers={"X-CSRF-Token": csrf},
    )

    assert response.status_code == 200, response.text
    assert response.json() == {
        "result_id": RESULT_ID,
        "is_published": True,
        "is_default": True,
        "published_at": "2026-08-14T00:00:00+00:00",
        "dto_version": "1",
    }
    assert repository.calls == [(RESULT_ID, True, True)]
    assert "secret" not in response.text
    assert "workbook_path" not in response.text
    assert "engine_version" not in response.text


def test_result_publication_rejects_rpc_state_that_does_not_match_requested_flags():
    repository = PublicationRepository(row={
        "id": RESULT_ID,
        "is_published": False,
        "is_default": False,
        "published_at": None,
    })
    client = fixture(repository)
    csrf = login(client)
    response = client.post(
        f"/api/admin/results/{RESULT_ID}/publication",
        json={"is_published": True, "is_default": False},
        headers={"X-CSRF-Token": csrf},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INPUT_INTEGRITY_MISMATCH"


def test_result_publication_is_admin_and_csrf_protected():
    repository = PublicationRepository(row={
        "id": RESULT_ID,
        "is_published": True,
        "is_default": False,
        "published_at": "2026-08-14T00:00:00+00:00",
    })
    client = fixture(repository)
    assert client.post(
        f"/api/admin/results/{RESULT_ID}/publication",
        json={"is_published": True, "is_default": False},
    ).status_code == 401

    viewer_csrf = login(client, "viewer-code")
    denied = client.post(
        f"/api/admin/results/{RESULT_ID}/publication",
        json={"is_published": True, "is_default": False},
        headers={"X-CSRF-Token": viewer_csrf},
    )
    assert denied.status_code == 403

    admin = fixture(repository)
    login(admin)
    missing_csrf = admin.post(
        f"/api/admin/results/{RESULT_ID}/publication",
        json={"is_published": True, "is_default": False},
    )
    assert missing_csrf.status_code == 403


def test_default_result_requires_publication_without_calling_repository():
    repository = PublicationRepository(row={
        "id": RESULT_ID,
        "is_published": False,
        "is_default": False,
        "published_at": None,
    })
    client = fixture(repository)
    csrf = login(client)
    response = client.post(
        f"/api/admin/results/{RESULT_ID}/publication",
        json={"is_published": False, "is_default": True},
        headers={"X-CSRF-Token": csrf},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert response.json()["error"]["field_errors"] == {"is_default": "requires_published"}
    assert repository.calls == []


def test_publication_errors_are_safe_and_distinguish_not_found_from_integrity():
    missing = PublicationRepository()
    client = fixture(missing)
    csrf = login(client)
    response = client.post(
        f"/api/admin/results/{RESULT_ID}/publication",
        json={"is_published": True, "is_default": False},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RESULT_NOT_FOUND"

    broken = PublicationRepository(error=RuntimeError("postgres secret / storage/path.xlsx"))
    client = fixture(broken)
    csrf = login(client)
    response = client.post(
        f"/api/admin/results/{RESULT_ID}/publication",
        json={"is_published": True, "is_default": False},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INPUT_INTEGRITY_MISMATCH"
    assert "postgres" not in response.text
    assert "storage/path" not in response.text


def test_unpublish_response_keeps_default_false_and_timestamp_null():
    repository = PublicationRepository(row={
        "id": RESULT_ID,
        "is_published": False,
        "is_default": False,
        "published_at": None,
    })
    client = fixture(repository)
    csrf = login(client)
    response = client.post(
        f"/api/admin/results/{RESULT_ID}/publication",
        json={"is_published": False, "is_default": False},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 200
    assert response.json()["is_published"] is False
    assert response.json()["is_default"] is False
    assert response.json()["published_at"] is None
    assert repository.calls == [(RESULT_ID, False, False)]


class _RpcResponse:
    def __init__(self, data):
        self.data = data

    def execute(self):
        return self


class _HistoryQuery:
    def __init__(self, client):
        self.client = client

    def select(self, fields):
        self.client.table_select = fields
        return self

    def in_(self, field, values):
        self.client.table_filter = (field, list(values))
        return self

    def execute(self):
        return _RpcResponse(self.client.table_rows)


class _HistoryClient:
    def __init__(self):
        self.table_rows = [{
            "id": RESULT_ID,
            "is_default": True,
            "published_at": "2026-08-14T00:00:00+00:00",
        }]
        self.table_select = None
        self.table_filter = None

    def rpc(self, name, _params):
        assert name == "list_calculation_history_admin"
        return _RpcResponse([{
            "job_id": "33333333-3333-4333-8333-333333333333",
            "result_id": RESULT_ID,
            "status": "completed",
            "baseline_model_id": "11111111-1111-4111-8111-111111111111",
            "baseline_model_name": "Base",
            "comparison_model_id": "22222222-2222-4222-8222-222222222222",
            "comparison_model_name": "Comparison",
            "start_month": 7,
            "end_month": 7,
            "attempt": 1,
            "max_attempts": 3,
            "created_at": "2026-08-14T00:00:00+00:00",
            "completed_at": "2026-08-14T00:01:00+00:00",
            "error_code": None,
            "error_message": None,
            "is_published": True,
        }])

    def table(self, name):
        assert name == "calculation_results"
        return _HistoryQuery(self)


def test_history_batch_enrichment_reads_default_and_timestamp_without_n_plus_one():
    client = _HistoryClient()
    rows = SupabaseBffApplicationGateway(client).list_calculation_history(
        limit=25,
        before_created_at=None,
        before_job_id=None,
    )

    assert rows[0]["is_published"] is True
    assert rows[0]["is_default"] is True
    assert rows[0]["published_at"] == "2026-08-14T00:00:00+00:00"
    assert client.table_select == "id,is_default,published_at"
    assert client.table_filter == ("id", [RESULT_ID])


def test_history_batch_enrichment_fails_closed_when_result_metadata_is_missing():
    client = _HistoryClient()
    client.table_rows = []
    with pytest.raises(GatewayTransientError, match="missing result"):
        SupabaseBffApplicationGateway(client).list_calculation_history(
            limit=25,
            before_created_at=None,
            before_job_id=None,
        )


class _PublicationRpcClient:
    def __init__(self):
        self.calls: list[tuple[str, dict[str, object]]] = []

    def rpc(self, name, params):
        self.calls.append((name, params))
        return _RpcResponse([{
            "id": RESULT_ID,
            "is_published": True,
            "is_default": True,
            "published_at": "2026-08-14T00:00:00+00:00",
        }])


def test_supabase_result_repository_uses_existing_publication_rpc_without_payload_access():
    client = _PublicationRpcClient()
    row = SupabaseResultPublicationRepository(client).set_publication(
        RESULT_ID,
        is_published=True,
        is_default=True,
    )
    assert row["id"] == RESULT_ID
    assert client.calls == [(
        "set_calculation_result_publication",
        {
            "p_result_id": RESULT_ID,
            "p_is_published": True,
            "p_is_default": True,
        },
    )]
