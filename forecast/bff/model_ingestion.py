from __future__ import annotations

import hashlib
import re
import stat
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol

from ..preflight import ExcelPreflightValidator, PreflightValidationError
from ..provenance import ResultProvenance, SHA256_PATTERN
from ..workbook import extract_period_types
from .auth import AccessCodeSessionService
from .dto import (
    AdminModelListResponse,
    AdminModelResponse,
    ModelPublicationResponse,
    ModelUploadRequest,
    ModelUploadResponse,
)
from .errors import ApiErrorCode, BffError
from ..parser_isolation import IsolatedParserError


MAX_WORKBOOK_BYTES = 50 * 1024 * 1024
MAX_ZIP_ENTRIES = 5_000
MAX_ZIP_ENTRY_BYTES = 256 * 1024 * 1024
MAX_ZIP_EXPANDED_BYTES = 512 * 1024 * 1024
MAX_ZIP_COMPRESSION_RATIO = 1_000
IDEMPOTENCY_KEY_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
MODEL_TYPES = {"PLAN", "ACTUAL", "FORECAST"}
REQUIRED_XLSX_PARTS = frozenset({"[Content_Types].xml", "_rels/.rels", "xl/workbook.xml"})


class ModelIngestionConflictError(RuntimeError):
    pass


class ModelIngestionInProgressError(RuntimeError):
    pass


class ModelIngestionCleanupRequiredError(RuntimeError):
    pass


class ModelIngestionFinalizeUncertainError(RuntimeError):
    """Finalize outcome could not be read; source compensation is unsafe."""


@dataclass(frozen=True)
class ModelIngestionReservation:
    ingestion_id: str
    model_id: str
    status: str
    lease_token: str | None
    idempotency_replayed: bool


class ModelIngestionGateway(Protocol):
    def reserve(
        self,
        *,
        actor: str,
        request: ModelUploadRequest,
        workbook_sha256: str,
        period_types: Mapping[str, str],
        provenance: ResultProvenance,
    ) -> ModelIngestionReservation: ...

    def upload_source(self, model_id: str, source: Path, workbook_sha256: str) -> None: ...

    def verify_source(self, model_id: str, workbook_sha256: str) -> None: ...

    def finalize(self, reservation: ModelIngestionReservation) -> Mapping[str, Any]: ...

    def remove_source(self, model_id: str) -> None: ...

    def record_failure(
        self,
        reservation: ModelIngestionReservation,
        *,
        cleanup_succeeded: bool,
        error_code: str,
        error_detail: Mapping[str, Any],
    ) -> None: ...

    def heartbeat(self, reservation: ModelIngestionReservation) -> None: ...


class ModelManagementService:
    def __init__(self, sessions: AccessCodeSessionService, repository: Any) -> None:
        self._sessions = sessions
        self._repository = repository

    def list_models(self, session_id: str) -> AdminModelListResponse:
        self._sessions.require_admin(session_id)
        try:
            rows = self._repository.list()
            return AdminModelListResponse(models=tuple(_model_response(row) for row in rows))
        except BffError:
            raise
        except Exception as exc:
            raise BffError(
                ApiErrorCode.TRANSIENT_SYSTEM_ERROR,
                "Model management list is temporarily unavailable",
            ) from exc


