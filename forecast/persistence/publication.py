from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .contracts import ResultPublicationRepository


class AdminResultPublicationGateway:
    """Trusted-server capability that re-authorizes every publication call.

    The Supabase service secret bypasses RLS, so callers must not receive the
    low-level repository directly.  Streamlit supplies its server-side role
    check here; no secret or capability object belongs in browser/session data.
    """

    def __init__(
        self,
        repository: ResultPublicationRepository,
        require_admin: Callable[[], None],
    ) -> None:
        self._repository = repository
        self._require_admin = require_admin

    def set_publication(
        self,
        result_id: str,
        *,
        is_published: bool,
        is_default: bool = False,
    ) -> dict[str, Any]:
        self._require_admin()
        return self._repository.set_publication(
            result_id,
            is_published=is_published,
            is_default=is_default,
        )
