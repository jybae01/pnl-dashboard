from __future__ import annotations

import json
import re
import shutil
import tempfile
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from ..analysis_export import MIME_XLSX, write_comparison_audit_workbook
from ..provenance import ResultProvenance, SHA256_PATTERN, mapping_hash
from .auth import AccessCodeSessionService
from .dto import CalculationHistoryItem, CalculationHistoryResponse
from .errors import ApiErrorCode, BffError
from .gateway import BffApplicationGateway, GatewayTransientError
from ..temp_artifacts import temp_artifact_policy


_SAFE_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T")
_STATUSES = {"pending", "processing", "completed", "failed"}
MAX_EVIDENCE_BYTES = 100 * 1024 * 1024
MAX_STORED_RESULT_BYTES = 25 * 1024 * 1024
MAX_SALES_ROWS = 10_000


@dataclass
class EvidenceArtifact:
    path: Path
    filename: str
    media_type: str = MIME_XLSX
    _temporary_root: Path | None = None

    def cleanup(self) -> None:
        if self._temporary_root is not None:
            shutil.rmtree(self._temporary_root, ignore_errors=True)
            self._temporary_root = None


class EvidenceDeliveryService:
    """Generate evidence from one stored Result and its exact pinned inputs."""

    def __init__(
        self,
        sessions: AccessCodeSessionService,
        gateway: BffApplicationGateway,
        provenance: ResultProvenance,
        *,
        mapping_path: str | Path,
        supported_result_schema_versions: Sequence[str],
    ) -> None:
        self._sessions = sessions
        self._gateway = gateway
        self._provenance = provenance
        self._mapping_path = Path(mapping_path)
        self._supported_versions = tuple(supported_result_schema_versions)
        self._generation_slots = threading.BoundedSemaphore(2)

    def admin_download(self, session_id: str, result_id: str) -> EvidenceArtifact:
        self._sessions.require_admin(session_id)
        normalized = _uuid(result_id, "result_id")
        try:
            row = self._gateway.get_admin_evidence_payload(
                normalized,
                supported_result_schema_versions=self._supported_versions,
            )
        except GatewayTransientError as exc:
            raise _temporary_failure() from exc
        if row is None:
            raise BffError(ApiErrorCode.RESULT_NOT_FOUND, "Result not found")
        return self._generate_bounded(normalized, row)

    def viewer_download(self, session_id: str, result_id: str) -> EvidenceArtifact:
        self._sessions.require_viewer(session_id)
        normalized = _uuid(result_id, "result_id")
        try:
            row = self._gateway.get_viewer_evidence_payload(
                normalized,
                supported_result_schema_versions=self._supported_versions,
            )
        except GatewayTransientError as exc:
            raise _temporary_failure() from exc
        if row is None:
            raise BffError(ApiErrorCode.RESULT_NOT_AVAILABLE, "Result not available")
        try:
            artifact = self._generate_bounded(normalized, row)
        except BffError as exc:
            if exc.code == ApiErrorCode.INPUT_INTEGRITY_MISMATCH:
                raise BffError(ApiErrorCode.RESULT_NOT_AVAILABLE, "Result not available") from exc
            raise
        try:
            still_available = self._gateway.validate_result_availability(
                normalized,
                supported_result_schema_versions=self._supported_versions,
            )
        except GatewayTransientError as exc:
            artifact.cleanup()
            raise _temporary_failure() from exc
        if not still_available:
            artifact.cleanup()
            raise BffError(ApiErrorCode.RESULT_NOT_AVAILABLE, "Result not available")
        return artifact

    def _generate_bounded(self, result_id: str, row: Mapping[str, Any]) -> EvidenceArtifact:
        if not self._generation_slots.acquire(blocking=False):
            raise BffError(
                ApiErrorCode.TRANSIENT_SYSTEM_ERROR,
                "Evidence generation is temporarily busy",
            )
        try:
            return self._generate(result_id, row)
        finally:
            self._generation_slots.release()

    def _generate(self, result_id: str, row: Mapping[str, Any]) -> EvidenceArtifact:
        values = _validated_evidence_row(result_id, row, self._provenance, self._supported_versions)
        if mapping_hash(self._mapping_path) != values["mapping_hash"]:
            raise _integrity_failure()
        serialized_size = len(json.dumps(
            values["result_payload"], ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8"))
        if serialized_size > MAX_STORED_RESULT_BYTES:
            raise BffError(
                ApiErrorCode.EVIDENCE_GENERATION_FAILED,
                "Evidence workbook generation failed",
            )
        policy = temp_artifact_policy()
        policy.ensure_capacity(MAX_EVIDENCE_BYTES)
        root = policy.make_directory(prefix="pnl-evidence-")
        output_path = root / "evidence.xlsx"
        try:
            result = _escape_workbook_text(dict(values["result_payload"]["comparison_result"]))
            sales = result.get("sales_analysis")
            if not isinstance(sales, Mapping) or not isinstance(sales.get("rows"), list) \
                    or not isinstance(sales.get("totals"), Mapping):
                raise _integrity_failure()
            if len(sales["rows"]) > MAX_SALES_ROWS:
                raise BffError(
                    ApiErrorCode.EVIDENCE_GENERATION_FAILED,
                    "Evidence workbook generation failed",
                )
            baseline_fx = _positive_finite(sales.get("baseline_fx_krw_per_usd"))
            comparison_fx = _positive_finite(sales.get("comparison_fx_krw_per_usd"))
            result["evidence_provenance"] = _escape_workbook_text({
                "result_id": result_id,
                "job_id": values["job_id"],
                "baseline_model_id": values["baseline_model_id"],
                "comparison_model_id": values["comparison_model_id"],
                "baseline_workbook_sha256": values["baseline_workbook_sha256"],
                "comparison_workbook_sha256": values["comparison_workbook_sha256"],
                "engine_version": values["engine_version"],
                "mapping_version": values["mapping_version"],
                "mapping_hash": values["mapping_hash"],
                "result_schema_version": values["result_schema_version"],
                "analysis_request": values["analysis_request"],
            })
            write_comparison_audit_workbook(
                output_path,
                result=result,
                sales_rows=sales["rows"],
                sales_totals=dict(sales["totals"]),
                baseline_fx=baseline_fx,
                comparison_fx=comparison_fx,
                mapping_path=self._mapping_path,
            )
            size = output_path.stat().st_size
            if size < 1 or size > MAX_EVIDENCE_BYTES:
                raise BffError(
                    ApiErrorCode.EVIDENCE_GENERATION_FAILED,
                    "Evidence workbook generation failed",
                )
            period = result.get("period") if isinstance(result.get("period"), Mapping) else {}
            label = re.sub(r"[^0-9A-Za-z_-]+", "-", str(period.get("label") or "period"))[:40]
            filename = f"손익분석_근거_{label}_{result_id[:8]}.xlsx"
            return EvidenceArtifact(output_path, filename, _temporary_root=root)
        except BffError:
            shutil.rmtree(root, ignore_errors=True)
            raise
        except Exception as exc:
            shutil.rmtree(root, ignore_errors=True)
            raise BffError(
                ApiErrorCode.EVIDENCE_GENERATION_FAILED,
                "Evidence workbook generation failed",
            ) from exc


def _escape_workbook_text(value):
    """Prevent stored/user text from becoming an executable Excel formula."""
    if isinstance(value, str):
        return "'" + value if value.startswith(("=", "+", "-", "@")) else value
    if isinstance(value, list):
        return [_escape_workbook_text(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_escape_workbook_text(item) for item in value)
    if isinstance(value, Mapping):
        return {key: _escape_workbook_text(item) for key, item in value.items()}
    return value


class CalculationHistoryService:
    def __init__(self, sessions: AccessCodeSessionService, gateway: BffApplicationGateway) -> None:
        self._sessions = sessions
        self._gateway = gateway

    def list_admin(
        self,
        session_id: str,
        *,
        limit: int = 25,
        before_created_at: str | None = None,
        before_job_id: str | None = None,
    ) -> CalculationHistoryResponse:
        self._sessions.require_admin(session_id)
        if isinstance(limit, bool) or not 1 <= int(limit) <= 50:
            raise BffError(ApiErrorCode.VALIDATION_ERROR, "History limit is invalid")
        if (before_created_at is None) != (before_job_id is None):
            raise BffError(ApiErrorCode.VALIDATION_ERROR, "History cursor is invalid")
        if before_created_at is not None:
            if not _SAFE_TIMESTAMP.match(before_created_at):
                raise BffError(ApiErrorCode.VALIDATION_ERROR, "History cursor is invalid")
            before_job_id = _uuid(before_job_id, "before_job_id")
        try:
            rows = self._gateway.list_calculation_history(
                limit=int(limit),
                before_created_at=before_created_at,
                before_job_id=before_job_id,
            )
        except GatewayTransientError as exc:
            raise BffError(
                ApiErrorCode.TRANSIENT_SYSTEM_ERROR,
                "Calculation history is temporarily unavailable",
            ) from exc
        has_more = len(rows) > limit
        visible = rows[:limit]
        items = tuple(_history_item(row) for row in visible)
        tail = items[-1] if has_more and items else None
        return CalculationHistoryResponse(
            items=items,
            next_before_created_at=tail.created_at if tail else None,
            next_before_job_id=tail.job_id if tail else None,
        )


def _validated_evidence_row(
    result_id: str,
    row: Mapping[str, Any],
    provenance: ResultProvenance,
    supported_versions: Sequence[str],
) -> dict[str, Any]:
    required = (
        "result_id", "job_id", "result_payload", "analysis_request",
        "baseline_model_id", "comparison_model_id", "baseline_workbook_sha256",
        "comparison_workbook_sha256", "engine_version", "mapping_version",
        "mapping_hash", "result_schema_version",
    )
    if any(row.get(key) is None for key in required):
        raise _integrity_failure()
    values = dict(row)
    if str(values["result_id"]) != result_id:
        raise _integrity_failure()
    for key in ("result_id", "job_id", "baseline_model_id", "comparison_model_id"):
        values[key] = str(uuid.UUID(str(values[key])))
    if values["baseline_model_id"] == values["comparison_model_id"]:
        raise _integrity_failure()
    for key in ("baseline_workbook_sha256", "comparison_workbook_sha256", "mapping_hash"):
        values[key] = str(values[key])
        if not SHA256_PATTERN.fullmatch(values[key]):
            raise _integrity_failure()
    if (
        str(values["engine_version"]) != provenance.engine_version
        or str(values["mapping_version"]) != provenance.mapping_version
        or str(values["mapping_hash"]) != provenance.mapping_hash
        or str(values["result_schema_version"]) not in supported_versions
    ):
        raise _integrity_failure()
    if not isinstance(values["result_payload"], Mapping) or not isinstance(values["analysis_request"], Mapping):
        raise _integrity_failure()
    return values


def _history_item(row: Mapping[str, Any]) -> CalculationHistoryItem:
    try:
        status = str(row["status"]).lower()
        if status not in _STATUSES:
            raise ValueError
        result_id = str(uuid.UUID(str(row["result_id"]))) if row.get("result_id") else None
        if status != "completed" and result_id is not None:
            raise ValueError
        start = int(row["start_month"]) if row.get("start_month") is not None else None
        end = int(row["end_month"]) if row.get("end_month") is not None else None
        if (start is None) != (end is None) or (
            start is not None and end is not None and not 1 <= start <= end <= 12
        ):
            raise ValueError
        return CalculationHistoryItem(
            job_id=str(uuid.UUID(str(row["job_id"]))),
            result_id=result_id,
            status=status.upper(),
            baseline_model_id=str(uuid.UUID(str(row["baseline_model_id"]))),
            baseline_model_name=str(row["baseline_model_name"]),
            comparison_model_id=str(uuid.UUID(str(row["comparison_model_id"]))),
            comparison_model_name=str(row["comparison_model_name"]),
            start_month=start,
            end_month=end,
            attempt=int(row["attempt"]),
            max_attempts=int(row["max_attempts"]),
            created_at=str(row["created_at"]),
            completed_at=str(row["completed_at"]) if row.get("completed_at") else None,
            error_code=str(row["error_code"]) if row.get("error_code") else None,
            error_message=str(row["error_message"]) if row.get("error_message") else None,
            is_published=bool(row["is_published"]),
            is_default=bool(row.get("is_default", False)),
            published_at=str(row["published_at"]) if row.get("published_at") else None,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise _integrity_failure() from exc


def _positive_finite(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise _integrity_failure() from exc
    if number <= 0 or number != number or number in (float("inf"), float("-inf")):
        raise _integrity_failure()
    return number


def _uuid(value: Any, field_name: str) -> str:
    try:
        return str(uuid.UUID(str(value)))
    except (TypeError, ValueError, AttributeError) as exc:
        raise BffError(
            ApiErrorCode.VALIDATION_ERROR,
            "Request identifier is invalid",
            field_errors={field_name: "must be a UUID"},
        ) from exc


def _integrity_failure() -> BffError:
    return BffError(ApiErrorCode.INPUT_INTEGRITY_MISMATCH, "Evidence provenance is invalid")


def _temporary_failure() -> BffError:
    return BffError(
        ApiErrorCode.TRANSIENT_SYSTEM_ERROR,
        "Evidence delivery is temporarily unavailable",
    )