class ModelIngestionService:
    def __init__(
        self,
        sessions: AccessCodeSessionService,
        repository: Any,
        gateway: ModelIngestionGateway,
        validator: ExcelPreflightValidator,
        provenance: ResultProvenance,
    ) -> None:
        self._sessions = sessions
        self._repository = repository
        self._gateway = gateway
        self._validator = validator
        self._provenance = provenance

    def ingest(
        self,
        session_id: str,
        request: ModelUploadRequest,
        source: str | Path,
    ) -> ModelUploadResponse:
        principal = self._sessions.require_admin(session_id)
        normalized = _validate_request(request)
        path = Path(source)
        isolated_validation = hasattr(self._validator, "require_with_metadata")
        if not isolated_validation:
            _validate_xlsx_package(path, normalized.file_name)
        workbook_sha256 = _sha256_file(path)
        try:
            if hasattr(self._validator, "require_with_metadata"):
                period_types = self._validator.require_with_metadata(
                    path, expected_year=normalized.model_year, file_name=normalized.file_name,
                )
            else:
                self._validator.require(path, expected_year=normalized.model_year)
                period_types = extract_period_types(path)
        except IsolatedParserError as exc:
            raise BffError(
                ApiErrorCode.VALIDATION_ERROR,
                "Workbook structural preflight failed",
                field_errors={"file": exc.code},
            ) from exc
        except PreflightValidationError as exc:
            raise BffError(
                ApiErrorCode.VALIDATION_ERROR,
                "Workbook structural preflight failed",
                field_errors={
                    "file": "; ".join(issue.code for issue in exc.report.issues) or "preflight_failed"
                },
            ) from exc
        except Exception as exc:
            raise BffError(
                ApiErrorCode.VALIDATION_ERROR,
                "Workbook metadata could not be read",
                field_errors={"file": "workbook_metadata_invalid"},
            ) from exc

        try:
            reservation = self._gateway.reserve(
                actor=principal.actor_id,
                request=normalized,
                workbook_sha256=workbook_sha256,
                period_types=period_types,
                provenance=self._provenance,
            )
        except ModelIngestionConflictError as exc:
            raise BffError(ApiErrorCode.IDEMPOTENCY_CONFLICT, "Idempotency key conflicts with another upload") from exc
        except ModelIngestionCleanupRequiredError as exc:
            raise BffError(
                ApiErrorCode.INGESTION_CLEANUP_REQUIRED,
                "A previous upload requires administrator cleanup",
            ) from exc
        except ModelIngestionInProgressError as exc:
            raise BffError(ApiErrorCode.TRANSIENT_SYSTEM_ERROR, "The same upload is already in progress") from exc
        except Exception as exc:
            raise BffError(ApiErrorCode.TRANSIENT_SYSTEM_ERROR, "Model ingestion is temporarily unavailable") from exc

        if reservation.status == "completed":
            try:
                existing = self._repository.get(reservation.model_id)
                response = _model_response(existing)
                if not response.workbook_sha256:
                    raise ValueError("completed ingestion has no workbook SHA")
                self._gateway.verify_source(reservation.model_id, response.workbook_sha256)
            except Exception as exc:
                raise BffError(
                    ApiErrorCode.INPUT_INTEGRITY_MISMATCH,
                    "Completed ingestion source provenance is invalid",
                ) from exc
            return ModelUploadResponse(model=response, idempotency_replayed=True)
        if reservation.status != "reserved" or not reservation.lease_token:
            raise BffError(ApiErrorCode.TRANSIENT_SYSTEM_ERROR, "The same upload is already in progress")

        storage_written = False
        finalized = False
        try:
            # Once an upload is attempted, object state is unknown until the
            # exact-byte verification succeeds; compensation is conservative.
            storage_written = True
            if hasattr(self._gateway, "heartbeat"):
                self._gateway.heartbeat(reservation)
            self._gateway.upload_source(reservation.model_id, path, workbook_sha256)
            self._gateway.verify_source(reservation.model_id, workbook_sha256)
            if hasattr(self._gateway, "heartbeat"):
                self._gateway.heartbeat(reservation)
            saved = self._gateway.finalize(reservation)
            finalized = True
            response = _model_response(saved)
            if (
                response.model_id != reservation.model_id
                or response.workbook_sha256 != workbook_sha256
                or response.is_published
                or response.is_default
            ):
                raise BffError(
                    ApiErrorCode.INPUT_INTEGRITY_MISMATCH,
                    "Finalized Model provenance is invalid",
                )
            return ModelUploadResponse(
                model=response,
                idempotency_replayed=reservation.idempotency_replayed,
            )
        except ModelIngestionFinalizeUncertainError as exc:
            # The DB may already contain the durable Model. Never delete its
            # source while the commit outcome is unknown. If still reserved,
            # persist cleanup_required for the operator recovery queue.
            try:
                self._gateway.record_failure(
                    reservation,
                    cleanup_succeeded=False,
                    error_code="FINALIZE_OUTCOME_UNCERTAIN",
                    error_detail={"exception_type": type(exc).__name__},
                )
            except Exception:
                pass
            raise BffError(
                ApiErrorCode.INGESTION_CLEANUP_REQUIRED,
                "Model finalization outcome requires administrator verification",
            ) from exc
        except Exception as exc:
            # Never compensate an object after its durable Model row exists.
            # A response-shaping defect must not corrupt finalized provenance.
            if finalized:
                if isinstance(exc, BffError):
                    raise
                raise BffError(
                    ApiErrorCode.INPUT_INTEGRITY_MISMATCH,
                    "Finalized Model response is invalid",
                ) from exc
            detail = {"exception_type": type(exc).__name__}
            cleanup_succeeded = not storage_written
            if storage_written:
                try:
                    self._gateway.remove_source(reservation.model_id)
                    cleanup_succeeded = True
                except Exception as cleanup_exc:
                    detail["cleanup_exception_type"] = type(cleanup_exc).__name__
                    cleanup_succeeded = False
            try:
                self._gateway.record_failure(
                    reservation,
                    cleanup_succeeded=cleanup_succeeded,
                    error_code=("INGESTION_FAILED" if cleanup_succeeded else "INGESTION_CLEANUP_REQUIRED"),
                    error_detail=detail,
                )
            except Exception as diagnostic_exc:
                raise BffError(
                    ApiErrorCode.INGESTION_CLEANUP_REQUIRED,
                    "Upload recovery state could not be recorded",
                ) from diagnostic_exc
            if not cleanup_succeeded:
                raise BffError(
                    ApiErrorCode.INGESTION_CLEANUP_REQUIRED,
                    "Upload cleanup requires administrator attention",
                ) from exc
            raise BffError(ApiErrorCode.TRANSIENT_SYSTEM_ERROR, "Model ingestion failed safely") from exc


