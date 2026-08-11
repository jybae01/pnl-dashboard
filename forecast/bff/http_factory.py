from __future__ import annotations

import os
import json
from pathlib import Path

from fastapi import FastAPI

from ..persistence.factory import create_repository_bundle
from ..provenance import load_registered_provenance
from .factory import create_supabase_bff_application
from .http import HttpBffSettings, LoginRateLimiter, create_http_bff
from .production import (
    SupabaseAuditSink, SupabaseLoginRateLimiter, SupabaseSessionStore, TrustedProxyPolicy,
)
from ..temp_artifacts import configure_temp_artifacts
from ..parser_isolation import IsolatedExcelPreflight
from ..logging_config import configure_structured_logging


def create_http_bff_from_environment(
    *,
    project_root: str | Path | None = None,
    rate_limiter: LoginRateLimiter | None = None,
) -> FastAPI:
    """Explicit HTTP composition root; secrets never select a backend.

    The existing local Streamlit workflow remains the default repository path.
    This durable HTTP vertical slice requires an explicit Supabase selection;
    it never falls back to runtime ``get_default`` or the legacy local queue.
    """

    root = Path(project_root or Path(__file__).resolve().parents[2])
    configure_structured_logging(os.getenv("BFF_LOG_LEVEL", "INFO"))
    backend = os.getenv("PNL_REPOSITORY_BACKEND", "local").strip().lower()
    if backend != "supabase":
        raise RuntimeError(
            "React HTTP analysis requires PNL_REPOSITORY_BACKEND=supabase; "
            "the local Streamlit backend remains available separately"
        )
    bundle = create_repository_bundle(root / "data", backend="supabase")
    client = bundle.models.client
    provenance = load_registered_provenance(
        root / "config" / "model_mapping.json",
        root / "config" / "mapping_registry.json",
        root / "config" / "release.json",
    )
    environment = os.getenv("BFF_ENVIRONMENT", "development").strip().lower()
    forecast_max_seconds = int(os.getenv("BFF_FORECAST_MAX_SECONDS", "900"))
    forecast_permit_seconds = int(os.getenv("BFF_FORECAST_PERMIT_LEASE_SECONDS", "1200"))
    forecast_max_concurrency = int(os.getenv("BFF_FORECAST_MAX_CONCURRENCY", "1"))
    session_ttl_seconds = int(os.getenv("BFF_SESSION_TTL_SECONDS", "28800"))
    login_max_attempts = int(os.getenv("BFF_LOGIN_MAX_ATTEMPTS", "5"))
    login_window_seconds = int(os.getenv("BFF_LOGIN_WINDOW_SECONDS", "300"))
    if not 1 <= forecast_max_concurrency <= 64:
        raise RuntimeError("BFF_FORECAST_MAX_CONCURRENCY must be 1-64")
    if not 30 <= forecast_permit_seconds <= 3600:
        raise RuntimeError("BFF_FORECAST_PERMIT_LEASE_SECONDS must be 30-3600")
    if forecast_permit_seconds < forecast_max_seconds + 60:
        raise RuntimeError("Forecast permit lease must exceed the execution budget by 60 seconds")
    if not 60 <= session_ttl_seconds <= 86400:
        raise RuntimeError("BFF_SESSION_TTL_SECONDS must be 60-86400")
    if not 1 <= login_max_attempts <= 100:
        raise RuntimeError("BFF_LOGIN_MAX_ATTEMPTS must be 1-100")
    if not 1 <= login_window_seconds <= 86400:
        raise RuntimeError("BFF_LOGIN_WINDOW_SECONDS must be 1-86400")
    shared_session_store = SupabaseSessionStore(client) if environment == "production" else None
    mapping_document = json.loads((root / "config" / "model_mapping.json").read_text(encoding="utf-8"))
    viewer_code = _required("VIEWER_CODE")
    admin_code = _required("ADMIN_CODE")
    if environment == "production" and (len(viewer_code) < 16 or len(admin_code) < 16):
        raise RuntimeError("production access codes must contain at least 16 characters")
    application = create_supabase_bff_application(
        supabase_client=client,
        viewer_code=viewer_code,
        admin_code=admin_code,
        actor_namespace_secret=_required("BFF_ACTOR_NAMESPACE_SECRET"),
        provenance=provenance,
        model_repository=bundle.models,
        model_mapping=mapping_document,
        mapping_path=str(root / "config" / "model_mapping.json"),
        session_ttl_seconds=session_ttl_seconds,
        session_store=shared_session_store,
        forecast_max_concurrency=forecast_max_concurrency,
        forecast_permit_lease_seconds=forecast_permit_seconds,
        forecast_max_execution_seconds=forecast_max_seconds,
        workbook_validator=(IsolatedExcelPreflight(
            mapping_document,
            timeout_seconds=int(os.getenv("BFF_PARSER_TIMEOUT_SECONDS", "30")),
            memory_limit_bytes=int(os.getenv("BFF_PARSER_MEMORY_LIMIT_BYTES", str(1024 * 1024 * 1024))),
        ) if environment == "production" else None),
    )
    origins = tuple(
        value.strip() for value in os.getenv("BFF_ALLOWED_ORIGINS", "").split(",") if value.strip()
    )
    if environment == "production" and not origins:
        raise RuntimeError("BFF_ALLOWED_ORIGINS is required in production")
    if environment == "production":
        if not _truthy(os.getenv("BFF_FORECAST_SYNC_APPROVED", "false")):
            raise RuntimeError(
                "synchronous Forecast requires an explicit staging benchmark approval"
            )
        temp_root = Path(_required("BFF_TEMP_ROOT"))
        if not temp_root.is_absolute():
            raise RuntimeError("BFF_TEMP_ROOT must be absolute in production")
        temp_quota = int(os.getenv("BFF_TEMP_QUOTA_BYTES", str(2 * 1024 * 1024 * 1024)))
        orphan_age = int(os.getenv("BFF_TEMP_ORPHAN_AGE_SECONDS", "86400"))
        if temp_quota < 512 * 1024 * 1024:
            raise RuntimeError("BFF_TEMP_QUOTA_BYTES must be at least 512MiB")
        if orphan_age < max(3600, forecast_max_seconds + 300):
            raise RuntimeError("BFF_TEMP_ORPHAN_AGE_SECONDS is below the active-operation safety window")
        configure_temp_artifacts(temp_root, temp_quota, orphan_age)
        client.rpc("set_bff_forecast_max_concurrency", {
            "p_max": forecast_max_concurrency,
        }).execute()
    settings = HttpBffSettings(
        environment=environment,
        cookie_secure=_truthy(os.getenv("BFF_COOKIE_SECURE", "false")),
        cookie_same_site=os.getenv("BFF_COOKIE_SAME_SITE", "strict").strip().lower(),
        session_ttl_seconds=session_ttl_seconds,
        csrf_secret=_required("BFF_CSRF_SECRET"),
        allowed_origins=origins,
        forecast_request_max_bytes=int(os.getenv("BFF_FORECAST_REQUEST_MAX_BYTES", str(1024 * 1024))),
    )
    effective_limiter = rate_limiter
    audit_sink = None
    if environment == "production":
        effective_limiter = effective_limiter or SupabaseLoginRateLimiter(
            client,
            max_attempts=login_max_attempts,
            window_seconds=login_window_seconds,
        )
        audit_sink = SupabaseAuditSink(client)
    proxy_policy = TrustedProxyPolicy.from_cidrs(
        _proxy_cidrs(environment),
        forwarded_header=os.getenv("BFF_FORWARDED_HEADER", "x-forwarded-for"),
    )
    return create_http_bff(
        application, settings=settings, rate_limiter=effective_limiter,
        proxy_policy=proxy_policy, audit_sink=audit_sink,
        readiness_check=(lambda: _readiness(client)) if environment == "production" else None,
        production_execution_policy_ready=(environment == "production"),
    )


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


def _truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _readiness(client) -> bool:
    response = client.rpc("bff_readiness_check", {}).execute()
    value = response.data if hasattr(response, "data") else response
    if isinstance(value, list):
        value = value[0] if value else False
    if isinstance(value, dict):
        value = value.get("bff_readiness_check", value.get("ready", False))
    return bool(value)


def _proxy_cidrs(environment: str) -> list[str]:
    values = [value.strip() for value in os.getenv("BFF_TRUSTED_PROXY_CIDRS", "").split(",") if value.strip()]
    if environment != "production":
        return values
    mode = _required("BFF_PROXY_MODE").lower()
    if mode not in {"direct", "trusted"}:
        raise RuntimeError("BFF_PROXY_MODE must be direct or trusted")
    if mode == "trusted" and not values:
        raise RuntimeError("trusted proxy mode requires BFF_TRUSTED_PROXY_CIDRS")
    if mode == "direct" and values:
        raise RuntimeError("direct proxy mode must not configure trusted proxy CIDRs")
    return values
