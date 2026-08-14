from __future__ import annotations

import hashlib
import hmac
import secrets
import tempfile
import threading
import time
import uuid
import logging
from urllib.parse import urlsplit
from collections import defaultdict, deque
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Annotated, Callable, Mapping, Protocol

from fastapi import Cookie, Depends, FastAPI, File, Form, Header, Query, Request, Response, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictFloat, StrictInt, StrictStr

from .application import TrustedBffApplication
from .dto import AnalysisSubmitRequest, ModelUploadRequest
from .errors import ApiErrorCode, BffError
from .model_ingestion import MAX_WORKBOOK_BYTES
from .forecast_orchestration import (
    ForecastAdjustmentInput, ForecastGenerateRequest, ForecastMonthInput,
    ForecastQuantityInput, ForecastSalesInput,
)
from .production import AuditSink, TrustedProxyPolicy
from ..temp_artifacts import temp_artifact_policy, temp_artifacts_configured


class LoginBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    access_code: StrictStr = Field(min_length=1, max_length=512)


class SubmitBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    baseline_model_id: StrictStr
    comparison_model_id: StrictStr
    start_month: StrictInt
    end_month: StrictInt
    baseline_sales_fx: StrictFloat | StrictInt
    comparison_sales_fx: StrictFloat | StrictInt
    idempotency_key: StrictStr


class ModelPublicationBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    is_published: StrictBool
    is_default: StrictBool = False


class ForecastSalesBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    product_code: StrictStr
    quantity: StrictFloat | StrictInt
    amount: StrictFloat | StrictInt


class ForecastQuantityBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    product_code: StrictStr
    quantity: StrictFloat | StrictInt


class ForecastAdjustmentBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    row: StrictInt | None = None
    adjustment_key: StrictStr | None = Field(default=None, max_length=32)
    amount: StrictFloat | StrictInt
    reason: StrictStr = Field(default="", max_length=500)


class ForecastMonthBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    month: StrictInt
    sales: list[ForecastSalesBody] = Field(max_length=100)
    production: list[ForecastQuantityBody] = Field(max_length=100)
    mcm: list[ForecastQuantityBody] = Field(default_factory=list, max_length=100)
    manufacturing_adjustments: list[ForecastAdjustmentBody] = Field(default_factory=list, max_length=500)
    sga_adjustments: list[ForecastAdjustmentBody] = Field(default_factory=list, max_length=500)
    disposal_adjustment: StrictFloat | StrictInt = 0
    disposal_reason: StrictStr = Field(default="", max_length=500)
    obsolescence_adjustment: StrictFloat | StrictInt = 0
    obsolescence_reason: StrictStr = Field(default="", max_length=500)
    new_business_goods_cogs: StrictFloat | StrictInt = 0
    new_business_goods_cogs_reason: StrictStr = Field(default="", max_length=500)
    uf_mbr_cogs_rate: StrictFloat | StrictInt = 0.85
    ix_cogs_rate: StrictFloat | StrictInt = 0.85
    uf_mbr_transport_rate: StrictFloat | StrictInt = 0.05
    ix_transport_rate: StrictFloat | StrictInt = 0.05
    ix_pack_liters: StrictFloat | StrictInt = 25
    ix_pack_cost: StrictFloat | StrictInt = 380
    plan_na_sa_sales: StrictFloat | StrictInt = 0
    na_sa_sales: StrictFloat | StrictInt = 0
    tariff_applicable_rate: StrictFloat | StrictInt = 0.10
    tariff_rate: StrictFloat | StrictInt = 0.13
    raw_material_basis: StrictStr = "model"
    raw_material_direct: StrictFloat | StrictInt | None = None
    raw_material_adjustment: StrictFloat | StrictInt = 0
    raw_material_reason: StrictStr = Field(default="", max_length=500)
    refund_rate: StrictFloat | StrictInt = 0.013


class ForecastGenerateBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    base_model_id: StrictStr
    name: StrictStr
    model_year: StrictInt
    version: StrictStr
    start_month: StrictInt
    end_month: StrictInt
    months: list[ForecastMonthBody] = Field(min_length=1, max_length=12)
    idempotency_key: StrictStr


