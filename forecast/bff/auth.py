from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable

from .dto import SessionResponse, SessionTicket
from .errors import ApiErrorCode, BffError


@dataclass(frozen=True)
class SessionPrincipal:
    role: str
    actor_id: str
    expires_at: datetime


class AccessCodeSessionService:
    """Server-only V1 access-code verifier and revocable opaque session store.

    The default store is intentionally process-local. A multi-instance BFF must
    supply a shared session implementation in a later deployment goal; process
    restart safely invalidates every session rather than accepting stale state.
    """

    def __init__(
        self,
        *,
        viewer_code: str,
        admin_code: str,
        actor_namespace_secret: str,
        ttl_seconds: int = 8 * 60 * 60,
        clock: Callable[[], datetime] | None = None,
        token_factory: Callable[[], str] | None = None,
    ) -> None:
        if not viewer_code or not admin_code:
            raise ValueError("VIEWER_CODE and ADMIN_CODE are required")
        if viewer_code == admin_code:
            raise ValueError("VIEWER_CODE and ADMIN_CODE must be different")
        if not isinstance(actor_namespace_secret, str) or len(actor_namespace_secret) < 32:
            raise ValueError("actor namespace secret must contain at least 32 characters")
        if ttl_seconds < 60:
            raise ValueError("session ttl must be at least 60 seconds")
        self._viewer_digest = self._digest(viewer_code)
        self._admin_digest = self._digest(admin_code)
        self._actor_secret = actor_namespace_secret.encode("utf-8")
        self._ttl = timedelta(seconds=ttl_seconds)
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._token_factory = token_factory or (lambda: secrets.token_urlsafe(32))
        self._sessions: dict[bytes, SessionPrincipal] = {}
        self._lock = threading.RLock()

    @staticmethod
    def _digest(value: str) -> bytes:
        return hashlib.sha256(value.encode("utf-8")).digest()

    def login(self, access_code: str) -> SessionTicket:
        if not isinstance(access_code, str) or not access_code:
            raise BffError(ApiErrorCode.AUTH_REQUIRED, "Invalid access code")
        candidate = self._digest(access_code)
        admin_match = hmac.compare_digest(candidate, self._admin_digest)
        viewer_match = hmac.compare_digest(candidate, self._viewer_digest)
        if not admin_match and not viewer_match:
            raise BffError(ApiErrorCode.AUTH_REQUIRED, "Invalid access code")

        role = "admin" if admin_match else "viewer"
        now = self._now()
        expires_at = now + self._ttl
        session_id = self._token_factory()
        if not isinstance(session_id, str) or len(session_id) < 32:
            raise RuntimeError("session token generator returned an unsafe identifier")
        token_digest = self._digest(session_id)
        principal = SessionPrincipal(
            role=role,
            actor_id=self._actor_id(role),
            expires_at=expires_at,
        )
        with self._lock:
            self._purge_expired(now)
            if token_digest in self._sessions:
                raise RuntimeError("session token generator returned a duplicate identifier")
            self._sessions[token_digest] = principal
        return SessionTicket(
            session_id=session_id,
            session=SessionResponse(role=role, expires_at=expires_at.isoformat()),
        )

    def validate(self, session_id: str) -> SessionResponse:
        principal = self._require_session(session_id)
        return SessionResponse(
            role=principal.role,
            expires_at=principal.expires_at.isoformat(),
        )

    def logout(self, session_id: str) -> None:
        token_digest = self._session_digest(session_id)
        with self._lock:
            self._sessions.pop(token_digest, None)

    def require_viewer(self, session_id: str) -> SessionPrincipal:
        principal = self._require_session(session_id)
        if principal.role not in {"viewer", "admin"}:
            raise BffError(ApiErrorCode.FORBIDDEN, "Viewer capability required")
        return principal

    def require_admin(self, session_id: str) -> SessionPrincipal:
        principal = self._require_session(session_id)
        if principal.role != "admin":
            raise BffError(ApiErrorCode.FORBIDDEN, "Admin capability required")
        return principal

    def _require_session(self, session_id: str) -> SessionPrincipal:
        token_digest = self._session_digest(session_id)
        now = self._now()
        with self._lock:
            principal = self._sessions.get(token_digest)
            if principal is None:
                raise BffError(ApiErrorCode.AUTH_REQUIRED, "Authentication required")
            if principal.expires_at <= now:
                del self._sessions[token_digest]
                raise BffError(ApiErrorCode.AUTH_REQUIRED, "Session expired")
            return principal

    def _session_digest(self, session_id: str) -> bytes:
        if not isinstance(session_id, str) or not 32 <= len(session_id) <= 512:
            raise BffError(ApiErrorCode.AUTH_REQUIRED, "Authentication required")
        return self._digest(session_id)

    def _actor_id(self, role: str) -> str:
        digest = hmac.new(
            self._actor_secret,
            f"access-code-v1:{role}".encode("ascii"),
            hashlib.sha256,
        ).hexdigest()
        return f"access-code-v1:{digest}"

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None:
            raise RuntimeError("session clock must return a timezone-aware datetime")
        return value.astimezone(timezone.utc)

    def _purge_expired(self, now: datetime) -> None:
        expired = [key for key, value in self._sessions.items() if value.expires_at <= now]
        for key in expired:
            del self._sessions[key]
