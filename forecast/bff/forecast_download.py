from __future__ import annotations

import hashlib
import hmac
import re
import uuid
from typing import Any, Mapping, Protocol
from urllib.parse import quote

from ..provenance import SHA256_PATTERN
from .auth import AccessCodeSessionService
from .dto import ForecastWorkbookArtifact
from .errors import ApiErrorCode, BffError
from .gateway import GatewayTransientError


MODEL_SOURCE_BUCKET = "pnl-models"
MODEL_SOURCE_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
MAX_FORECAST_WORKBOOK_BYTES = 50 * 1024 * 1024
_SAFE_FILENAME = re.compile(r"^[^/\\\x00-\x1f\x7f]+\.xlsx$", re.IGNORECASE)


class ForecastWorkbookDownloadGateway(Protocol):
    """Trusted server operations needed for one Forecast workbook download."""

    def get_forecast_model(self, model_id: str) -> Mapping[str, Any] | None: ...

    def download_model_source(self, bucket: str, path: str) -> bytes: ...


class ForecastWorkbookDownloadService:
    """Admin-only delivery of exact bytes for a generated Forecast Model.

    The Model row is looked up by ID on the trusted server.  The client cannot
    provide a bucket, path, SHA, or filename.  Storage bytes are returned only
    after their SHA-256 matches the immutable value recorded on that row.
    """

    def __init__(
        self,
        sessions: AccessCodeSessionService,
        gateway: ForecastWorkbookDownloadGateway,
    ) -> None:
        self._sessions = sessions
        self._gateway = gateway

    def download(self, session_id: str, model_id: str) -> ForecastWorkbookArtifact:
        self._sessions.require_admin(session_id)
        normalized_id = _uuid(model_id)
        try:
            row = self._lookup_model(normalized_id)
        except GatewayTransientError as exc:
            raise _temporary_failure() from exc
        except BffError:
            raise
        except ValueError as exc:
            raise _integrity_failure() from exc
        except Exception as exc:
            # Provider/SQL details are never allowed to cross the BFF boundary.
            raise _temporary_failure() from exc
        if row is None:
            raise BffError(ApiErrorCode.MODEL_NOT_FOUND, "Forecast model not found")

        values = _validated_model(normalized_id, row)
        try:
            payload = self._gateway.download_model_source(values["bucket"], values["path"])
        except GatewayTransientError as exc:
            raise _temporary_failure() from exc
        except BffError:
            raise
        except Exception as exc:
            raise _temporary_failure() from exc
        if not isinstance(payload, (bytes, bytearray, memoryview)):
            raise _integrity_failure()
        content = bytes(payload)
        if not content or len(content) > MAX_FORECAST_WORKBOOK_BYTES:
            raise _integrity_failure()
        actual_sha = hashlib.sha256(content).hexdigest()
        if not hmac.compare_digest(actual_sha, values["workbook_sha256"]):
            raise _integrity_failure()
        return ForecastWorkbookArtifact(
            content=content,
            filename=values["filename"],
            media_type=MODEL_SOURCE_MEDIA_TYPE,
        )

    # Keep the capability name parallel with EvidenceDeliveryService for
    # callers that use an explicit Admin operation verb.
    def admin_download(self, session_id: str, model_id: str) -> ForecastWorkbookArtifact:
        return self.download(session_id, model_id)

    def _lookup_model(self, model_id: str) -> Mapping[str, Any] | None:
        value = self._gateway.get_forecast_model(model_id)
        if value is None:
            return None
        if not isinstance(value, Mapping):
            # Small trusted test/local adapters may return a dataclass or
            # SimpleNamespace; normalize those without accepting arbitrary
            # browser-provided objects.
            fields = getattr(value, "__dict__", None)
            if isinstance(fields, dict):
                value = fields
            else:
                raise ValueError("forecast model lookup returned an invalid shape")
        return value


# Public naming alias for callers that refer to the capability by its Model
# route rather than its Workbook artifact representation.
ForecastModelDownloadService = ForecastWorkbookDownloadService


