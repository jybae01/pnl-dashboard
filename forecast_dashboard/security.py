"""Authentication helpers kept independent from the Streamlit UI."""

from __future__ import annotations

import hashlib
import hmac
import time
from dataclasses import dataclass
from typing import Mapping


MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_SECONDS = 30


class SecretConfigurationError(RuntimeError):
    """Raised when required authentication secrets are missing or unsafe."""


@dataclass(frozen=True)
class AccessCredentials:
    viewer_hash: str
    admin_hash: str


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _credential_hash(secrets: Mapping[str, object], role: str) -> str:
    hash_key = f"{role}_CODE_SHA256"
    plain_key = f"{role}_CODE"
    configured_hash = str(secrets.get(hash_key, "")).strip().lower()
    if configured_hash:
        if len(configured_hash) != 64 or any(c not in "0123456789abcdef" for c in configured_hash):
            raise SecretConfigurationError(f"{hash_key} must be a SHA-256 hex digest.")
        return configured_hash

    plain_code = str(secrets.get(plain_key, ""))
    if len(plain_code) < 12:
        raise SecretConfigurationError(
            f"Configure {hash_key}, or set {plain_key} to at least 12 characters."
        )
    return _sha256(plain_code)


def load_credentials(secrets: Mapping[str, object]) -> AccessCredentials:
    credentials = AccessCredentials(
        viewer_hash=_credential_hash(secrets, "VIEWER"),
        admin_hash=_credential_hash(secrets, "ADMIN"),
    )
    if hmac.compare_digest(credentials.viewer_hash, credentials.admin_hash):
        raise SecretConfigurationError("Viewer and admin credentials must be different.")
    return credentials


def verify_access_code(code: str, credentials: AccessCredentials) -> str | None:
    candidate = _sha256(code)
    viewer_match = hmac.compare_digest(candidate, credentials.viewer_hash)
    admin_match = hmac.compare_digest(candidate, credentials.admin_hash)
    if admin_match:
        return "admin"
    if viewer_match:
        return "viewer"
    return None


def lockout_remaining(session: Mapping[str, object], now: float | None = None) -> int:
    current = time.time() if now is None else now
    locked_until = float(session.get("login_locked_until", 0.0) or 0.0)
    return max(0, int(locked_until - current + 0.999))


def register_failed_attempt(session: dict[str, object], now: float | None = None) -> None:
    current = time.time() if now is None else now
    attempts = int(session.get("login_attempts", 0) or 0) + 1
    if attempts >= MAX_LOGIN_ATTEMPTS:
        session["login_attempts"] = 0
        session["login_locked_until"] = current + LOCKOUT_SECONDS
    else:
        session["login_attempts"] = attempts


def clear_login_failures(session: dict[str, object]) -> None:
    session["login_attempts"] = 0
    session["login_locked_until"] = 0.0
