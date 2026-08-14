from __future__ import annotations

import math
import logging
import re
import uuid
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from ..provenance import ResultProvenance, SHA256_PATTERN
from .auth import AccessCodeSessionService
from .dto import (
    AdminResultPreviewResponse,
    AnalysisModelListResponse,
    AnalysisModelResponse,
    AnalysisSubmitRequest,
    AnalysisSubmitResponse,
    JobStatusResponse,
    ResultPublicationResponse,
    ResultProvenanceResponse,
    SessionResponse,
    SessionTicket,
    ViewerResultResponse,
)
from .errors import ApiErrorCode, BffError
from .gateway import (
    BffApplicationGateway,
    GatewayIdempotencyConflictError,
    GatewayModelNotFoundError,
    GatewayTransientError,
    GatewayValidationError,
)


IDEMPOTENCY_KEY_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
JOB_STATUSES = {"pending", "processing", "completed", "failed"}
LOGGER = logging.getLogger(__name__)


class AnalysisModelListService:
    """Narrow Admin model-selection capability over the existing repository."""

    def __init__(self, sessions: AccessCodeSessionService, repository: Any) -> None:
        self._sessions = sessions
        self._repository = repository

    def list_eligible(self, session_id: str) -> AnalysisModelListResponse:
        self._sessions.require_admin(session_id)
        try:
            rows = self._repository.list()
        except Exception as exc:
            raise BffError(
                ApiErrorCode.TRANSIENT_SYSTEM_ERROR,
                "Model list is temporarily unavailable",
            ) from exc
        models: list[AnalysisModelResponse] = []
        for row in rows:
            if not bool(getattr(row, "is_published", False)):
                continue
            if not getattr(row, "workbook_sha256", None):
                continue
            try:
                models.append(AnalysisModelResponse(
                    model_id=str(uuid.UUID(str(row.id))),
                    display_name=str(row.name),
                    model_type=str(row.model_type),
                    model_year=int(row.year),
                    start_month=int(row.start_month),
                    end_month=int(row.end_month),
                    is_published=True,
                    is_default=bool(row.is_default),
                ))
            except (AttributeError, TypeError, ValueError) as exc:
                raise BffError(
                    ApiErrorCode.INPUT_INTEGRITY_MISMATCH,
                    "Model list contract is invalid",
                ) from exc
        return AnalysisModelListResponse(models=tuple(models))


@dataclass(frozen=True)
class _ValidatedSubmit:
    baseline_model_id: str
    comparison_model_id: str
    start_month: int
    end_month: int
    baseline_sales_fx: float
    comparison_sales_fx: float
    idempotency_key: str


class AnalysisSubmissionService:
    def __init__(
        self,
        sessions: AccessCodeSessionService,
        gateway: BffApplicationGateway,
        provenance: ResultProvenance,
        *,
        max_attempts: int = 3,
        worker_control: Any | None = None,
    ) -> None:
        if not 1 <= max_attempts <= 20:
            raise ValueError("max_attempts must be between 1 and 20")
        self._sessions = sessions
        self._gateway = gateway
        self._provenance = provenance
        self._max_attempts = max_attempts
        self._worker_control = worker_control

    def submit(
        self,
        session_id: str,
        request: AnalysisSubmitRequest,
    ) -> AnalysisSubmitResponse:
        principal = self._sessions.require_admin(session_id)
        value = _validate_submit(request)
        try:
            record = self._gateway.submit_analysis(
                baseline_model_id=value.baseline_model_id,
                comparison_model_id=value.comparison_model_id,
                start_month=value.start_month,
                end_month=value.end_month,
                baseline_sales_fx=value.baseline_sales_fx,
                comparison_sales_fx=value.comparison_sales_fx,
                idempotency_actor=principal.actor_id,
                idempotency_key=value.idempotency_key,
                provenance=self._provenance,
                max_attempts=self._max_attempts,
            )
        except GatewayIdempotencyConflictError as exc:
            raise BffError(
                ApiErrorCode.IDEMPOTENCY_CONFLICT,
                "Idempotency key was already used for a different request",
            ) from exc
        except GatewayModelNotFoundError as exc:
            raise BffError(ApiErrorCode.MODEL_NOT_FOUND, "Model not found") from exc
        except GatewayValidationError as exc:
            raise BffError(
                ApiErrorCode.VALIDATION_ERROR,
                "Analysis request was rejected",
            ) from exc
        except GatewayTransientError as exc:
            raise BffError(
                ApiErrorCode.TRANSIENT_SYSTEM_ERROR,
                "Analysis submission is temporarily unavailable",
            ) from exc
        if record.status not in JOB_STATUSES:
            raise BffError(
                ApiErrorCode.INPUT_INTEGRITY_MISMATCH,
                "Job status contract is invalid",
            )
        execution_state = _execution_state(record.status)
        if record.status in {"pending", "processing"} and self._worker_control is not None:
            try:
                control = self._worker_control.ensure_after_enqueue()
                if record.status == "pending" and control.get("actual_instance_count") != 1:
                    execution_state = "STARTING_WORKER"
            except Exception:
                # The RPC above already committed the Job and pgmq message. A
                # control-plane failure must never turn durable work into loss;
                # the five-minute reconciler will retry the wake.
                LOGGER.warning(
                    "worker wake deferred to reconciler",
                    extra={"job_id": record.job_id, "worker_state": "QUEUED"},
                )
                execution_state = "QUEUED"
        return AnalysisSubmitResponse(
            job_id=record.job_id,
            status=record.status.upper(),
            execution_state=execution_state,
            idempotency_replayed=record.idempotency_replayed,
        )