class ModelPublicationService:
    def __init__(
        self,
        sessions: AccessCodeSessionService,
        repository: Any,
        gateway: ModelIngestionGateway,
    ) -> None:
        self._sessions = sessions
        self._repository = repository
        self._gateway = gateway

    def set_publication(
        self,
        session_id: str,
        model_id: str,
        *,
        is_published: bool,
        is_default: bool = False,
    ) -> ModelPublicationResponse:
        self._sessions.require_admin(session_id)
        normalized_id = _uuid(model_id, "model_id")
        if is_default and not is_published:
            raise BffError(
                ApiErrorCode.VALIDATION_ERROR,
                "A default Model must be published",
                field_errors={"is_default": "requires_published"},
            )
        try:
            model = self._repository.get(normalized_id)
        except (KeyError, StopIteration) as exc:
            raise BffError(ApiErrorCode.MODEL_NOT_FOUND, "Model not found") from exc
        except Exception as exc:
            raise BffError(ApiErrorCode.TRANSIENT_SYSTEM_ERROR, "Model lookup failed") from exc
        sha = str(getattr(model, "workbook_sha256", "") or "")
        if is_published:
            if not SHA256_PATTERN.fullmatch(sha):
                raise BffError(ApiErrorCode.INPUT_INTEGRITY_MISMATCH, "Model source provenance is incomplete")
            try:
                self._gateway.verify_source(normalized_id, sha)
            except Exception as exc:
                raise BffError(ApiErrorCode.INPUT_INTEGRITY_MISMATCH, "Model source integrity verification failed") from exc
        try:
            saved = self._repository.set_publication(
                normalized_id,
                is_published=bool(is_published),
                is_default=bool(is_default),
            )
            return ModelPublicationResponse(model=_model_response(saved))
        except ValueError as exc:
            raise BffError(ApiErrorCode.VALIDATION_ERROR, "Model publication request is invalid") from exc
        except KeyError as exc:
            raise BffError(ApiErrorCode.MODEL_NOT_FOUND, "Model not found") from exc
        except Exception as exc:
            raise BffError(ApiErrorCode.INPUT_INTEGRITY_MISMATCH, "Model publication prerequisites are not satisfied") from exc


def _validate_request(request: ModelUploadRequest) -> ModelUploadRequest:
    name = str(request.name).strip() if isinstance(request.name, str) else ""
    model_type = str(request.model_type).strip().upper() if isinstance(request.model_type, str) else ""
    version = str(request.version).strip() if isinstance(request.version, str) else ""
    file_name = _safe_file_name(request.file_name)
    key = request.idempotency_key if isinstance(request.idempotency_key, str) else ""
    fields: dict[str, str] = {}
    if not name or len(name) > 200:
        fields["name"] = "must be 1-200 characters"
    if model_type not in MODEL_TYPES:
        fields["model_type"] = "must be PLAN, ACTUAL or FORECAST"
    if isinstance(request.model_year, bool) or not isinstance(request.model_year, int) or not 2000 <= request.model_year <= 2200:
        fields["model_year"] = "must be between 2000 and 2200"
    if not version or len(version) > 64:
        fields["version"] = "must be 1-64 characters"
    if not file_name:
        fields["file"] = "file name is invalid"
    if not IDEMPOTENCY_KEY_PATTERN.fullmatch(key):
        fields["idempotency_key"] = "invalid idempotency key"
    if fields:
        raise BffError(ApiErrorCode.VALIDATION_ERROR, "Model upload request is invalid", field_errors=fields)
    return ModelUploadRequest(
        name=name,
        model_type=model_type,
        model_year=request.model_year,
        version=version,
        file_name=file_name,
        idempotency_key=key,
    )


def _safe_file_name(value: Any) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 255:
        return ""
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        return ""
    normalized = value.strip().replace("\\", "/")
    name = normalized.rsplit("/", 1)[-1]
    if name in {"", ".", ".."} or name != normalized:
        return ""
    return name


