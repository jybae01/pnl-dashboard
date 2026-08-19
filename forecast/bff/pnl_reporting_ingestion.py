from __future__ import annotations

import hashlib
import hmac
import json
import re
import uuid
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol

from ..reporting import (
    DatasetType,
    PnlReportingValidationResult,
    TEMPLATE_VERSION,
    ValidationErrorCode,
    ValidationIssue,
    ValidationSeverity,
    parse_pnl_reporting_workbook,
)
from .auth import AccessCodeSessionService
from .errors import ApiErrorCode, BffError


CANONICAL_SCHEMA_VERSION = "PNL_REPORTING_CANONICAL_V1"
PARSER_VERSION = "PNL_REPORTING_PARSER_V1"
MAX_VALIDATION_ISSUES = 100
IDEMPOTENCY_KEY_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class PnlReportingIdempotencyConflictError(RuntimeError):
    pass


class PnlReportingInProgressError(RuntimeError):
    pass


class PnlReportingCleanupRequiredError(RuntimeError):
    pass


class PnlReportingStorageError(RuntimeError):
    pass


class PnlReportingSourceIntegrityError(RuntimeError):
    pass


class PnlReportingFinalizeError(RuntimeError):
    pass


class PnlReportingFinalizeUncertainError(RuntimeError):
    """The finalize commit outcome could not be read, so compensation is unsafe."""


class PnlReportingValidationFailure(RuntimeError):
    """Safe structured Slice A validation response for the HTTP 422 boundary."""

    def __init__(self, payload: Mapping[str, Any]) -> None:
        super().__init__("P&L Reporting workbook validation failed")
        self.payload = dict(payload)


@dataclass(frozen=True)
class PnlReportingUploadRequest:
    dataset_type: DatasetType
    reporting_year: int
    actual_through_month: int | None
    original_filename: str
    idempotency_key: str


@dataclass(frozen=True)
class PnlReportingReservation:
    ingestion_id: str
    dataset_id: str
    status: str
    lease_token: str | None
    source_sha256: str


@dataclass(frozen=True)
class PnlReportingUploadResponse:
    dataset_id: str
    dataset_type: DatasetType
    reporting_year: int
    actual_through_month: int | None
    template_version: str
    source_sha256: str
    uploaded_at: str
    warnings: tuple[Mapping[str, Any], ...]
    superseded_dataset_id: str | None
    replayed: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "datasetId": self.dataset_id,
            "datasetType": self.dataset_type.value,
            "reportingYear": self.reporting_year,
            "actualThroughMonth": self.actual_through_month,
            "templateVersion": self.template_version,
            "sourceSha256": self.source_sha256,
            "uploadedAt": self.uploaded_at,
            "warnings": [dict(item) for item in self.warnings],
            "supersededDatasetId": self.superseded_dataset_id,
            "replayed": self.replayed,
        }


class PnlReportingGateway(Protocol):
    def reserve(
        self,
        *,
        actor: str,
        request: PnlReportingUploadRequest,
        source_sha256: str,
        request_fingerprint: str,
    ) -> PnlReportingReservation: ...

    def upload_source(self, reservation: PnlReportingReservation, source: Path) -> None: ...

    def verify_source(self, reservation: PnlReportingReservation) -> None: ...

    def finalize(
        self,
        reservation: PnlReportingReservation,
        *,
        canonical_payload: Mapping[str, Any],
        original_filename: str,
        validation_summary: Mapping[str, Any],
    ) -> Mapping[str, Any]: ...

    def completed_response(self, reservation: PnlReportingReservation) -> Mapping[str, Any]: ...

    def remove_source(self, reservation: PnlReportingReservation) -> None: ...

    def record_failure(
        self,
        reservation: PnlReportingReservation,
        *,
        cleanup_succeeded: bool,
        classification: str,
        detail: Mapping[str, Any],
    ) -> None: ...

    def heartbeat(self, reservation: PnlReportingReservation) -> None: ...


