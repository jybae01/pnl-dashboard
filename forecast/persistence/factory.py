from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..mapping_config import LocalMappingConfigRepository
from ..provenance import load_registered_provenance
from ..storage import ModelRegistry, ResultStore
from .local import (
    LocalCalculationJobRepository,
    LocalModelRepositoryAdapter,
    LocalResultRepositoryAdapter,
)
from .supabase import (
    SupabaseCalculationJobRepository,
    SupabaseMappingConfigRepository,
    SupabaseModelRepositoryAdapter,
    SupabaseResultRepository,
)


@dataclass(frozen=True)
class RepositoryBundle:
    models: Any
    results: Any
    jobs: Any
    mappings: Any
    backend: str


def create_repository_bundle(
    data_directory: str | Path,
    *,
    backend: str | None = None,
    supabase_client: Any | None = None,
) -> RepositoryBundle:
    """Create explicit local or Supabase adapters.

    The default remains local.  Supabase is opt-in so merely adding environment
    secrets cannot silently change production persistence before the Edge
    upload UI and real Python worker arrive in Phase 2.
    """

    directory = Path(data_directory)
    selected = (backend or os.getenv("PNL_REPOSITORY_BACKEND", "local")).strip().lower()
    if selected == "local":
        project_root = directory.parent
        provenance = None
        registry_path = project_root / "config" / "mapping_registry.json"
        release_path = project_root / "config" / "release.json"
        mapping_path = project_root / "config" / "model_mapping.json"
        if registry_path.exists() and release_path.exists() and mapping_path.exists():
            provenance = load_registered_provenance(mapping_path, registry_path, release_path)
        return RepositoryBundle(
            models=LocalModelRepositoryAdapter(ModelRegistry(directory / "registry"), provenance),
            results=LocalResultRepositoryAdapter(ResultStore(directory), provenance),
            jobs=LocalCalculationJobRepository(directory / "jobs"),
            mappings=LocalMappingConfigRepository(directory / "mapping_versions.json"),
            backend="local",
        )
    if selected != "supabase":
        raise ValueError("PNL_REPOSITORY_BACKEND must be 'local' or 'supabase'")
    client = supabase_client or _create_supabase_client()
    return RepositoryBundle(
        models=SupabaseModelRepositoryAdapter(client, directory / "model_cache"),
        results=SupabaseResultRepository(client),
        jobs=SupabaseCalculationJobRepository(client),
        mappings=SupabaseMappingConfigRepository(client),
        backend="supabase",
    )


def _create_supabase_client() -> Any:
    url = os.getenv("SUPABASE_URL", "").strip()
    service_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not url or not service_key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required")
    try:
        from supabase import create_client
    except ModuleNotFoundError as exc:
        raise RuntimeError("install the optional supabase dependency") from exc
    return create_client(url, service_key)
