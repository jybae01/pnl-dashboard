from forecast_dashboard.security import (
    clear_login_failures,
    load_credentials,
    lockout_remaining,
    register_failed_attempt,
    verify_access_code,
)


def test_roles_are_verified():
    credentials = load_credentials(
        {"VIEWER_CODE": "viewer-code-123", "ADMIN_CODE": "admin-code-4567"}
    )
    assert verify_access_code("viewer-code-123", credentials) == "viewer"
    assert verify_access_code("admin-code-4567", credentials) == "admin"
    assert verify_access_code("wrong", credentials) is None


def test_lockout_after_five_failures():
    session = {}
    for _ in range(5):
        register_failed_attempt(session, now=100.0)
    assert lockout_remaining(session, now=100.0) == 30
    clear_login_failures(session)
    assert lockout_remaining(session, now=100.0) == 0
