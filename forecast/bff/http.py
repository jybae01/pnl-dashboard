from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
import time
import uuid
from collections import defaultdict, deque
from dataclasses import asdict, dataclass
from typing import Protocol

from fastapi import Cookie, Depends, FastAPI, Header, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StrictFloat, StrictInt, StrictStr

from .application import TrustedBffApplication
from .dto import AnalysisSubmitRequest
from .errors import ApiErrorCode, BffError


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

    def __post_init__(self) -> None:
        if self.environment not in {"development", "test", "production"}:
            raise ValueError("environment must be development, test, or production")
        if self.environment == "production" and not self.cookie_secure:
            raise ValueError("production session cookies must be Secure")
        if self.cookie_same_site not in {"strict", "lax"}:
            raise ValueError("cookie_same_site must be strict or lax")
        if len(self.csrf_secret) < 32:
            raise ValueError("CSRF secret must contain at least 32 characters")
        if self.session_ttl_seconds < 60:
            raise ValueError("session TTL must be at least 60 seconds")
        if any(origin == "*" for origin in self.allowed_origins):
            raise ValueError("credentialed CORS must not use a wildcard origin")


class LoginRateLimiter(Protocol):
    shared: bool

    def consume(self, client_key: str) -> tuple[bool, int]: ...


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

    def consume(self, client_key: str) -> tuple[bool, int]:
        now = time.monotonic()
        with self._lock:
            values = self._attempts[client_key]
            while values and now - values[0] >= self._window:
                values.popleft()
            if len(values) >= self._max_attempts:
                retry_after = max(1, int(self._window - (now - values[0])))
                return False, retry_after
            values.append(now)
            return True, 0


def create_http_bff(
    application: TrustedBffApplication,
    *,
    settings: HttpBffSettings,
    rate_limiter: LoginRateLimiter | None = None,
) -> FastAPI:
    limiter = rate_limiter or InMemoryLoginRateLimiter()
    if settings.environment == "production" and not limiter.shared:
        raise ValueError("production requires an injected shared login rate limiter")

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
        response = await call_next(request)
        response.headers["X-Correlation-ID"] = request.state.correlation_id
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(BffError)
    async def bff_error(request: Request, exc: BffError) -> JSONResponse:
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

    def viewer_session(value: str = Depends(session_id)) -> str:
        application.sessions.require_viewer(value)
        return value

    def admin_session(value: str = Depends(session_id)) -> str:
        application.sessions.require_admin(value)
        return value

    def csrf_guard(
        value: str = Depends(session_id),
        csrf_cookie: str | None = Cookie(default=None, alias=settings.csrf_cookie_name),
        csrf_header: str | None = Header(default=None, alias=settings.csrf_header_name),
    ) -> None:
        expected = _csrf_token(settings.csrf_secret, value)
        if not csrf_cookie or not csrf_header:
            raise BffError(ApiErrorCode.FORBIDDEN, "CSRF validation failed")
        if not hmac.compare_digest(csrf_cookie, csrf_header):
            raise BffError(ApiErrorCode.FORBIDDEN, "CSRF validation failed")
        if not hmac.compare_digest(csrf_header, expected):
            raise BffError(ApiErrorCode.FORBIDDEN, "CSRF validation failed")

    @app.post("/api/session/login")
    def login(body: LoginBody, request: Request, response: Response):
        client_key = request.client.host if request.client else "unknown"
        allowed, retry_after = limiter.consume(client_key)
        if not allowed:
            result = _error_response(
                request,
                429,
                ApiErrorCode.AUTH_REQUIRED,
                "Login temporarily unavailable",
            )
            result.headers["Retry-After"] = str(retry_after)
            return result
        ticket = application.login(body.access_code)
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
    def logout(response: Response, value: str = Depends(viewer_session)):
        application.logout(value)
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

    @app.post("/api/analyses", dependencies=[Depends(csrf_guard)])
    def submit_analysis(body: SubmitBody, value: str = Depends(admin_session)):
        return application.submissions.submit(value, AnalysisSubmitRequest(**body.model_dump()))

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: str, value: str = Depends(admin_session)):
        return application.jobs.get_by_id(value, job_id)

    @app.get("/api/admin/results/{result_id}")
    def admin_result(result_id: str, value: str = Depends(admin_session)):
        return application.results.admin_preview(value, result_id)

    @app.get("/api/viewer/results/{result_id}")
    def viewer_result(result_id: str, value: str = Depends(viewer_session)):
        return application.results.viewer_read(value, result_id)

    return app


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
