from __future__ import annotations

import hashlib
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from forecast.benchmark import benchmark_forecast
from forecast.bff.auth import AccessCodeSessionService
from forecast.bff.errors import ApiErrorCode, BffError
from forecast.bff.production import SupabaseLoginRateLimiter, SupabaseSessionStore, TrustedProxyPolicy
from forecast.bff.http import HttpBffSettings
from forecast.bff.http_factory import _proxy_cidrs, create_http_bff_from_environment
from forecast.parser_isolation import IsolatedExcelPreflight, IsolatedParserError
from forecast.temp_artifacts import TempArtifactPolicy
from forecast.bff.evidence_history import _escape_workbook_text


class _Call:
    def __init__(self, fn): self.fn = fn
    def execute(self): return SimpleNamespace(data=self.fn())


class SharedRpcState:
    """One transactional backing state reached by independent adapter instances."""
    def __init__(self):
        self.sessions = {}; self.failures = {}; self.lock = threading.RLock()

    def rpc(self, name, payload):
        def execute():
            with self.lock:
                if name == "create_bff_session":
                    self.sessions[payload["p_session_digest"]] = dict(
                        session_ref=payload["p_session_ref"], principal_id=payload["p_principal_id"],
                        session_role=payload["p_role"],
                        expires_at=(datetime.now(timezone.utc)+timedelta(seconds=payload["p_ttl_seconds"])).isoformat(),
                        revoked=False)
                    return None
                if name == "get_bff_session":
                    row = self.sessions.get(payload["p_session_digest"])
                    if not row or row["revoked"] or datetime.fromisoformat(row["expires_at"]) <= datetime.now(timezone.utc):
                        return []
                    return [{key: value for key, value in row.items() if key != "revoked"}]
                if name == "revoke_bff_session":
                    if payload["p_session_digest"] in self.sessions:
                        self.sessions[payload["p_session_digest"]]["revoked"] = True
                    return None
                key = payload["p_client_key"]
                state = self.failures.setdefault(key, {"count": 0, "locked": False})
                if name == "check_bff_login_lockout":
                    return [{"allowed": not state["locked"], "retry_after_seconds": 60 if state["locked"] else 0}]
                if name == "record_bff_login_failure":
                    state["count"] += 1; state["locked"] = state["count"] >= payload["p_max_attempts"]
                    return [{"allowed": not state["locked"], "retry_after_seconds": 60 if state["locked"] else 0}]
                if name == "clear_bff_login_failures":
                    self.failures.pop(key, None); return None
                raise AssertionError(name)
        return _Call(execute)


def _service(store):
    return AccessCodeSessionService(
        viewer_code="viewer-secret", admin_code="admin-secret",
        actor_namespace_secret="a" * 32, store=store, ttl_seconds=3600,
    )


def test_shared_session_cross_instance_login_logout_and_unknown_malformed():
    state = SharedRpcState()
    instance_a = _service(SupabaseSessionStore(state))
    instance_b = _service(SupabaseSessionStore(state))
    ticket = instance_a.login("admin-secret")
    assert instance_b.require_admin(ticket.session_id).session_ref.startswith("session-v1:")
    assert ticket.session_id not in repr(state.sessions)
    instance_b.logout(ticket.session_id)
    with pytest.raises(BffError) as revoked:
        instance_a.validate(ticket.session_id)
    assert revoked.value.code is ApiErrorCode.AUTH_REQUIRED
    for token in ("short", "x" * 43):
        with pytest.raises(BffError): instance_a.validate(token)


def test_shared_session_expiry_is_database_authoritative():
    state = SharedRpcState()
    service = _service(SupabaseSessionStore(state))
    ticket = service.login("viewer-secret")
    digest = hashlib.sha256(ticket.session_id.encode("ascii")).hexdigest()
    state.sessions[digest]["expires_at"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    with pytest.raises(BffError) as expired:
        service.validate(ticket.session_id)
    assert expired.value.code is ApiErrorCode.AUTH_REQUIRED


def test_shared_lockout_accumulates_across_instances_and_clears_atomically():
    state = SharedRpcState()
    first = SupabaseLoginRateLimiter(state, max_attempts=3, window_seconds=60)
    second = SupabaseLoginRateLimiter(state, max_attempts=3, window_seconds=60)
    key = hashlib.sha256(b"client").hexdigest()
    assert first.check(key) == (True, 0)
    first.record_failure(key); second.record_failure(key); first.record_failure(key)
    assert second.check(key)[0] is False
    second.record_success(key)
    assert first.check(key) == (True, 0)


def test_shared_lockout_concurrent_failures_reach_one_global_threshold():
    state = SharedRpcState()
    first = SupabaseLoginRateLimiter(state, max_attempts=4, window_seconds=60)
    second = SupabaseLoginRateLimiter(state, max_attempts=4, window_seconds=60)
    key = hashlib.sha256(b"parallel-client").hexdigest()
    threads = [threading.Thread(target=limiter.record_failure, args=(key,))
               for limiter in (first, second, first, second)]
    for thread in threads: thread.start()
    for thread in threads: thread.join()
    assert first.check(key)[0] is False


def test_trusted_proxy_headers_cannot_spoof_untrusted_peer_and_chain_is_bounded():
    policy = TrustedProxyPolicy.from_cidrs(["10.0.0.0/8"])
    assert policy.client_ip("203.0.113.8", {"x-forwarded-for": "198.51.100.2"}) == "203.0.113.8"
    assert policy.client_ip("10.1.2.3", {"x-forwarded-for": "198.51.100.2, 10.2.3.4"}) == "198.51.100.2"
    assert policy.client_ip("10.1.2.3", {"x-forwarded-for": "garbage"}) == "10.1.2.3"


def test_production_origin_proxy_and_backend_selection_fail_closed(monkeypatch):
    with pytest.raises(ValueError, match="explicit http"):
        HttpBffSettings(environment="production", cookie_secure=True,
                        csrf_secret="x" * 32, allowed_origins=("null",))
    monkeypatch.setenv("BFF_PROXY_MODE", "trusted")
    monkeypatch.delenv("BFF_TRUSTED_PROXY_CIDRS", raising=False)
    with pytest.raises(RuntimeError, match="trusted proxy"):
        _proxy_cidrs("production")
    monkeypatch.setenv("PNL_REPOSITORY_BACKEND", "local")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "must-not-select-backend")
    with pytest.raises(RuntimeError, match="PNL_REPOSITORY_BACKEND=supabase"):
        create_http_bff_from_environment()