@dataclass(frozen=True)
class HttpBffSettings:
    environment: str = "development"
    session_cookie_name: str = "pnl_session"
    csrf_cookie_name: str = "pnl_csrf"
    csrf_header_name: str = "X-CSRF-Token"
    cookie_secure: bool = False
    cookie_same_site: str = "strict"
    cookie_path: str = "/api"
    csrf_cookie_path: str = "/"
    session_ttl_seconds: int = 8 * 60 * 60
    csrf_secret: str = ""
    allowed_origins: tuple[str, ...] = ()
    forecast_request_max_bytes: int = 1024 * 1024

    def __post_init__(self) -> None:
        if self.environment not in {"development", "test", "production"}:
            raise ValueError("environment must be development, test, or production")
        if self.environment == "production" and not self.cookie_secure:
            raise ValueError("production session cookies must be Secure")
        if self.cookie_same_site not in {"strict", "lax"}:
            raise ValueError("cookie_same_site must be strict or lax")
        if len(self.csrf_secret) < 32:
            raise ValueError("CSRF secret must contain at least 32 characters")
        if not 60 <= self.session_ttl_seconds <= 86400:
            raise ValueError("session TTL must be 60-86400 seconds")
        if any(origin == "*" for origin in self.allowed_origins):
            raise ValueError("credentialed CORS must not use a wildcard origin")
        for origin in self.allowed_origins:
            parsed = urlsplit(origin)
            try:
                parsed.port
            except ValueError as exc:
                raise ValueError("allowed origins must contain a valid port") from exc
            if (parsed.scheme not in {"http", "https"} or not parsed.netloc or not parsed.hostname
                    or parsed.username is not None or parsed.password is not None
                    or parsed.path not in {"", "/"} or parsed.query or parsed.fragment
                    or "*" in origin or origin == "null"):
                raise ValueError("allowed origins must be explicit http(s) origins")
            if self.environment == "production" and parsed.scheme != "https":
                raise ValueError("production frontend origins must use https")
        if not 16 * 1024 <= self.forecast_request_max_bytes <= 1024 * 1024:
            raise ValueError("forecast request limit must be 16KiB-1MiB")


class LoginRateLimiter(Protocol):
    shared: bool

    def check(self, client_key: str) -> tuple[bool, int]: ...
    def record_failure(self, client_key: str) -> tuple[bool, int]: ...
    def record_success(self, client_key: str) -> None: ...


class InMemoryLoginRateLimiter:
    """Single-process development limiter; never represented as shared/durable."""

    shared = False

    def __init__(self, *, max_attempts: int = 5, window_seconds: int = 60) -> None:
        if max_attempts < 1 or window_seconds < 1:
            raise ValueError("rate limit values must be positive")
        self._max_attempts = max_attempts
        self._window = window_seconds
        self._attempts: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, client_key: str) -> tuple[bool, int]:
        now = time.monotonic()
        with self._lock:
            values = self._attempts[client_key]
            while values and now - values[0] >= self._window:
                values.popleft()
            if len(values) >= self._max_attempts:
                retry_after = max(1, int(self._window - (now - values[0])))
                return False, retry_after
            return True, 0

    def record_failure(self, client_key: str) -> tuple[bool, int]:
        now = time.monotonic()
        with self._lock:
            values = self._attempts[client_key]
            while values and now - values[0] >= self._window:
                values.popleft()
            values.append(now)
            if len(values) >= self._max_attempts:
                return False, max(1, int(self._window - (now - values[0])))
            return True, 0

    def record_success(self, client_key: str) -> None:
        with self._lock:
            self._attempts.pop(client_key, None)


