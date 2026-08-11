from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping


class ApiErrorCode(str, Enum):
    AUTH_REQUIRED = "AUTH_REQUIRED"
    FORBIDDEN = "FORBIDDEN"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    MODEL_NOT_FOUND = "MODEL_NOT_FOUND"
    IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"
    JOB_NOT_FOUND = "JOB_NOT_FOUND"
    RESULT_NOT_FOUND = "RESULT_NOT_FOUND"
    RESULT_NOT_AVAILABLE = "RESULT_NOT_AVAILABLE"
    INPUT_INTEGRITY_MISMATCH = "INPUT_INTEGRITY_MISMATCH"
    TRANSIENT_SYSTEM_ERROR = "TRANSIENT_SYSTEM_ERROR"


@dataclass(frozen=True)
class ApiError:
    code: ApiErrorCode
    message: str
    field_errors: Mapping[str, str] = field(default_factory=dict)
    correlation_id: str | None = None
    dto_version: str = "1"


class BffError(Exception):
    """Safe application error that may cross the trusted transport boundary."""

    def __init__(
        self,
        code: ApiErrorCode,
        message: str,
        *,
        field_errors: Mapping[str, str] | None = None,
        correlation_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.error = ApiError(
            code=code,
            message=message,
            field_errors=dict(field_errors or {}),
            correlation_id=correlation_id,
        )

    @property
    def code(self) -> ApiErrorCode:
        return self.error.code