def test_temp_orphan_sweep_is_owned_dry_run_and_idempotent(tmp_path: Path):
    policy = TempArtifactPolicy(tmp_path, 64 * 1024 * 1024, orphan_age_seconds=10)
    owned = tmp_path / "pnl-model-old.xlsx"; owned.write_bytes(b"x")
    unrelated = tmp_path / "keep.txt"; unrelated.write_bytes(b"safe")
    old = time.time() - 20; os.utime(owned, (old, old))
    assert policy.sweep(dry_run=True)[0]["deleted"] is False and owned.exists()
    assert policy.sweep(dry_run=False)[0]["deleted"] is True and not owned.exists()
    assert policy.sweep(dry_run=False) == [] and unrelated.exists()


def test_benchmark_labels_fixture_and_reports_1_6_12_without_claiming_golden(tmp_path: Path):
    source = tmp_path / "base.xlsx"; source.write_bytes(b"base")
    mapping = tmp_path / "mapping.json"; mapping.write_text("{}", encoding="utf-8")
    def runner(src, _mapping, months, root):
        (root / "forecast.xlsx").write_bytes(src.read_bytes() + bytes([months]))
    values = [benchmark_forecast(source, mapping, months=month, runner=runner) for month in (1, 6, 12)]
    assert [value.months for value in values] == [1, 6, 12]
    assert all(value.fixture_class == "synthetic_or_fixture" and value.output_bytes == 5 for value in values)


def test_evidence_text_formula_injection_is_escaped_without_changing_numbers():
    value = _escape_workbook_text({"label": "=HYPERLINK(\"https://evil\")", "amount": 12.5,
                                   "rows": [{"note": "+cmd"}, {"note": "safe"}]})
    assert value["label"].startswith("'=") and value["rows"][0]["note"] == "'+cmd"
    assert value["amount"] == 12.5 and value["rows"][1]["note"] == "safe"


def _hanging_worker(*_args):
    time.sleep(5)


def _crashing_worker(*_args):
    raise RuntimeError("boom")


@pytest.mark.parametrize("target,code,timeout", [
    (_hanging_worker, "workbook_resource_timeout", 1),
    (_crashing_worker, "workbook_parser_crashed", 10),
])
def test_parser_timeout_and_crash_are_contained(tmp_path: Path, target, code, timeout):
    source = tmp_path / "source.xlsx"; source.write_bytes(b"not-an-xlsx")
    isolated = IsolatedExcelPreflight({}, timeout_seconds=timeout, worker_target=target)
    with pytest.raises(IsolatedParserError, match=code):
        isolated.require_with_metadata(source, expected_year=2026)


def test_migration_012_is_private_fixed_search_path_and_redacts_sensitive_audit():
    text = (Path(__file__).parents[1] / "supabase/migrations/202608090012_production_hardening_foundation.sql").read_text(encoding="utf-8").lower()
    for table in ("bff_sessions", "bff_login_lockouts", "bff_audit_events", "forecast_execution_permits", "bff_runtime_limits"):
        assert f"alter table public.{table} enable row level security" in text
        assert f"revoke all on table public.{table} from public, anon, authenticated, service_role" in text
    for name in ("create_bff_session", "get_bff_session", "record_bff_login_failure",
                 "append_bff_audit_event", "acquire_forecast_execution_permit"):
        body = text.split(f"function public.{name}", 1)[1].split("$$;", 1)[0]
        assert "security definer set search_path = ''" in body
        assert f"grant execute on function public.{name}" in text
        assert f"revoke all on function public.{name}" in text
    assert "revoke create on schema public from public, anon, authenticated" in text
    assert "'claim_token'" in text and "'error_detail'" in text
    for sensitive_column in ("'result'", "'content'", "'regional_sales_monthly'",
                             "'tariff_adjustment_monthly'", "'workbook_path'"):
        assert sensitive_column in text
    assert "calculation_jobs_analysis_request_size_limit" in text
    assert "heartbeat_model_ingestion" in text
    assert "renew_forecast_execution_permit" in text
    assert "raw session" not in text