def _validate_xlsx_package(path: Path, file_name: str) -> None:
    fields: dict[str, str] = {}
    if "/" in file_name or "\\" in file_name or file_name in {".", ".."}:
        fields["file"] = "file name must not contain a path"
    if Path(file_name).suffix.casefold() != ".xlsx":
        fields["file"] = "only .xlsx files are accepted"
    if not path.is_file():
        fields["file"] = "upload is missing"
    elif path.stat().st_size <= 0:
        fields["file"] = "upload is empty"
    elif path.stat().st_size > MAX_WORKBOOK_BYTES:
        fields["file"] = "file exceeds the 50MB limit"
    if fields:
        raise BffError(ApiErrorCode.VALIDATION_ERROR, "Workbook upload is invalid", field_errors=fields)
    try:
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
            if len(entries) > MAX_ZIP_ENTRIES:
                raise ValueError("too_many_entries")
            names: set[str] = set()
            expanded = 0
            for entry in entries:
                name = entry.filename.replace("\\", "/")
                if name in names or name.startswith("/") or any(part == ".." for part in name.split("/")):
                    raise ValueError("unsafe_or_duplicate_entry")
                names.add(name)
                if entry.flag_bits & 0x1:
                    raise ValueError("encrypted_entry")
                mode = entry.external_attr >> 16
                if mode and stat.S_ISLNK(mode):
                    raise ValueError("symlink_entry")
                if entry.file_size > MAX_ZIP_ENTRY_BYTES:
                    raise ValueError("entry_too_large")
                expanded += entry.file_size
                if expanded > MAX_ZIP_EXPANDED_BYTES:
                    raise ValueError("expanded_package_too_large")
                ratio = entry.file_size / max(entry.compress_size, 1)
                if ratio > MAX_ZIP_COMPRESSION_RATIO:
                    raise ValueError("compression_ratio_too_high")
            if not REQUIRED_XLSX_PARTS.issubset(names):
                raise ValueError("required_ooxml_parts_missing")
            if archive.testzip() is not None:
                raise ValueError("zip_crc_failed")
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        safe_reasons = {
            "too_many_entries", "unsafe_or_duplicate_entry", "encrypted_entry",
            "symlink_entry", "entry_too_large", "expanded_package_too_large",
            "compression_ratio_too_high", "required_ooxml_parts_missing", "zip_crc_failed",
        }
        reason = str(exc) if isinstance(exc, ValueError) and str(exc) in safe_reasons else "invalid_xlsx"
        raise BffError(
            ApiErrorCode.VALIDATION_ERROR,
            "Workbook is not a safe readable XLSX package",
            field_errors={"file": reason},
        ) from exc


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _uuid(value: str, field: str) -> str:
    try:
        return str(uuid.UUID(str(value)))
    except (TypeError, ValueError, AttributeError) as exc:
        raise BffError(
            ApiErrorCode.VALIDATION_ERROR,
            "Identifier is invalid",
            field_errors={field: "invalid UUID"},
        ) from exc


def _model_response(row: Any) -> AdminModelResponse:
    def read(name: str, fallback: str | None = None) -> Any:
        if isinstance(row, Mapping):
            return row.get(name, row.get(fallback)) if fallback else row.get(name)
        return getattr(row, name, getattr(row, fallback, None) if fallback else None)

    def required_text(name: str, fallback: str | None = None) -> str:
        value = read(name, fallback)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} is missing")
        return value.strip()

    try:
        raw_sha = read("workbook_sha256")
        sha = str(raw_sha) if raw_sha else None
        if sha is not None and not SHA256_PATTERN.fullmatch(sha):
            raise ValueError("invalid workbook SHA")
        model_type = required_text("model_type")
        if model_type not in {"PLAN", "ACTUAL", "FORECAST"}:
            raise ValueError("invalid model type")
        model_year = int(read("year", "model_year"))
        start_month = int(read("start_month"))
        end_month = int(read("end_month"))
        if not (2000 <= model_year <= 2200 and 1 <= start_month <= end_month <= 12):
            raise ValueError("invalid model period")
        is_published = read("is_published")
        is_default = read("is_default")
        if not isinstance(is_published, bool) or not isinstance(is_default, bool):
            raise ValueError("invalid publication flags")
        return AdminModelResponse(
            model_id=str(uuid.UUID(str(read("id", "model_id")))),
            display_name=required_text("name", "display_name"),
            model_type=model_type,
            model_year=model_year,
            start_month=start_month,
            end_month=end_month,
            version=required_text("version"),
            file_name=required_text("file_name"),
            workbook_sha256=sha,
            has_workbook_sha256=sha is not None,
            is_published=is_published,
            is_default=is_default,
            uploaded_at=required_text("uploaded_at"),
        )
    except (AttributeError, TypeError, ValueError) as exc:
        raise BffError(ApiErrorCode.INPUT_INTEGRITY_MISMATCH, "Model management contract is invalid") from exc