class JobQueryService:
    def __init__(
        self,
        sessions: AccessCodeSessionService,
        gateway: BffApplicationGateway,
        worker_control: Any | None = None,
    ) -> None:
        self._sessions = sessions
        self._gateway = gateway
        self._worker_control = worker_control

    def get_by_id(self, session_id: str, job_id: str) -> JobStatusResponse:
        self._sessions.require_admin(session_id)
        normalized_id = _uuid(job_id, "job_id")
        try:
            row = self._gateway.get_job_status(normalized_id)
        except GatewayTransientError as exc:
            raise BffError(
                ApiErrorCode.TRANSIENT_SYSTEM_ERROR,
                "Job status is temporarily unavailable",
            ) from exc
        if row is None:
            raise BffError(ApiErrorCode.JOB_NOT_FOUND, "Job not found")
        status = str(row.get("status") or "").lower()
        if status not in JOB_STATUSES:
            raise BffError(
                ApiErrorCode.INPUT_INTEGRITY_MISMATCH,
                "Job status contract is invalid",
            )
        try:
            execution_state = _execution_state(status)
            if status == "pending" and self._worker_control is not None:
                try:
                    control = self._worker_control.status()
                    if control.get("actual_instance_count") != 1:
                        execution_state = "STARTING_WORKER"
                except Exception:
                    execution_state = "QUEUED"
            response = JobStatusResponse(
                job_id=str(row["job_id"]),
                status=status.upper(),
                baseline_model_id=str(row["baseline_model_id"]),
                comparison_model_id=str(row["comparison_model_id"]),
                start_month=int(row["start_month"]),
                end_month=int(row["end_month"]),
                attempt=int(row["attempt"]),
                max_attempts=int(row["max_attempts"]),
                created_at=str(row["created_at"]),
                heartbeat_at=_optional_text(row.get("heartbeat_at")),
                completed_at=_optional_text(row.get("completed_at")),
                result_id=_optional_text(row.get("result_id")),
                error_code=_optional_text(row.get("error_code")),
                # Stored worker/DB messages are diagnostic data and may contain
                # internals. Browser DTOs are derived only from the allowlisted code.
                error_message=_safe_job_error_message(row.get("error_code")),
                execution_state=execution_state,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise BffError(
                ApiErrorCode.INPUT_INTEGRITY_MISMATCH,
                "Job status contract is invalid",
            ) from exc
        if response.job_id != normalized_id or not (
            1 <= response.start_month <= response.end_month <= 12
        ):
            raise BffError(
                ApiErrorCode.INPUT_INTEGRITY_MISMATCH,
                "Job status contract is invalid",
            )
        return response


class ResultQueryService:
    def __init__(
        self,
        sessions: AccessCodeSessionService,
        gateway: BffApplicationGateway,
        *,
        supported_result_schema_versions: Sequence[str],
    ) -> None:
        versions = tuple(str(value).strip() for value in supported_result_schema_versions)
        if not versions or any(not value for value in versions):
            raise ValueError("at least one supported result schema version is required")
        self._sessions = sessions
        self._gateway = gateway
        self._supported_versions = versions

    def admin_preview(
        self,
        session_id: str,
        result_id: str,
    ) -> AdminResultPreviewResponse:
        self._sessions.require_admin(session_id)
        normalized_id = _uuid(result_id, "result_id")
        try:
            row = self._gateway.get_admin_result_preview(normalized_id)
        except GatewayTransientError as exc:
            raise BffError(
                ApiErrorCode.TRANSIENT_SYSTEM_ERROR,
                "Result preview is temporarily unavailable",
            ) from exc
        if row is None:
            raise BffError(ApiErrorCode.RESULT_NOT_FOUND, "Result not found")
        schema_version = str(row.get("result_schema_version") or "")
        if schema_version not in self._supported_versions:
            raise BffError(
                ApiErrorCode.INPUT_INTEGRITY_MISMATCH,
                "Result schema is not supported",
            )
        view, provenance = _result_parts(row)
        try:
            response = AdminResultPreviewResponse(
                result_id=str(row["result_id"]),
                job_id=str(row["job_id"]),
                analysis_view=view,
                provenance=provenance,
                is_published=bool(row["is_published"]),
                is_default=bool(row["is_default"]),
                published_at=_optional_text(row.get("published_at")),
                created_at=str(row["created_at"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise BffError(
                ApiErrorCode.INPUT_INTEGRITY_MISMATCH,
                "Result preview contract is invalid",
            ) from exc
        if response.result_id != normalized_id:
            raise BffError(
                ApiErrorCode.INPUT_INTEGRITY_MISMATCH,
                "Result preview contract is invalid",
            )
        return response

    def validate_result_availability(self, session_id: str, result_id: str) -> bool:
        self._sessions.require_viewer(session_id)
        normalized_id = _uuid(result_id, "result_id")
        try:
            return self._gateway.validate_result_availability(
                normalized_id,
                supported_result_schema_versions=self._supported_versions,
            )
        except GatewayTransientError as exc:
            raise BffError(
                ApiErrorCode.TRANSIENT_SYSTEM_ERROR,
                "Result availability is temporarily unavailable",
            ) from exc

    def viewer_read(self, session_id: str, result_id: str) -> ViewerResultResponse:
        self._sessions.require_viewer(session_id)
        normalized_id = _uuid(result_id, "result_id")
        try:
            row = self._gateway.get_viewer_result(
                normalized_id,
                supported_result_schema_versions=self._supported_versions,
            )
        except GatewayTransientError as exc:
            raise BffError(
                ApiErrorCode.TRANSIENT_SYSTEM_ERROR,
                "Result is temporarily unavailable",
            ) from exc
        if row is None:
            # Do not reveal whether an unavailable Result exists.
            raise BffError(ApiErrorCode.RESULT_NOT_AVAILABLE, "Result not available")
        if str(row.get("result_schema_version") or "") not in self._supported_versions:
            raise BffError(
                ApiErrorCode.INPUT_INTEGRITY_MISMATCH,
                "Result schema is not supported",
            )
        view, provenance = _result_parts(row)
        published_at = _optional_text(row.get("published_at"))
        if published_at is None:
            raise BffError(
                ApiErrorCode.INPUT_INTEGRITY_MISMATCH,
                "Published result contract is invalid",
            )
        try:
            response = ViewerResultResponse(
                result_id=str(row["result_id"]),
                job_id=str(row["job_id"]),
                analysis_view=view,
                provenance=provenance,
                is_default=bool(row["is_default"]),
                published_at=published_at,
                created_at=str(row["created_at"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise BffError(
                ApiErrorCode.INPUT_INTEGRITY_MISMATCH,
                "Published result contract is invalid",
            ) from exc
        if response.result_id != normalized_id:
            raise BffError(
                ApiErrorCode.INPUT_INTEGRITY_MISMATCH,
                "Published result contract is invalid",
            )
        return response


class ResultPublicationService:
    """Admin-only metadata publication over the existing trusted repository.

    The repository is server-side only and delegates to the narrow
    ``set_calculation_result_publication`` RPC.  This service performs the
    session check and shapes the RPC row into a minimal DTO before it crosses
    the HTTP boundary.
    """

    def __init__(self, sessions: AccessCodeSessionService, repository: Any) -> None:
        self._sessions = sessions
        self._repository = repository

    def set_publication(
        self,
        session_id: str,
        result_id: str,
        *,
        is_published: bool,
        is_default: bool = False,
    ) -> ResultPublicationResponse:
        self._sessions.require_admin(session_id)
        normalized_id = _uuid(result_id, "result_id")
        if not isinstance(is_published, bool) or not isinstance(is_default, bool):
            raise BffError(
                ApiErrorCode.VALIDATION_ERROR,
                "Result publication request is invalid",
                field_errors={"publication": "boolean flags are required"},
            )
        if is_default and not is_published:
            raise BffError(
                ApiErrorCode.VALIDATION_ERROR,
                "Result publication request is invalid",
                field_errors={"is_default": "requires_published"},
            )
        try:
            row = self._repository.set_publication(
                normalized_id,
                is_published=bool(is_published),
                is_default=bool(is_default),
            )
        except ValueError as exc:
            raise BffError(
                ApiErrorCode.VALIDATION_ERROR,
                "Result publication request is invalid",
            ) from exc
        except KeyError as exc:
            raise BffError(ApiErrorCode.RESULT_NOT_FOUND, "Result not found") from exc
        except Exception as exc:
            # Do not leak provider/SQL diagnostics.  The RPC validates the
            # completed-result provenance and published-model prerequisites;
            # expose only the established safe integrity taxonomy.
            raise BffError(
                ApiErrorCode.INPUT_INTEGRITY_MISMATCH,
                "Result publication prerequisites are not satisfied",
            ) from exc

        try:
            if not isinstance(row, Mapping):
                raise TypeError("publication response is not an object")
            returned_id = _uuid(row.get("id") or row.get("result_id"), "result_id")
            published = row.get("is_published")
            default = row.get("is_default")
            if not isinstance(published, bool) or not isinstance(default, bool):
                raise TypeError("publication flags are invalid")
            published_at = row.get("published_at")
            if published_at is not None:
                published_at = str(published_at)
            if (
                returned_id != normalized_id
                or (default and not published)
                or published != is_published
                or default != is_default
                or (published and published_at is None)
                or (not published and published_at is not None)
            ):
                raise ValueError("publication response does not match request")
            return ResultPublicationResponse(
                result_id=returned_id,
                is_published=published,
                is_default=default,
                published_at=published_at,
            )
        except BffError:
            raise
        except (KeyError, TypeError, ValueError) as exc:
            raise BffError(
                ApiErrorCode.INPUT_INTEGRITY_MISMATCH,
                "Result publication response is invalid",
            ) from exc


class TrustedBffApplication:
    """Framework-neutral boundary for a later HTTP/cookie transport adapter."""

    def __init__(
        self,
        sessions: AccessCodeSessionService,
        submissions: AnalysisSubmissionService,
        jobs: JobQueryService,
        results: ResultQueryService,
        models: AnalysisModelListService | None = None,
        model_management: Any | None = None,
        model_ingestion: Any | None = None,
        model_publication: Any | None = None,
        evidence: Any | None = None,
        history: Any | None = None,
        presentation: Any | None = None,
        pnl_dashboard: Any | None = None,
        forecast_generation: Any | None = None,
        worker_administration: Any | None = None,
        result_publication: ResultPublicationService | None = None,
    ) -> None:
        self.sessions = sessions
        self.submissions = submissions
        self.jobs = jobs
        self.results = results
        self.models = models
        self.model_management = model_management
        self.model_ingestion = model_ingestion
        self.model_publication = model_publication
        self.result_publication = result_publication
        self.evidence = evidence
        self.history = history
        self.presentation = presentation
        self.pnl_dashboard = pnl_dashboard
        self.forecast_generation = forecast_generation
        self.worker_administration = worker_administration

    def login(self, access_code: str) -> SessionTicket:
        return self.sessions.login(access_code)

    def validate_session(self, session_id: str) -> SessionResponse:
        return self.sessions.validate(session_id)

    def logout(self, session_id: str) -> None:
        self.sessions.logout(session_id)


class WorkerAdministrationService:
    """Server-authorized emergency controls over the private controller."""

    def __init__(self, sessions: AccessCodeSessionService, worker_control: Any) -> None:
        self._sessions = sessions
        self._worker_control = worker_control

    def status(self, session_id: str) -> Mapping[str, Any]:
        self._sessions.require_admin(session_id)
        return _safe_worker_status(self._call("status"))

    def emergency_wake(self, session_id: str) -> Mapping[str, Any]:
        self._sessions.require_admin(session_id)
        return _safe_worker_status(self._call("emergency_wake"))

    def safe_stop(self, session_id: str) -> Mapping[str, Any]:
        self._sessions.require_admin(session_id)
        try:
            return _safe_worker_status(self._call("safe_stop"))
        except Exception as exc:
            from ..worker_lifecycle import WorkerBusyError

            if isinstance(exc, WorkerBusyError):
                raise BffError(ApiErrorCode.WORKER_BUSY, "Worker has active work") from exc
            raise

    def _call(self, name: str) -> Mapping[str, Any]:
        try:
            value = getattr(self._worker_control, name)()
        except Exception as exc:
            from ..worker_lifecycle import WorkerBusyError

            if isinstance(exc, WorkerBusyError):
                raise
            raise BffError(
                ApiErrorCode.TRANSIENT_SYSTEM_ERROR,
                "Worker control is temporarily unavailable",
            ) from exc
        if not isinstance(value, Mapping):
            raise BffError(
                ApiErrorCode.INPUT_INTEGRITY_MISMATCH,
                "Worker control response is invalid",
            )
        return value


def _validate_submit(request: AnalysisSubmitRequest) -> _ValidatedSubmit:
    baseline = _uuid(request.baseline_model_id, "baseline_model_id")
    comparison = _uuid(request.comparison_model_id, "comparison_model_id")
    errors: dict[str, str] = {}
    if baseline == comparison:
        errors["comparison_model_id"] = "must be different from baseline_model_id"
    if isinstance(request.start_month, bool) or not isinstance(request.start_month, int):
        errors["start_month"] = "must be an integer from 1 through 12"
    if isinstance(request.end_month, bool) or not isinstance(request.end_month, int):
        errors["end_month"] = "must be an integer from 1 through 12"
    if not errors and not 1 <= request.start_month <= request.end_month <= 12:
        errors["period"] = "must satisfy 1 <= start_month <= end_month <= 12"
    baseline_fx = _positive_number(request.baseline_sales_fx, "baseline_sales_fx", errors)
    comparison_fx = _positive_number(
        request.comparison_sales_fx,
        "comparison_sales_fx",
        errors,
    )
    key = request.idempotency_key.strip() if isinstance(request.idempotency_key, str) else ""
    if not IDEMPOTENCY_KEY_PATTERN.fullmatch(key):
        errors["idempotency_key"] = "must be 1-128 characters: A-Z a-z 0-9 . _ : -"
    if errors:
        raise BffError(
            ApiErrorCode.VALIDATION_ERROR,
            "Analysis request is invalid",
            field_errors=errors,
        )
    return _ValidatedSubmit(
        baseline_model_id=baseline,
        comparison_model_id=comparison,
        start_month=request.start_month,
        end_month=request.end_month,
        baseline_sales_fx=baseline_fx,
        comparison_sales_fx=comparison_fx,
        idempotency_key=key,
    )


def _uuid(value: str, field_name: str) -> str:
    try:
        return str(uuid.UUID(str(value)))
    except (TypeError, ValueError, AttributeError) as exc:
        raise BffError(
            ApiErrorCode.VALIDATION_ERROR,
            "Request identifier is invalid",
            field_errors={field_name: "must be a UUID"},
        ) from exc


def _positive_number(value: Any, field_name: str, errors: dict[str, str]) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        errors[field_name] = "must be a positive finite number"
        return 0.0
    if isinstance(value, bool) or not math.isfinite(number) or number <= 0:
        errors[field_name] = "must be a positive finite number"
    return number


def _execution_state(status: str) -> str:
    return {
        "pending": "QUEUED",
        "processing": "PROCESSING",
        "completed": "COMPLETED",
        "failed": "FAILED",
    }[status]


def _safe_worker_status(value: Mapping[str, Any]) -> Mapping[str, Any]:
    integer_fields = (
        "desired_instance_count",
        "configured_instance_count",
        "queue_depth",
        "claimable_count",
        "pending_count",
        "processing_count",
        "active_lease_count",
        "active_heartbeat_count",
        "recovery_pending_count",
        "idle_seconds",
    )
    try:
        result: dict[str, Any] = {name: int(value[name]) for name in integer_fields}
        actual = value.get("actual_instance_count")
        result["actual_instance_count"] = None if actual is None else int(actual)
        result["work_exists"] = bool(value["work_exists"])
        result["platform_reconciling"] = bool(value["platform_reconciling"])
        result["platform_ready"] = bool(value["platform_ready"])
        result["operating_policy"] = str(value["operating_policy"])
        result["idle_policy_seconds"] = int(value["idle_policy_seconds"])
        result["last_worker_activity_at"] = str(value["last_worker_activity_at"])
        result["last_scaling_result"] = (
            None if value.get("last_scaling_result") is None
            else str(value["last_scaling_result"])
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise BffError(
            ApiErrorCode.INPUT_INTEGRITY_MISMATCH,
            "Worker control response is invalid",
        ) from exc
    counts = tuple(result[name] for name in integer_fields)
    if (
        any(count < 0 for count in counts)
        or result["desired_instance_count"] not in (0, 1)
        or result["configured_instance_count"] not in (0, 1)
        or result["actual_instance_count"] not in (None, 0, 1)
        or result["operating_policy"] != "DEMAND_ONLY"
        or result["idle_policy_seconds"] != 1800
    ):
        raise BffError(
            ApiErrorCode.INPUT_INTEGRITY_MISMATCH,
            "Worker control response is invalid",
        )
    result["dto_version"] = "1"
    return result


def _result_parts(
    row: Mapping[str, Any],
) -> tuple[Mapping[str, Any], ResultProvenanceResponse]:
    view = row.get("analysis_view")
    if not isinstance(view, Mapping):
        raise BffError(
            ApiErrorCode.INPUT_INTEGRITY_MISMATCH,
            "Result payload contract is invalid",
        )
    required = (
        "baseline_model_id",
        "comparison_model_id",
        "baseline_workbook_sha256",
        "comparison_workbook_sha256",
        "engine_version",
        "mapping_version",
        "mapping_hash",
        "result_schema_version",
    )
    if any(not row.get(key) for key in required):
        raise BffError(
            ApiErrorCode.INPUT_INTEGRITY_MISMATCH,
            "Result provenance contract is invalid",
        )
    if not SHA256_PATTERN.fullmatch(str(row["baseline_workbook_sha256"])):
        raise BffError(ApiErrorCode.INPUT_INTEGRITY_MISMATCH, "Result provenance is invalid")
    if not SHA256_PATTERN.fullmatch(str(row["comparison_workbook_sha256"])):
        raise BffError(ApiErrorCode.INPUT_INTEGRITY_MISMATCH, "Result provenance is invalid")
    if not SHA256_PATTERN.fullmatch(str(row["mapping_hash"])):
        raise BffError(ApiErrorCode.INPUT_INTEGRITY_MISMATCH, "Result provenance is invalid")
    return dict(view), ResultProvenanceResponse(
        baseline_model_id=str(row["baseline_model_id"]),
        comparison_model_id=str(row["comparison_model_id"]),
        baseline_workbook_sha256=str(row["baseline_workbook_sha256"]),
        comparison_workbook_sha256=str(row["comparison_workbook_sha256"]),
        engine_version=str(row["engine_version"]),
        mapping_version=str(row["mapping_version"]),
        mapping_hash=str(row["mapping_hash"]),
        result_schema_version=str(row["result_schema_version"]),
    )


def _optional_text(value: Any) -> str | None:
    return None if value is None else str(value)


def _safe_job_error_message(error_code: Any) -> str | None:
    if not error_code:
        return None
    code = str(error_code)
    messages = {
        "INPUT_INTEGRITY_MISMATCH": "Calculation input integrity check failed",
        "INPUT_PROVENANCE_UNRESOLVED": "Calculation input provenance is unresolved",
        "preflight_failed": "Workbook preflight failed",
        "upload_timeout": "Workbook upload timed out",
        "attempts_exhausted": "Calculation retry limit was reached",
    }
    return messages.get(code, "Calculation failed")