class PnlReportingIngestionService:
    def __init__(
        self,
        sessions: AccessCodeSessionService,
        gateway: PnlReportingGateway,
        *,
        parser: Callable[..., PnlReportingValidationResult] = parse_pnl_reporting_workbook,
    ) -> None:
        self._sessions = sessions
        self._gateway = gateway
        self._parser = parser

    def ingest(
        self,
        session_id: str,
        request: PnlReportingUploadRequest,
        source: str | Path,
    ) -> PnlReportingUploadResponse:
        principal = self._sessions.require_admin(session_id)
        normalized = _validate_request(request)
        path = Path(source)
        try:
            source_sha256 = _sha256_file(path)
        except OSError as exc:
            raise BffError(
                ApiErrorCode.TRANSIENT_SYSTEM_ERROR,
                "P&L Reporting upload is temporarily unavailable",
            ) from exc

        try:
            validation = self._parser(
                path,
                dataset_type=normalized.dataset_type,
                reporting_year=normalized.reporting_year,
                actual_through_month=normalized.actual_through_month,
                source_filename=normalized.original_filename,
            )
        except Exception as exc:
            raise BffError(
                ApiErrorCode.TRANSIENT_SYSTEM_ERROR,
                "P&L Reporting validation is temporarily unavailable",
            ) from exc

        if not validation.valid:
            raise PnlReportingValidationFailure(validation_failure_payload(validation))
        canonical = validation.canonical_payload
        if canonical is None:
            raise BffError(
                ApiErrorCode.INPUT_INTEGRITY_MISMATCH,
                "P&L Reporting canonical payload is unavailable",
            )
        canonical_payload = canonical.to_dict()
        warnings = tuple(_safe_issue(issue) for issue in validation.warnings[:MAX_VALIDATION_ISSUES])
        validation_summary = {
            "status": "VALID",
            "errorCount": validation.error_count,
            "warningCount": validation.warning_count,
            "truncated": validation.warning_count > MAX_VALIDATION_ISSUES,
            "warnings": [dict(item) for item in warnings],
        }
        fingerprint = pnl_reporting_request_fingerprint(
            dataset_type=normalized.dataset_type,
            reporting_year=normalized.reporting_year,
            actual_through_month=normalized.actual_through_month,
            template_version=TEMPLATE_VERSION,
            source_sha256=source_sha256,
        )

        try:
            reservation = self._gateway.reserve(
                actor=principal.actor_id,
                request=normalized,
                source_sha256=source_sha256,
                request_fingerprint=fingerprint,
            )
        except PnlReportingIdempotencyConflictError as exc:
            raise BffError(
                ApiErrorCode.IDEMPOTENCY_CONFLICT,
                "Idempotency key conflicts with another P&L Reporting upload",
            ) from exc
        except PnlReportingCleanupRequiredError as exc:
            raise BffError(
                ApiErrorCode.INGESTION_CLEANUP_REQUIRED,
                "A previous P&L Reporting upload requires administrator cleanup",
            ) from exc
        except PnlReportingInProgressError as exc:
            raise BffError(
                ApiErrorCode.TRANSIENT_SYSTEM_ERROR,
                "The same P&L Reporting upload is already in progress",
            ) from exc
        except Exception as exc:
            raise BffError(
                ApiErrorCode.TRANSIENT_SYSTEM_ERROR,
                "P&L Reporting ingestion is temporarily unavailable",
            ) from exc

        if reservation.status == "COMPLETED":
            try:
                response = _response(self._gateway.completed_response(reservation))
                _validate_completed_response(response, normalized, reservation, source_sha256)
                self._gateway.verify_source(reservation)
            except Exception as exc:
                raise BffError(
                    ApiErrorCode.INPUT_INTEGRITY_MISMATCH,
                    "Completed P&L Reporting source provenance is invalid",
                ) from exc
            return replace(response, replayed=True)
        if reservation.status != "RESERVED" or not reservation.lease_token:
            raise BffError(
                ApiErrorCode.TRANSIENT_SYSTEM_ERROR,
                "The same P&L Reporting upload is already in progress",
            )

        storage_attempted = False
        finalized = False
        try:
            self._gateway.heartbeat(reservation)
            storage_attempted = True
            self._gateway.upload_source(reservation, path)
            self._gateway.verify_source(reservation)
            self._gateway.heartbeat(reservation)
            saved = self._gateway.finalize(
                reservation,
                canonical_payload=canonical_payload,
                original_filename=normalized.original_filename,
                validation_summary=validation_summary,
            )
            finalized = True
            response = _response(saved)
            _validate_completed_response(response, normalized, reservation, source_sha256)
            if response.replayed:
                raise ValueError("new finalization was marked as replayed")
            return response
        except PnlReportingFinalizeUncertainError as exc:
            try:
                self._gateway.record_failure(
                    reservation,
                    cleanup_succeeded=False,
                    classification="FINALIZE_OUTCOME_UNCERTAIN",
                    detail={"exceptionType": type(exc).__name__},
                )
            except Exception:
                pass
            raise BffError(
                ApiErrorCode.INGESTION_CLEANUP_REQUIRED,
                "P&L Reporting finalization outcome requires administrator verification",
            ) from exc
        except Exception as exc:
            if finalized:
                if isinstance(exc, BffError):
                    raise
                raise BffError(
                    ApiErrorCode.INPUT_INTEGRITY_MISMATCH,
                    "Finalized P&L Reporting response is invalid",
                ) from exc

            cleanup_succeeded = not storage_attempted
            detail: dict[str, Any] = {"exceptionType": type(exc).__name__}
            if storage_attempted:
                try:
                    self._gateway.remove_source(reservation)
                    cleanup_succeeded = True
                except Exception as cleanup_exc:
                    cleanup_succeeded = False
                    detail["cleanupExceptionType"] = type(cleanup_exc).__name__
            try:
                self._gateway.record_failure(
                    reservation,
                    cleanup_succeeded=cleanup_succeeded,
                    classification=(
                        "SOURCE_INTEGRITY_MISMATCH"
                        if isinstance(exc, PnlReportingSourceIntegrityError)
                        else "INGESTION_FAILED"
                    ),
                    detail=detail,
                )
            except Exception as diagnostic_exc:
                raise BffError(
                    ApiErrorCode.INGESTION_CLEANUP_REQUIRED,
                    "P&L Reporting upload recovery state could not be recorded",
                ) from diagnostic_exc
            if not cleanup_succeeded:
                raise BffError(
                    ApiErrorCode.INGESTION_CLEANUP_REQUIRED,
                    "P&L Reporting source cleanup requires administrator attention",
                ) from exc
            if isinstance(exc, PnlReportingSourceIntegrityError):
                raise BffError(
                    ApiErrorCode.INPUT_INTEGRITY_MISMATCH,
                    "P&L Reporting source integrity verification failed",
                ) from exc
            raise BffError(
                ApiErrorCode.TRANSIENT_SYSTEM_ERROR,
                "P&L Reporting ingestion failed safely",
            ) from exc


