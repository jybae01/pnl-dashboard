from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from pathlib import Path

from .auth import AccessCodeSessionService


PNL_REPORTING_TEMPLATE_FILENAME = "PNL_REPORTING_TEMPLATE_V1.xlsx"
PNL_REPORTING_TEMPLATE_SIZE = 20_639
PNL_REPORTING_TEMPLATE_SHA256 = (
    "ddaf345de82c8a91fc1ccc852dd90e3586f996709f020cf0f597a09345700b1a"
)
PNL_REPORTING_TEMPLATE_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)
PNL_REPORTING_TEMPLATE_RESOURCE = (
    Path(__file__).resolve().parent / "resources" / PNL_REPORTING_TEMPLATE_FILENAME
)
_INTEGRITY_ERROR = "P&L Reporting template resource integrity check failed"


class PnlReportingTemplateIntegrityError(RuntimeError):
    """Generic startup failure for a missing or altered approved artifact."""


@dataclass(frozen=True)
class PnlReportingTemplateArtifact:
    content: bytes
    filename: str
    media_type: str
    size: int
    sha256: str


class PnlReportingTemplateService:
    """Admin delivery of one repository-bundled, immutable approved workbook."""

    def __init__(
        self,
        sessions: AccessCodeSessionService,
        *,
        resource_path: str | Path | None = None,
    ) -> None:
        self._sessions = sessions
        path = PNL_REPORTING_TEMPLATE_RESOURCE
        if resource_path is not None:
            path = Path(resource_path)
            if not path.is_absolute():
                raise PnlReportingTemplateIntegrityError(_INTEGRITY_ERROR)
        self._artifact = _load_approved_artifact(path)

    def admin_download(self, session_id: str) -> PnlReportingTemplateArtifact:
        self._sessions.require_admin(session_id)
        return self._artifact


def _load_approved_artifact(path: Path) -> PnlReportingTemplateArtifact:
    try:
        content = path.read_bytes()
    except OSError:
        raise PnlReportingTemplateIntegrityError(_INTEGRITY_ERROR) from None

    actual_sha256 = hashlib.sha256(content).hexdigest()
    if len(content) != PNL_REPORTING_TEMPLATE_SIZE or not hmac.compare_digest(
        actual_sha256,
        PNL_REPORTING_TEMPLATE_SHA256,
    ):
        raise PnlReportingTemplateIntegrityError(_INTEGRITY_ERROR)

    return PnlReportingTemplateArtifact(
        content=content,
        filename=PNL_REPORTING_TEMPLATE_FILENAME,
        media_type=PNL_REPORTING_TEMPLATE_MEDIA_TYPE,
        size=PNL_REPORTING_TEMPLATE_SIZE,
        sha256=PNL_REPORTING_TEMPLATE_SHA256,
    )
