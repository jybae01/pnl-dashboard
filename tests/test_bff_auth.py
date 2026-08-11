from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from forecast.bff import AccessCodeSessionService, ApiErrorCode, BffError


class Clock:
    def __init__(self) -> None:
        self.value = datetime(2026, 8, 11, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.value


def sessions(clock: Clock | None = None) -> AccessCodeSessionService:
    return AccessCodeSessionService(
        viewer_code="viewer-secret",
        admin_code="admin-secret",
        actor_namespace_secret="actor-namespace-secret-that-is-stable",
        ttl_seconds=60,
        clock=clock,
    )


def test_valid_viewer_and_admin_login_have_server_owned_roles():
    service = sessions()

    viewer = service.login("viewer-secret")
    admin = service.login("admin-secret")

    assert viewer.session.role == "viewer"
    assert admin.session.role == "admin"
    assert viewer.session_id != admin.session_id
    assert service.require_viewer(viewer.session_id).role == "viewer"
    assert service.require_admin(admin.session_id).role == "admin"


def test_bad_code_is_rejected_without_role_assertion():
    with pytest.raises(BffError) as caught:
        sessions().login("not-a-code")
    assert caught.value.code is ApiErrorCode.AUTH_REQUIRED


def test_expired_session_is_rejected_and_removed():
    clock = Clock()
    service = sessions(clock)
    ticket = service.login("viewer-secret")
    clock.value += timedelta(seconds=61)

    with pytest.raises(BffError) as caught:
        service.validate(ticket.session_id)
    assert caught.value.code is ApiErrorCode.AUTH_REQUIRED


def test_viewer_cannot_use_admin_capability():
    service = sessions()
    ticket = service.login("viewer-secret")

    with pytest.raises(BffError) as caught:
        service.require_admin(ticket.session_id)
    assert caught.value.code is ApiErrorCode.FORBIDDEN


def test_logout_invalidates_session_and_is_idempotent():
    service = sessions()
    ticket = service.login("admin-secret")

    service.logout(ticket.session_id)
    service.logout(ticket.session_id)

    with pytest.raises(BffError) as caught:
        service.validate(ticket.session_id)
    assert caught.value.code is ApiErrorCode.AUTH_REQUIRED


def test_malformed_session_is_rejected():
    with pytest.raises(BffError) as caught:
        sessions().validate("short")
    assert caught.value.code is ApiErrorCode.AUTH_REQUIRED


def test_canonical_v1_error_taxonomy_is_complete():
    assert {code.value for code in ApiErrorCode} == {
        "AUTH_REQUIRED",
        "FORBIDDEN",
        "VALIDATION_ERROR",
        "MODEL_NOT_FOUND",
        "IDEMPOTENCY_CONFLICT",
        "JOB_NOT_FOUND",
        "RESULT_NOT_FOUND",
        "RESULT_NOT_AVAILABLE",
        "INPUT_INTEGRITY_MISMATCH",
        "TRANSIENT_SYSTEM_ERROR",
    }


def test_idempotency_actor_is_stable_opaque_credential_principal():
    first = sessions().login("admin-secret")
    second_service = sessions()
    second = second_service.login("admin-secret")

    first_actor = sessions_for_ticket(first)
    second_actor = second_service.require_admin(second.session_id).actor_id
    assert first_actor == second_actor
    assert first_actor.startswith("access-code-v1:")
    assert "admin-secret" not in first_actor


def sessions_for_ticket(ticket):
    # Recreate with the same server-only actor namespace and validate a fresh
    # login; actor identity is the shared V1 credential, not a browser claim.
    service = sessions()
    replacement = service.login("admin-secret")
    return service.require_admin(replacement.session_id).actor_id