def create_http_bff(
    application: TrustedBffApplication,
    *,
    settings: HttpBffSettings,
    rate_limiter: LoginRateLimiter | None = None,
    proxy_policy: TrustedProxyPolicy | None = None,
    audit_sink: AuditSink | None = None,
    readiness_check: Callable[[], bool] | None = None,
    production_execution_policy_ready: bool = False,
) -> FastAPI:
    limiter = rate_limiter or InMemoryLoginRateLimiter()
    proxy = proxy_policy or TrustedProxyPolicy()
    audit = audit_sink or AuditSink()
    if settings.environment == "production" and not limiter.shared:
        raise ValueError("production requires an injected shared login rate limiter")
    if settings.environment == "production" and not application.sessions.shared:
        raise ValueError("production requires an injected shared session store")
    if settings.environment == "production" and not audit.shared:
        raise ValueError("production requires an injected shared audit sink")
    if settings.environment == "production" and not settings.allowed_origins:
        raise ValueError("production requires an explicit frontend origin")
    if settings.environment == "production" and proxy_policy is None:
        raise ValueError("production requires an explicit trusted proxy policy")
    if settings.environment == "production" and readiness_check is None:
        raise ValueError("production requires an explicit readiness check")
    if settings.environment == "production" and not temp_artifacts_configured():
        raise ValueError("production requires an explicit temporary artifact policy")
    if settings.environment == "production" and not production_execution_policy_ready:
        raise ValueError("production requires isolated parser and Forecast execution policies")

    app = FastAPI(title="Profit Analysis Trusted BFF", version="1")
    if settings.allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.allowed_origins),
            allow_credentials=True,
            allow_methods=["GET", "POST"],
            allow_headers=["Content-Type", settings.csrf_header_name],
        )

    @app.middleware("http")
    async def correlation_id(request: Request, call_next):
        request.state.correlation_id = str(uuid.uuid4())
        upload_request = request.method == "POST" and request.url.path == "/api/admin/models"
        forecast_request = request.method == "POST" and request.url.path == "/api/admin/forecasts"
        limited_request = upload_request or forecast_request
        request_limit = (MAX_WORKBOOK_BYTES + 1024 * 1024) if upload_request else settings.forecast_request_max_bytes
        if limited_request:
            declared = request.headers.get("content-length")
            if declared is not None:
                try:
                    length = int(declared)
                except ValueError:
                    result = _error_response(
                        request, 422, ApiErrorCode.VALIDATION_ERROR, "Invalid Content-Length"
                    )
                    return _secure_response(result, request.state.correlation_id)
                # Multipart fields and boundaries receive a bounded allowance;
                # the staged file itself is still independently capped at 50MiB.
                if length > request_limit:
                    result = _error_response(
                        request,
                        413,
                        ApiErrorCode.VALIDATION_ERROR,
                        "Request exceeds the size limit",
                        {"file" if upload_request else "request": "request is too large"},
                    )
                    return _secure_response(result, request.state.correlation_id)
            # Starlette parses multipart before the endpoint executes. Cap the
            # ASGI receive stream too, so chunked or dishonest requests cannot
            # bypass the declared-length guard and exhaust parser temp storage.
            original_receive = request._receive
            received = 0
            body_too_large = False

            async def capped_receive():
                nonlocal received, body_too_large
                message = await original_receive()
                if message.get("type") == "http.request":
                    received += len(message.get("body", b""))
                    if received > request_limit:
                        body_too_large = True
                        # Starlette translates multipart receive failures into
                        # a generic 400. Record the authoritative limit breach
                        # and stop feeding the parser; the response is replaced
                        # with the stable 413 below.
                        return {"type": "http.request", "body": b"", "more_body": False}
                return message

            request._receive = capped_receive
        response = await call_next(request)
        if limited_request and body_too_large:
            result = _error_response(
                request,
                413,
                ApiErrorCode.VALIDATION_ERROR,
                "Request exceeds the size limit",
                {"file" if upload_request else "request": "request is too large"},
            )
            return _secure_response(result, request.state.correlation_id)
        response.headers["X-Correlation-ID"] = request.state.correlation_id
        response.headers["Cache-Control"] = "no-store"
        logging.getLogger("forecast.bff.http").info(
            "bff_request method=%s path=%s status=%s correlation_id=%s",
            request.method, request.url.path, response.status_code, request.state.correlation_id,
        )
        return response

    @app.get("/health/live", include_in_schema=False)
    def liveness():
        return {"status": "alive"}

    @app.get("/health/ready", include_in_schema=False)
    def readiness():
        try:
            ready = True if readiness_check is None else bool(readiness_check())
        except Exception:
            ready = False
        if not ready:
            return JSONResponse(status_code=503, content={"status": "not_ready"})
        return {"status": "ready"}

    @app.exception_handler(BffError)
    async def bff_error(request: Request, exc: BffError) -> JSONResponse:
        principal = getattr(request.state, "principal", None)
        if request.method in {"POST", "PUT", "PATCH", "DELETE"} and principal is not None:
            _audit(audit, event_type="mutation_failed", principal_id=principal.actor_id,
                   role=principal.role, session_ref=principal.session_ref,
                   correlation_id=request.state.correlation_id, outcome="failed",
                   error_code=exc.code.value)
        status = _status_for(exc.code)
        payload = asdict(exc.error)
        payload["code"] = exc.code.value
        payload["correlation_id"] = request.state.correlation_id
        return JSONResponse(status_code=status, content={"error": payload})

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        fields: dict[str, str] = {}
        for item in exc.errors():
            location = ".".join(str(value) for value in item.get("loc", ()) if value != "body")
            fields[location or "request"] = "invalid value"
        return _error_response(
            request,
            422,
            ApiErrorCode.VALIDATION_ERROR,
            "Request is invalid",
            fields,
        )

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logging.getLogger("forecast.bff.http").error(
            "unexpected_request_failure correlation_id=%s exception_class=%s",
            request.state.correlation_id, type(exc).__name__,
        )
        return _error_response(
            request,
            500,
            ApiErrorCode.TRANSIENT_SYSTEM_ERROR,
            "Service is temporarily unavailable",
        )

    def session_id(
        value: str | None = Cookie(default=None, alias=settings.session_cookie_name),
    ) -> str:
        if value is None:
            raise BffError(ApiErrorCode.AUTH_REQUIRED, "Authentication required")
        return value

    def viewer_session(request: Request, value: str = Depends(session_id)) -> str:
        request.state.principal = application.sessions.require_viewer(value)
        return value

    def admin_session(request: Request, value: str = Depends(session_id)) -> str:
        request.state.principal = application.sessions.require_admin(value)
        return value

    def csrf_guard(
        request: Request,
        value: str = Depends(session_id),
        csrf_cookie: str | None = Cookie(default=None, alias=settings.csrf_cookie_name),
        csrf_header: str | None = Header(default=None, alias=settings.csrf_header_name),
    ) -> None:
        if settings.environment == "production":
            origin = request.headers.get("origin")
            if origin not in settings.allowed_origins:
                raise BffError(ApiErrorCode.FORBIDDEN, "CSRF validation failed")
        expected = _csrf_token(settings.csrf_secret, value)
        if not csrf_cookie or not csrf_header:
            raise BffError(ApiErrorCode.FORBIDDEN, "CSRF validation failed")
        if not hmac.compare_digest(csrf_cookie, csrf_header):
            raise BffError(ApiErrorCode.FORBIDDEN, "CSRF validation failed")
        if not hmac.compare_digest(csrf_header, expected):
            raise BffError(ApiErrorCode.FORBIDDEN, "CSRF validation failed")

    @app.post("/api/session/login")
    def login(body: LoginBody, request: Request, response: Response):
        client_ip = proxy.client_ip(request.client.host if request.client else None, request.headers)
        client_key = hashlib.sha256(("login-client-v1:" + client_ip).encode("utf-8")).hexdigest()
        # Atomically reserve this attempt before credential verification. This
        # closes the multi-instance check-then-increment race.
        allowed, retry_after = limiter.record_failure(client_key)
        if not allowed:
            _audit(audit, event_type="login_lockout", correlation_id=request.state.correlation_id,
                   outcome="denied", error_code="AUTH_REQUIRED")
            result = _error_response(
                request,
                429,
                ApiErrorCode.AUTH_REQUIRED,
                "Login temporarily unavailable",
            )
            result.headers["Retry-After"] = str(retry_after)
            return result
        try:
            ticket = application.login(body.access_code)
        except BffError as exc:
            _audit(audit, event_type="login_failure", correlation_id=request.state.correlation_id,
                   outcome="denied", error_code=exc.code.value)
            raise
        limiter.record_success(client_key)
        principal = application.sessions.require_viewer(ticket.session_id)
        _audit(audit, event_type="login_success", principal_id=principal.actor_id,
               role=principal.role, session_ref=principal.session_ref,
               correlation_id=request.state.correlation_id, outcome="success")
        response.set_cookie(
            settings.session_cookie_name,
            ticket.session_id,
            max_age=settings.session_ttl_seconds,
            httponly=True,
            secure=settings.cookie_secure,
            samesite=settings.cookie_same_site,
            path=settings.cookie_path,
        )
        response.set_cookie(
            settings.csrf_cookie_name,
            _csrf_token(settings.csrf_secret, ticket.session_id),
            max_age=settings.session_ttl_seconds,
            httponly=False,
            secure=settings.cookie_secure,
            samesite=settings.cookie_same_site,
            path=settings.csrf_cookie_path,
        )
        return ticket.session

    @app.get("/api/session")
    def get_session(value: str = Depends(session_id)):
        return application.validate_session(value)

    @app.post("/api/session/logout", dependencies=[Depends(csrf_guard)])
    def logout(request: Request, response: Response, value: str = Depends(viewer_session)):
        principal = request.state.principal
        application.logout(value)
        _audit(audit, event_type="logout", principal_id=principal.actor_id, role=principal.role,
               session_ref=principal.session_ref, correlation_id=request.state.correlation_id,
               outcome="success")
        response.delete_cookie(settings.session_cookie_name, path=settings.cookie_path)
        response.delete_cookie(settings.csrf_cookie_name, path=settings.csrf_cookie_path)
        return {"authenticated": False, "dto_version": "1"}

    @app.get("/api/models")
    def list_models(value: str = Depends(admin_session)):
        if application.models is None:
            raise BffError(
                ApiErrorCode.TRANSIENT_SYSTEM_ERROR,
                "Model list capability is not configured",
            )
        return application.models.list_eligible(value)

    @app.get("/api/admin/models")
    def list_admin_models(value: str = Depends(admin_session)):
        if application.model_management is None:
            raise BffError(ApiErrorCode.TRANSIENT_SYSTEM_ERROR, "Model management capability is not configured")
        return application.model_management.list_models(value)

    @app.post("/api/admin/models", dependencies=[Depends(csrf_guard)])
    async def upload_model(
        request: Request,
        file: Annotated[UploadFile, File()],
        name: Annotated[str, Form(min_length=1, max_length=200)],
        model_type: Annotated[str, Form(min_length=1, max_length=32)],
        model_year: Annotated[str, Form(min_length=4, max_length=4)],
        version: Annotated[str, Form(min_length=1, max_length=64)],
        idempotency_key: Annotated[str, Form(min_length=1, max_length=128)],
        value: str = Depends(admin_session),
    ):
        if application.model_ingestion is None:
            raise BffError(ApiErrorCode.TRANSIENT_SYSTEM_ERROR, "Model ingestion capability is not configured")
        try:
            year = int(model_year)
        except ValueError as exc:
            raise BffError(
                ApiErrorCode.VALIDATION_ERROR,
                "Model upload request is invalid",
                field_errors={"model_year": "must be a four-digit year"},
            ) from exc
        staged: Path | None = None
        try:
            staged = await _stage_upload(file)
            upload_request = ModelUploadRequest(
                    name=name,
                    model_type=model_type,
                    model_year=year,
                    version=version,
                    file_name=file.filename or "",
                    idempotency_key=idempotency_key,
                )
            result = await run_in_threadpool(
                application.model_ingestion.ingest, value, upload_request, staged,
            )
            _operation_audit(audit, application, value, request, "model_upload", result.model.model_id)
            return result
        finally:
            await file.close()
            if staged is not None:
                staged.unlink(missing_ok=True)

    @app.post("/api/admin/models/{model_id}/publication", dependencies=[Depends(csrf_guard)])
    def set_model_publication(
        request: Request,
        model_id: str,
        body: ModelPublicationBody,
        value: str = Depends(admin_session),
    ):
        if application.model_publication is None:
            raise BffError(ApiErrorCode.TRANSIENT_SYSTEM_ERROR, "Model publication capability is not configured")
        result = application.model_publication.set_publication(
            value,
            model_id,
            is_published=body.is_published,
            is_default=body.is_default,
        )
        _operation_audit(audit, application, value, request, "model_publication", model_id)
        return result

    @app.post("/api/admin/results/{result_id}/publication", dependencies=[Depends(csrf_guard)])
    def set_result_publication(
        request: Request,
        result_id: str,
        body: ModelPublicationBody,
        value: str = Depends(admin_session),
    ):
        if application.result_publication is None:
            raise BffError(
                ApiErrorCode.TRANSIENT_SYSTEM_ERROR,
                "Result publication capability is not configured",
            )
        result = application.result_publication.set_publication(
            value,
            result_id,
            is_published=body.is_published,
            is_default=body.is_default,
        )
        _operation_audit(audit, application, value, request, "result_publication", result_id)
        return result

    @app.post("/api/analyses", dependencies=[Depends(csrf_guard)])
    def submit_analysis(request: Request, body: SubmitBody, value: str = Depends(admin_session)):
        result = application.submissions.submit(value, AnalysisSubmitRequest(**body.model_dump()))
        _operation_audit(audit, application, value, request, "analysis_submission", result.job_id)
        return result

    @app.get("/api/admin/worker")
    def worker_status(value: str = Depends(admin_session)):
        if application.worker_administration is None:
            raise BffError(
                ApiErrorCode.TRANSIENT_SYSTEM_ERROR,
                "Worker control capability is not configured",
            )
        return application.worker_administration.status(value)

    @app.post("/api/admin/worker/emergency-wake", dependencies=[Depends(csrf_guard)])
    def emergency_worker_wake(request: Request, value: str = Depends(admin_session)):
        if application.worker_administration is None:
            raise BffError(ApiErrorCode.TRANSIENT_SYSTEM_ERROR, "Worker control capability is not configured")
        result = application.worker_administration.emergency_wake(value)
        _operation_audit(audit, application, value, request, "worker_emergency_wake", "pnl-worker")
        return result

    @app.post("/api/admin/worker/safe-stop", dependencies=[Depends(csrf_guard)])
    def safe_worker_stop(request: Request, value: str = Depends(admin_session)):
        if application.worker_administration is None:
            raise BffError(ApiErrorCode.TRANSIENT_SYSTEM_ERROR, "Worker control capability is not configured")
        result = application.worker_administration.safe_stop(value)
        _operation_audit(audit, application, value, request, "worker_safe_stop", "pnl-worker")
        return result

    @app.post("/api/admin/forecasts", dependencies=[Depends(csrf_guard)])
    def generate_forecast(http_request: Request, body: ForecastGenerateBody, value: str = Depends(admin_session)):
        if application.forecast_generation is None:
            raise BffError(
                ApiErrorCode.FORECAST_SCOPE_NOT_APPROVED,
                "Synchronous Forecast is disabled",
            )
        def adjustments(entries, category: str):
            keys: list[str] = []
            for entry in entries:
                if (entry.row is None) == (entry.adjustment_key is None):
                    raise BffError(
                        ApiErrorCode.VALIDATION_ERROR,
                        "Forecast adjustment identity is invalid",
                        field_errors={"adjustment": "provide one adjustment identity"},
                    )
                if entry.adjustment_key is not None:
                    keys.append(entry.adjustment_key)
            resolved: Mapping[str, int] = {}
            if keys:
                if application.forecast_input_metadata is None:
                    raise BffError(
                        ApiErrorCode.TRANSIENT_SYSTEM_ERROR,
                        "Forecast input metadata capability is not configured",
                    )
                resolved = application.forecast_input_metadata.resolve_adjustment_keys(
                    value, body.base_model_id, category, tuple(keys),
                )
            return tuple(ForecastAdjustmentInput(
                row=(entry.row if entry.row is not None else resolved[str(entry.adjustment_key)]),
                amount=entry.amount,
                reason=entry.reason,
            ) for entry in entries)

        months = tuple(ForecastMonthInput(
            month=item.month,
            sales=tuple(ForecastSalesInput(**entry.model_dump()) for entry in item.sales),
            production=tuple(ForecastQuantityInput(**entry.model_dump()) for entry in item.production),
            mcm=tuple(ForecastQuantityInput(**entry.model_dump()) for entry in item.mcm),
            manufacturing_adjustments=adjustments(item.manufacturing_adjustments, "manufacturing"),
            sga_adjustments=adjustments(item.sga_adjustments, "sga"),
            **item.model_dump(exclude={"month", "sales", "production", "mcm", "manufacturing_adjustments", "sga_adjustments"}),
        ) for item in body.months)
        forecast_request = ForecastGenerateRequest(
            months=months,
            **body.model_dump(exclude={"months"}),
        )
        result = application.forecast_generation.generate(value, forecast_request)
        generation_id = result.get("generation_id") if isinstance(result, dict) else result.generation_id
        _operation_audit(audit, application, value, http_request, "forecast_generation", generation_id)
        return result

    @app.get("/api/admin/forecasts/input-metadata")
    def forecast_input_metadata(
        base_model_id: Annotated[str, Query(min_length=36, max_length=36)],
        value: str = Depends(admin_session),
    ):
        if application.forecast_input_metadata is None:
            raise BffError(
                ApiErrorCode.TRANSIENT_SYSTEM_ERROR,
                "Forecast input metadata capability is not configured",
            )
        return application.forecast_input_metadata.get(value, base_model_id)

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: str, value: str = Depends(admin_session)):
        return application.jobs.get_by_id(value, job_id)

    @app.get("/api/admin/results/{result_id}")
    def admin_result(result_id: str, value: str = Depends(admin_session)):
        return application.results.admin_preview(value, result_id)

    @app.get("/api/viewer/results/{result_id}")
    def viewer_result(result_id: str, value: str = Depends(viewer_session)):
        return application.results.viewer_read(value, result_id)

    @app.get("/api/admin/results/{result_id}/presentation")
    def admin_result_presentation(result_id: str, value: str = Depends(admin_session)):
        if application.presentation is None:
            raise BffError(
                ApiErrorCode.TRANSIENT_SYSTEM_ERROR,
                "Analysis presentation capability is not configured",
            )
        return application.presentation.admin_read(value, result_id)

    @app.get("/api/viewer/results/{result_id}/presentation")
    def viewer_result_presentation(result_id: str, value: str = Depends(viewer_session)):
        if application.presentation is None:
            raise BffError(
                ApiErrorCode.TRANSIENT_SYSTEM_ERROR,
                "Analysis presentation capability is not configured",
            )
        return application.presentation.viewer_read(value, result_id)

    @app.get("/api/viewer/pnl-dashboard")
    def viewer_pnl_dashboard(response: Response, value: str = Depends(viewer_session)):
        if application.pnl_dashboard is None:
            raise BffError(
                ApiErrorCode.TRANSIENT_SYSTEM_ERROR,
                "P&L dashboard capability is not configured",
            )
        response.headers["Cache-Control"] = "no-store, private"
        return application.pnl_dashboard.viewer_read(value)

    @app.get("/api/admin/results/{result_id}/evidence")
    def admin_evidence(request: Request, result_id: str, value: str = Depends(admin_session)):
        if application.evidence is None:
            raise BffError(ApiErrorCode.TRANSIENT_SYSTEM_ERROR, "Evidence capability is not configured")
        artifact = application.evidence.admin_download(value, result_id)
        _operation_audit(audit, application, value, request, "evidence_download", result_id)
        return FileResponse(
            artifact.path,
            media_type=artifact.media_type,
            filename=artifact.filename,
            background=BackgroundTask(artifact.cleanup),
        )

    @app.get("/api/viewer/results/{result_id}/evidence")
    def viewer_evidence(request: Request, result_id: str, value: str = Depends(viewer_session)):
        if application.evidence is None:
            raise BffError(ApiErrorCode.TRANSIENT_SYSTEM_ERROR, "Evidence capability is not configured")
        artifact = application.evidence.viewer_download(value, result_id)
        _operation_audit(audit, application, value, request, "evidence_download", result_id)
        return FileResponse(
            artifact.path,
            media_type=artifact.media_type,
            filename=artifact.filename,
            background=BackgroundTask(artifact.cleanup),
        )

    @app.get("/api/admin/calculation-history")
    def calculation_history(
        limit: Annotated[int, Query(ge=1, le=50)] = 25,
        before_created_at: str | None = None,
        before_job_id: str | None = None,
        value: str = Depends(admin_session),
    ):
        if application.history is None:
            raise BffError(ApiErrorCode.TRANSIENT_SYSTEM_ERROR, "History capability is not configured")
        return application.history.list_admin(
            value,
            limit=limit,
            before_created_at=before_created_at,
            before_job_id=before_job_id,
        )

    return app


