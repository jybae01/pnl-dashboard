from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI

from ..persistence.factory import create_repository_bundle
from ..provenance import load_registered_provenance
from .factory import create_supabase_bff_application
from .http import HttpBffSettings, LoginRateLimiter, create_http_bff


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
    application = create_supabase_bff_application(
        supabase_client=client,
        viewer_code=_required("VIEWER_CODE"),
        admin_code=_required("ADMIN_CODE"),
        actor_namespace_secret=_required("BFF_ACTOR_NAMESPACE_SECRET"),
        provenance=provenance,
        model_repository=bundle.models,
        session_ttl_seconds=int(os.getenv("BFF_SESSION_TTL_SECONDS", "28800")),
    )
    environment = os.getenv("BFF_ENVIRONMENT", "development").strip().lower()
    settings = HttpBffSettings(
        environment=environment,
        cookie_secure=_truthy(os.getenv("BFF_COOKIE_SECURE", "false")),
        cookie_same_site=os.getenv("BFF_COOKIE_SAME_SITE", "strict").strip().lower(),
        session_ttl_seconds=int(os.getenv("BFF_SESSION_TTL_SECONDS", "28800")),
        csrf_secret=_required("BFF_CSRF_SECRET"),
        allowed_origins=tuple(
            value.strip()
            for value in os.getenv("BFF_ALLOWED_ORIGINS", "").split(",")
            if value.strip()
        ),
    )
    return create_http_bff(application, settings=settings, rate_limiter=rate_limiter)


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


def _truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}
