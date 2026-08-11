from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class SessionResponse:
    role: str
    expires_at: str
    authenticated: bool = True
    dto_version: str = "1"


@dataclass(frozen=True)
class AnalysisModelResponse:
    model_id: str
    display_name: str
    model_type: str
    model_year: int
    start_month: int
    end_month: int
    is_published: bool
    is_default: bool
    dto_version: str = "1"


@dataclass(frozen=True)
class AnalysisModelListResponse:
    models: tuple[AnalysisModelResponse, ...]
    dto_version: str = "1"


@dataclass(frozen=True)
class AdminModelResponse:
    model_id: str
    display_name: str
    model_type: str
    model_year: int
    start_month: int
    end_month: int
    version: str
    file_name: str
    workbook_sha256: str | None
    has_workbook_sha256: bool
    is_published: bool
    is_default: bool
    uploaded_at: str
    dto_version: str = "1"


@dataclass(frozen=True)
class AdminModelListResponse:
    models: tuple[AdminModelResponse, ...]
    dto_version: str = "1"


@dataclass(frozen=True)
class ModelUploadRequest:
    name: str
    model_type: str
    model_year: int
    version: str
    file_name: str
    idempotency_key: str


@dataclass(frozen=True)
class ModelUploadResponse:
    model: AdminModelResponse
    idempotency_replayed: bool
    dto_version: str = "1"


@dataclass(frozen=True)
class ModelPublicationResponse:
    model: AdminModelResponse
    dto_version: str = "1"


@dataclass(frozen=True)
class AnalysisSubmitRequest:
    baseline_model_id: str
    comparison_model_id: str
    start_month: int
    end_month: int
    baseline_sales_fx: float
    comparison_sales_fx: float
    idempotency_key: str


@dataclass(frozen=True)
class AnalysisSubmitResponse:
    job_id: str
    status: str
    idempotency_replayed: bool
    dto_version: str = "1"


@dataclass(frozen=True)
class JobStatusResponse:
    job_id: str
    status: str
    baseline_model_id: str
    comparison_model_id: str
    start_month: int
    end_month: int
    attempt: int
    max_attempts: int
    created_at: str
    heartbeat_at: str | None
    completed_at: str | None
    result_id: str | None
    error_code: str | None
    error_message: str | None
    dto_version: str = "1"


@dataclass(frozen=True)
class ResultProvenanceResponse:
    baseline_model_id: str
    comparison_model_id: str
    baseline_workbook_sha256: str
    comparison_workbook_sha256: str
    engine_version: str
    mapping_version: str
    mapping_hash: str
    result_schema_version: str


@dataclass(frozen=True)
class AdminResultPreviewResponse:
    result_id: str
    job_id: str
    analysis_view: Mapping[str, Any]
    provenance: ResultProvenanceResponse
    is_published: bool
    is_default: bool
    published_at: str | None
    created_at: str
    dto_version: str = "1"


@dataclass(frozen=True)
class ViewerResultResponse:
    result_id: str
    job_id: str
    analysis_view: Mapping[str, Any]
    provenance: ResultProvenanceResponse
    is_default: bool
    published_at: str
    created_at: str
    dto_version: str = "1"


@dataclass(frozen=True)
class SessionTicket:
    """Internal transport handoff; place session_id only in a secure cookie."""

    session_id: str = field(repr=False)
    session: SessionResponse