async def _stage_upload(file: UploadFile) -> Path:
    suffix = Path(file.filename or "").suffix.casefold()
    if suffix != ".xlsx":
        raise BffError(
            ApiErrorCode.VALIDATION_ERROR,
            "Workbook upload is invalid",
            field_errors={"file": "only .xlsx files are accepted"},
        )
    policy = temp_artifact_policy()
    policy.ensure_capacity(MAX_WORKBOOK_BYTES)
    temporary = policy.make_file(prefix="pnl-model-", suffix=".xlsx")
    path = Path(temporary.name)
    size = 0
    try:
        with temporary:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_WORKBOOK_BYTES:
                    raise BffError(
                        ApiErrorCode.VALIDATION_ERROR,
                        "Workbook upload is invalid",
                        field_errors={"file": "file exceeds the 50MB limit"},
                    )
                temporary.write(chunk)
        if size == 0:
            raise BffError(
                ApiErrorCode.VALIDATION_ERROR,
                "Workbook upload is invalid",
                field_errors={"file": "upload is empty"},
            )
        return path
    except Exception:
        path.unlink(missing_ok=True)
        raise


def _csrf_token(secret: str, session_id: str) -> str:
    return hmac.new(
        secret.encode("utf-8"),
        ("csrf-v1:" + session_id).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _status_for(code: ApiErrorCode) -> int:
    return {
        ApiErrorCode.AUTH_REQUIRED: 401,
        ApiErrorCode.FORBIDDEN: 403,
        ApiErrorCode.VALIDATION_ERROR: 422,
        ApiErrorCode.MODEL_NOT_FOUND: 404,
        ApiErrorCode.IDEMPOTENCY_CONFLICT: 409,
        ApiErrorCode.JOB_NOT_FOUND: 404,
        ApiErrorCode.RESULT_NOT_FOUND: 404,
        ApiErrorCode.RESULT_NOT_AVAILABLE: 404,
        ApiErrorCode.INPUT_INTEGRITY_MISMATCH: 409,
        ApiErrorCode.INGESTION_CLEANUP_REQUIRED: 500,
        ApiErrorCode.EVIDENCE_GENERATION_FAILED: 500,
        ApiErrorCode.FORECAST_SCOPE_NOT_APPROVED: 403,
        ApiErrorCode.WORKER_BUSY: 409,
        ApiErrorCode.TRANSIENT_SYSTEM_ERROR: 503,
    }[code]


def _error_response(
    request: Request,
    status: int,
    code: ApiErrorCode,
    message: str,
    field_errors: dict[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={
            "error": {
                "code": code.value,
                "message": message,
                "field_errors": field_errors or {},
                "correlation_id": request.state.correlation_id,
                "dto_version": "1",
            }
        },
    )


def _audit(sink: AuditSink, **event) -> None:
    """Audit failure must not expose secrets or alter the public response body."""
    try:
        sink.record(**event)
    except Exception:
        logging.getLogger("forecast.bff.audit").error(
            "audit_write_failed event_type=%s correlation_id=%s",
            event.get("event_type"), event.get("correlation_id"),
        )


def _secure_response(response: Response, correlation_id: str) -> Response:
    response.headers["X-Correlation-ID"] = correlation_id
    response.headers["Cache-Control"] = "no-store"
    return response


def _operation_audit(
    sink: AuditSink, application: TrustedBffApplication, session_id: str,
    request: Request, operation_type: str, operation_id: str,
) -> None:
    del application, session_id
    principal = getattr(request.state, "principal", None)
    if principal is None:
        raise RuntimeError("authenticated operation has no principal context")
    _audit(
        sink,
        event_type=operation_type,
        principal_id=principal.actor_id,
        role=principal.role,
        session_ref=principal.session_ref,
        correlation_id=request.state.correlation_id,
        operation_type=operation_type,
        operation_id=_audit_operation_id(operation_type, operation_id),
        outcome="success",
    )


def _audit_operation_id(operation_type: str, operation_id: str) -> str:
    """Return the UUID storage key used by the existing audit schema.

    Domain resources such as a Worker Pool have stable names rather than UUIDs.
    Map those names deterministically without placing the raw identifier in a
    separate, unconstrained audit field.
    """
    try:
        return str(uuid.UUID(str(operation_id)))
    except (ValueError, TypeError, AttributeError):
        return str(uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"pnl-audit:{operation_type}:{operation_id}",
        ))