def _validated_model(model_id: str, row: Mapping[str, Any]) -> dict[str, str]:
    row_id = row.get("id")
    if row_id is None:
        raise _integrity_failure()
    try:
        if str(uuid.UUID(str(row_id))) != model_id:
            raise ValueError("model lookup identity mismatch")
    except (TypeError, ValueError, AttributeError) as exc:
        raise _integrity_failure() from exc

    model_type = str(row.get("model_type") or "").strip().upper()
    if model_type != "FORECAST":
        raise BffError(
            ApiErrorCode.VALIDATION_ERROR,
            "Only FORECAST models can be downloaded",
            field_errors={"model_id": "must refer to a FORECAST model"},
        )
    # Migration 011 records this linkage for generated models.  This endpoint
    # is intentionally narrower than generic Model download and fails closed
    # when the generated linkage is absent or inconsistent.
    source_kind = row.get("source_kind")
    if source_kind != "forecast_generated":
        raise _integrity_failure()
    generation_id = row.get("forecast_generation_id")
    source_model_id = row.get("source_model_id")
    try:
        if generation_id is None:
            raise ValueError("missing forecast generation linkage")
        uuid.UUID(str(generation_id))
        if source_model_id is None:
            raise ValueError("missing forecast source model linkage")
        uuid.UUID(str(source_model_id))
    except (TypeError, ValueError, AttributeError) as exc:
        raise _integrity_failure() from exc

    workbook_sha256 = str(row.get("workbook_sha256") or "")
    if not SHA256_PATTERN.fullmatch(workbook_sha256):
        raise _integrity_failure()

    expected_path = f"models/{model_id}/source.xlsx"
    bucket_raw = row.get("workbook_bucket")
    path_raw = row.get("workbook_path")
    if not isinstance(bucket_raw, str) or not isinstance(path_raw, str):
        raise _integrity_failure()
    bucket = bucket_raw
    path = path_raw
    # The DB trigger currently enforces this shape.  Recheck it here before
    # calling private Storage, so a drifted row cannot redirect the download.
    if bucket != MODEL_SOURCE_BUCKET or path != expected_path:
        raise _integrity_failure()

    return {
        "workbook_sha256": workbook_sha256,
        "bucket": bucket,
        "path": path,
        "filename": _safe_filename(row.get("file_name"), model_id),
    }


def _safe_filename(value: Any, model_id: str) -> str:
    if isinstance(value, str):
        candidate = value.strip()
        if len(candidate) <= 255 and _SAFE_FILENAME.fullmatch(candidate):
            return candidate
    # The fallback is generated solely from the validated UUID and cannot
    # contain a path separator, control character, or alternate extension.
    return f"forecast_model_{model_id[:8]}.xlsx"


def content_disposition(filename: str) -> str:
    """Create a safe attachment header for an already validated XLSX name."""

    # RFC 5987 handles non-ASCII authoritative filenames.  The quoted ASCII
    # fallback remains safe for clients that do not understand filename*.
    ascii_fallback = filename.encode("ascii", "ignore").decode("ascii") or "forecast_model.xlsx"
    ascii_fallback = re.sub(r"[^A-Za-z0-9._-]", "_", ascii_fallback)
    if not ascii_fallback.lower().endswith(".xlsx"):
        ascii_fallback = "forecast_model.xlsx"
    return (
        f'attachment; filename="{ascii_fallback}"; '
        f"filename*=utf-8''{quote(filename, safe='!#$&+-.^_`|~')}")


def _uuid(value: Any) -> str:
    try:
        return str(uuid.UUID(str(value)))
    except (TypeError, ValueError, AttributeError) as exc:
        raise BffError(
            ApiErrorCode.VALIDATION_ERROR,
            "Request identifier is invalid",
            field_errors={"model_id": "must be a UUID"},
        ) from exc


def _integrity_failure() -> BffError:
    return BffError(
        ApiErrorCode.INPUT_INTEGRITY_MISMATCH,
        "Forecast workbook provenance is invalid",
    )


def _temporary_failure() -> BffError:
    return BffError(
        ApiErrorCode.TRANSIENT_SYSTEM_ERROR,
        "Forecast workbook download is temporarily unavailable",
    )