class SupabasePnlReportingGateway(PnlReportingGateway):
    """Service-role-only Reporting coordinator and private Storage adapter."""

    bucket = "pnl-models"

    def __init__(self, client: Any) -> None:
        self._client = client

    def reserve(
        self,
        *,
        actor: str,
        request: PnlReportingUploadRequest,
        source_sha256: str,
        request_fingerprint: str,
    ) -> PnlReportingReservation:
        try:
            row = _rpc_value(self._client.rpc("reserve_pnl_reporting_ingestion", {
                "p_idempotency_actor": actor,
                "p_idempotency_key": request.idempotency_key,
                "p_request_fingerprint": request_fingerprint,
                "p_dataset_type": request.dataset_type.value,
                "p_reporting_year": request.reporting_year,
                "p_actual_through_month": request.actual_through_month,
                "p_template_version": TEMPLATE_VERSION,
                "p_source_sha256": source_sha256,
            }).execute())
        except Exception as exc:
            if "IDEMPOTENCY_CONFLICT" in str(exc).upper():
                raise PnlReportingIdempotencyConflictError from exc
            raise
        if not isinstance(row, Mapping):
            raise RuntimeError("P&L Reporting reservation returned no row")
        status = str(row.get("ingestion_status") or "")
        if status == "IN_PROGRESS":
            raise PnlReportingInProgressError
        if status == "CLEANUP_REQUIRED":
            raise PnlReportingCleanupRequiredError
        return PnlReportingReservation(
            ingestion_id=str(uuid.UUID(str(row["ingestion_id"]))),
            dataset_id=str(uuid.UUID(str(row["dataset_id"]))),
            status=status,
            lease_token=(str(uuid.UUID(str(row["lease_token"]))) if row.get("lease_token") else None),
            source_sha256=source_sha256,
        )

    def upload_source(self, reservation: PnlReportingReservation, source: Path) -> None:
        path = _reporting_source_path(reservation.dataset_id)
        try:
            with source.open("rb") as payload:
                self._client.storage.from_(self.bucket).upload(
                    path=path,
                    file=payload,
                    file_options={
                        "content-type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        "upsert": "false",
                    },
                )
        except Exception as upload_exc:
            try:
                self.verify_source(reservation)
                return
            except Exception:
                raise PnlReportingStorageError("private source upload failed") from upload_exc

    def verify_source(self, reservation: PnlReportingReservation) -> None:
        try:
            payload = self._client.storage.from_(self.bucket).download(
                _reporting_source_path(reservation.dataset_id)
            )
        except Exception as exc:
            raise PnlReportingStorageError("private source verification download failed") from exc
        actual_sha256 = hashlib.sha256(bytes(payload)).hexdigest()
        if not hmac.compare_digest(actual_sha256, reservation.source_sha256):
            raise PnlReportingSourceIntegrityError("stored source SHA-256 mismatch")

    def finalize(
        self,
        reservation: PnlReportingReservation,
        *,
        canonical_payload: Mapping[str, Any],
        original_filename: str,
        validation_summary: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        finalize_error: Exception | None = None
        try:
            row = _rpc_value(self._client.rpc("finalize_pnl_reporting_ingestion", {
                "p_ingestion_id": reservation.ingestion_id,
                "p_lease_token": reservation.lease_token,
                "p_canonical_schema_version": CANONICAL_SCHEMA_VERSION,
                "p_parser_version": PARSER_VERSION,
                "p_canonical_payload": dict(canonical_payload),
                "p_original_filename": original_filename,
                "p_validation_summary": dict(validation_summary),
            }).execute())
        except Exception as exc:
            finalize_error = exc
            row = None
        if row is None:
            try:
                row = _rpc_value(self._client.rpc(
                    "get_completed_pnl_reporting_ingestion",
                    {"p_ingestion_id": reservation.ingestion_id},
                ).execute())
            except Exception as recovery_exc:
                raise PnlReportingFinalizeUncertainError from recovery_exc
            if row is None:
                raise PnlReportingFinalizeError("P&L Reporting finalization failed") from finalize_error
            try:
                self.verify_source(reservation)
            except Exception as integrity_exc:
                raise PnlReportingFinalizeUncertainError from integrity_exc
        if not isinstance(row, Mapping):
            raise PnlReportingFinalizeUncertainError("completed response is invalid")
        return row

    def completed_response(self, reservation: PnlReportingReservation) -> Mapping[str, Any]:
        row = _rpc_value(self._client.rpc(
            "get_completed_pnl_reporting_ingestion",
            {"p_ingestion_id": reservation.ingestion_id},
        ).execute())
        if not isinstance(row, Mapping):
            raise PnlReportingSourceIntegrityError("completed ingestion response is unavailable")
        return row

    def remove_source(self, reservation: PnlReportingReservation) -> None:
        path = _reporting_source_path(reservation.dataset_id)
        bucket = self._client.storage.from_(self.bucket)
        try:
            bucket.remove([path])
            parent, name = path.rsplit("/", 1)
            remaining = bucket.list(parent, {"search": name, "limit": 10})
        except Exception as exc:
            raise PnlReportingStorageError("private source cleanup is uncertain") from exc
        if any(str(item.get("name")) == name for item in (remaining or [])):
            raise PnlReportingStorageError("private source cleanup could not be verified")

    def record_failure(
        self,
        reservation: PnlReportingReservation,
        *,
        cleanup_succeeded: bool,
        classification: str,
        detail: Mapping[str, Any],
    ) -> None:
        self._client.rpc("record_pnl_reporting_ingestion_failure", {
            "p_ingestion_id": reservation.ingestion_id,
            "p_lease_token": reservation.lease_token,
            "p_cleanup_succeeded": cleanup_succeeded,
            "p_safe_failure_classification": classification,
            "p_failure_detail": dict(detail),
        }).execute()

    def heartbeat(self, reservation: PnlReportingReservation) -> None:
        self._client.rpc("heartbeat_pnl_reporting_ingestion", {
            "p_ingestion_id": reservation.ingestion_id,
            "p_lease_token": reservation.lease_token,
        }).execute()


def pnl_reporting_request_fingerprint(
    *,
    dataset_type: DatasetType,
    reporting_year: int,
    actual_through_month: int | None,
    template_version: str,
    source_sha256: str,
) -> str:
    canonical = json.dumps(
        {
            "actual_through_month": actual_through_month,
            "dataset_type": dataset_type.value,
            "reporting_year": reporting_year,
            "source_sha256": source_sha256,
            "template_version": template_version,
        },
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def validation_failure_payload(
    validation: PnlReportingValidationResult,
) -> dict[str, Any]:
    error_count = 0
    warning_count = 0
    error_issues: list[ValidationIssue] = []
    warning_issues: list[ValidationIssue] = []
    for issue in validation.issues:
        if issue.severity is ValidationSeverity.BLOCKING:
            error_count += 1
            if len(error_issues) < MAX_VALIDATION_ISSUES:
                error_issues.append(issue)
        elif issue.severity is ValidationSeverity.WARNING:
            warning_count += 1
            if len(warning_issues) < MAX_VALIDATION_ISSUES:
                warning_issues.append(issue)

    returned_errors = [_safe_issue(issue) for issue in error_issues]
    remaining = MAX_VALIDATION_ISSUES - len(returned_errors)
    returned_warnings = [_safe_issue(issue) for issue in warning_issues[:remaining]]
    return {
        "status": "INVALID",
        "errorCount": error_count,
        "warningCount": warning_count,
        "truncated": error_count + warning_count > MAX_VALIDATION_ISSUES,
        "errors": returned_errors,
        "warnings": returned_warnings,
    }


def _validate_request(request: PnlReportingUploadRequest) -> PnlReportingUploadRequest:
    fields: dict[str, str] = {}
    try:
        dataset_type = (
            request.dataset_type
            if isinstance(request.dataset_type, DatasetType)
            else DatasetType(str(request.dataset_type))
        )
    except (TypeError, ValueError):
        dataset_type = DatasetType.PLAN
        fields["dataset_type"] = "must be PLAN or ACTUAL"
    if isinstance(request.reporting_year, bool) or not isinstance(request.reporting_year, int):
        fields["reporting_year"] = "must be an integer"
    elif not 2000 <= request.reporting_year <= 2200:
        fields["reporting_year"] = "must be between 2000 and 2200"
    through = request.actual_through_month
    if dataset_type is DatasetType.PLAN:
        if through is not None:
            fields["actual_through_month"] = "must not be provided for PLAN"
    elif isinstance(through, bool) or not isinstance(through, int) or not 1 <= through <= 12:
        fields["actual_through_month"] = "must be an integer from 1 to 12"
    filename = _safe_filename(request.original_filename)
    if not filename or Path(filename).suffix.casefold() != ".xlsx":
        fields["file"] = "file name must be a safe .xlsx name"
    key = request.idempotency_key if isinstance(request.idempotency_key, str) else ""
    if not IDEMPOTENCY_KEY_PATTERN.fullmatch(key):
        fields["idempotency_key"] = "invalid idempotency key"
    if fields:
        raise BffError(
            ApiErrorCode.VALIDATION_ERROR,
            "P&L Reporting upload request is invalid",
            field_errors=fields,
        )
    return PnlReportingUploadRequest(
        dataset_type=dataset_type,
        reporting_year=request.reporting_year,
        actual_through_month=through,
        original_filename=filename,
        idempotency_key=key,
    )


def _safe_filename(value: Any) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 255:
        return ""
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        return ""
    normalized = value.strip().replace("\\", "/")
    name = normalized.rsplit("/", 1)[-1]
    if not name or name in {".", ".."} or name != normalized:
        return ""
    return name


def _safe_issue(issue: ValidationIssue) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "severity": issue.severity.value,
        "errorCode": issue.error_code.value,
        "message": _bounded_issue_text(
            issue.safe_message,
            maximum=500,
            fallback="Workbook validation failed",
        ),
    }
    optional = {
        "sheet": issue.sheet,
        "rowKey": issue.row_key,
        "productGroupKey": issue.product_group_key,
        "displayLabel": issue.display_label,
        "field": issue.field,
    }
    for key, value in optional.items():
        safe_value = _bounded_issue_text(value, maximum=200)
        if safe_value is not None:
            payload[key] = safe_value
    if (
        not isinstance(issue.month, bool)
        and isinstance(issue.month, int)
        and 1 <= issue.month <= 12
    ):
        payload["month"] = issue.month
    return payload


def _bounded_issue_text(
    value: Any,
    *,
    maximum: int,
    fallback: str | None = None,
) -> str | None:
    if not isinstance(value, str) or not value:
        return fallback
    return value[:maximum]


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _reporting_source_path(dataset_id: str) -> str:
    return f"reporting/{uuid.UUID(str(dataset_id))}/source.xlsx"


def _rpc_value(response: Any) -> Any:
    value = response.data if hasattr(response, "data") else response
    if isinstance(value, list):
        return value[0] if value else None
    return value


def _response(value: Mapping[str, Any]) -> PnlReportingUploadResponse:
    if not isinstance(value, Mapping):
        raise ValueError("response must be an object")
    try:
        dataset_id = str(uuid.UUID(str(value["datasetId"])))
        dataset_type = DatasetType(str(value["datasetType"]))
        reporting_year = value["reportingYear"]
        if isinstance(reporting_year, bool) or not isinstance(reporting_year, int):
            raise ValueError("reporting year is invalid")
        through = value.get("actualThroughMonth")
        if dataset_type is DatasetType.PLAN:
            if through is not None:
                raise ValueError("PLAN through month is invalid")
        elif isinstance(through, bool) or not isinstance(through, int) or not 1 <= through <= 12:
            raise ValueError("ACTUAL through month is invalid")
        template_version = str(value["templateVersion"])
        source_sha256 = str(value["sourceSha256"])
        uploaded_at = str(value["uploadedAt"])
        if template_version != TEMPLATE_VERSION or not SHA256_PATTERN.fullmatch(source_sha256):
            raise ValueError("response provenance is invalid")
        if not uploaded_at.strip():
            raise ValueError("upload timestamp is invalid")
        uploaded_datetime = datetime.fromisoformat(uploaded_at.replace("Z", "+00:00"))
        if uploaded_datetime.tzinfo is None:
            raise ValueError("upload timestamp must include a timezone")
        raw_warnings = value.get("warnings", [])
        if not isinstance(raw_warnings, list) or len(raw_warnings) > MAX_VALIDATION_ISSUES:
            raise ValueError("response warnings are invalid")
        warnings: list[Mapping[str, Any]] = []
        for warning in raw_warnings:
            if not isinstance(warning, Mapping):
                raise ValueError("response warning is invalid")
            warnings.append(_safe_response_warning(warning))
        raw_superseded = value.get("supersededDatasetId")
        superseded = str(uuid.UUID(str(raw_superseded))) if raw_superseded else None
        if superseded == dataset_id:
            raise ValueError("superseded dataset identity is invalid")
        replayed = value["replayed"]
        if not isinstance(replayed, bool):
            raise ValueError("replay flag is invalid")
        return PnlReportingUploadResponse(
            dataset_id=dataset_id,
            dataset_type=dataset_type,
            reporting_year=reporting_year,
            actual_through_month=through,
            template_version=template_version,
            source_sha256=source_sha256,
            uploaded_at=uploaded_at,
            warnings=tuple(warnings),
            superseded_dataset_id=superseded,
            replayed=replayed,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("P&L Reporting response contract is invalid") from exc


def _safe_response_warning(value: Mapping[str, Any]) -> dict[str, Any]:
    severity = value.get("severity")
    error_code = value.get("errorCode")
    message = value.get("message")
    if severity != ValidationSeverity.WARNING.value:
        raise ValueError("response warning severity is invalid")
    if error_code not in {item.value for item in ValidationErrorCode}:
        raise ValueError("response warning code is invalid")
    if not isinstance(message, str) or not message or len(message) > 500:
        raise ValueError("response warning message is invalid")
    safe: dict[str, Any] = {
        "severity": severity,
        "errorCode": error_code,
        "message": message,
    }
    for key in ("sheet", "rowKey", "productGroupKey", "displayLabel", "field"):
        item = value.get(key)
        if item is not None:
            if not isinstance(item, str) or not item or len(item) > 200:
                raise ValueError("response warning coordinate is invalid")
            safe[key] = item
    month = value.get("month")
    if month is not None:
        if isinstance(month, bool) or not isinstance(month, int) or not 1 <= month <= 12:
            raise ValueError("response warning month is invalid")
        safe["month"] = month
    return safe


def _validate_completed_response(
    response: PnlReportingUploadResponse,
    request: PnlReportingUploadRequest,
    reservation: PnlReportingReservation,
    source_sha256: str,
) -> None:
    if (
        response.dataset_id != reservation.dataset_id
        or response.dataset_type is not request.dataset_type
        or response.reporting_year != request.reporting_year
        or response.actual_through_month != request.actual_through_month
        or response.template_version != TEMPLATE_VERSION
        or response.source_sha256 != source_sha256
        or reservation.source_sha256 != source_sha256
    ):
        raise ValueError("completed P&L Reporting response does not match the request")
