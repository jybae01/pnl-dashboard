from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from .auth import SessionPrincipal


def _data(response: Any) -> Any:
    if hasattr(response, "data"):
        return response.data
    if isinstance(response, Mapping):
        return response.get("data", response)
    return response


def _one(response: Any) -> Mapping[str, Any] | None:
    value = _data(response)
    if isinstance(value, list):
        return value[0] if value else None
    return value if isinstance(value, Mapping) else None


class SupabaseSessionStore:
    """Shared session persistence through narrow service-role-only RPCs."""

    shared = True

    def __init__(self, client: Any) -> None:
        self._client = client

    def create(self, token_digest: str, principal: SessionPrincipal, ttl_seconds: int) -> None:
        self._client.rpc("create_bff_session", {
            "p_session_digest": token_digest,
            "p_session_ref": principal.session_ref,
            "p_principal_id": principal.actor_id,
            "p_role": principal.role,
            "p_ttl_seconds": ttl_seconds,
        }).execute()

    def get(self, token_digest: str, now: datetime) -> SessionPrincipal | None:
        del now  # Database time is authoritative across BFF instances.
        row = _one(self._client.rpc("get_bff_session", {
            "p_session_digest": token_digest,
        }).execute())
        if row is None:
            return None
        expires = datetime.fromisoformat(str(row["expires_at"]).replace("Z", "+00:00"))
        if expires.tzinfo is None:
            raise RuntimeError("shared session expiry is not timezone-aware")
        return SessionPrincipal(
            role=str(row["session_role"]),
            actor_id=str(row["principal_id"]),
            session_ref=str(row["session_ref"]),
            expires_at=expires.astimezone(timezone.utc),
        )

    def revoke(self, token_digest: str, now: datetime) -> None:
        del now
        self._client.rpc("revoke_bff_session", {
            "p_session_digest": token_digest,
        }).execute()


class SupabaseLoginRateLimiter:
    """Atomic shared login lockout state. Client keys are server-side digests."""

    shared = True

    def __init__(self, client: Any, *, max_attempts: int, window_seconds: int) -> None:
        self._client = client
        self._max_attempts = max_attempts
        self._window_seconds = window_seconds

    def check(self, client_key: str) -> tuple[bool, int]:
        row = _one(self._client.rpc("check_bff_login_lockout", {
            "p_client_key": client_key,
        }).execute())
        return _lockout_result(row)

    def record_failure(self, client_key: str) -> tuple[bool, int]:
        row = _one(self._client.rpc("record_bff_login_failure", {
            "p_client_key": client_key,
            "p_max_attempts": self._max_attempts,
            "p_window_seconds": self._window_seconds,
        }).execute())
        return _lockout_result(row)

    def record_success(self, client_key: str) -> None:
        self._client.rpc("clear_bff_login_failures", {"p_client_key": client_key}).execute()


def _lockout_result(row: Mapping[str, Any] | None) -> tuple[bool, int]:
    if row is None:
        raise RuntimeError("login lockout RPC returned no state")
    return bool(row.get("allowed")), max(0, int(row.get("retry_after_seconds") or 0))


@dataclass(frozen=True)
class TrustedProxyPolicy:
    """Resolve a rate-limit identity without trusting attacker-supplied headers."""

    trusted_networks: tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...] = ()
    forwarded_header: str = "x-forwarded-for"

    @classmethod
    def from_cidrs(cls, values: Sequence[str], *, forwarded_header: str = "x-forwarded-for") -> "TrustedProxyPolicy":
        if forwarded_header.lower() not in {"x-forwarded-for", "forwarded"}:
            raise ValueError("forwarded header must be x-forwarded-for or forwarded")
        networks = tuple(ipaddress.ip_network(value.strip(), strict=False) for value in values if value.strip())
        if any(network.prefixlen == 0 for network in networks):
            raise ValueError("trusted proxy networks must not cover the entire address space")
        return cls(networks, forwarded_header.lower())

    def client_ip(self, peer: str | None, headers: Mapping[str, str]) -> str:
        peer_ip = _ip(peer)
        if peer_ip is None:
            return "unknown"
        if not self._trusted(peer_ip):
            return peer_ip.compressed
        raw = headers.get(self.forwarded_header)
        chain = _forwarded_chain(raw, self.forwarded_header)
        if not chain:
            return peer_ip.compressed
        addresses = [_ip(value) for value in chain]
        if any(value is None for value in addresses):
            return peer_ip.compressed
        for value in reversed(addresses):
            assert value is not None
            if not self._trusted(value):
                return value.compressed
        return addresses[0].compressed  # all hops are explicitly trusted

    def _trusted(self, value: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
        return any(value in network for network in self.trusted_networks)


def _ip(value: str | None):
    try:
        return ipaddress.ip_address(str(value).strip())
    except ValueError:
        return None


def _forwarded_chain(raw: str | None, header: str) -> list[str]:
    if not raw or len(raw) > 2048:
        return []
    if header == "x-forwarded-for":
        return [part.strip() for part in raw.split(",") if part.strip()][:16]
    values: list[str] = []
    for element in raw.split(","):
        for part in element.split(";"):
            name, separator, value = part.strip().partition("=")
            if separator and name.lower() == "for":
                cleaned = value.strip().strip('"').strip("[]")
                if cleaned and not cleaned.startswith("_"):
                    values.append(cleaned.rsplit(":", 1)[0] if cleaned.count(":") == 1 else cleaned)
    return values[:16]


class AuditSink:
    shared = False

    def record(self, **event: Any) -> None:
        del event


class SupabaseAuditSink(AuditSink):
    shared = True

    def __init__(self, client: Any) -> None:
        self._client = client

    def record(self, **event: Any) -> None:
        self._client.rpc("append_bff_audit_event", {
            "p_event_type": event.get("event_type"),
            "p_principal_id": event.get("principal_id"),
            "p_role": event.get("role"),
            "p_session_ref": event.get("session_ref"),
            "p_correlation_id": event.get("correlation_id"),
            "p_operation_type": event.get("operation_type"),
            "p_operation_id": event.get("operation_id"),
            "p_outcome": event.get("outcome"),
            "p_error_code": event.get("error_code"),
        }).execute()
