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
class ForecastWorkbookArtifact:
    """Exact bytes for an authorized Forecast-generated workbook download.

    This is an internal transport handoff rather than a JSON browser DTO.  The
    bytes are fetched from private Storage after checking the authoritative
    Model row's recorded SHA-256; no Storage path crosses the HTTP boundary.
    """

    content: bytes = field(repr=False)
    filename: str
    media_type: str = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


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
class ResultPublicationResponse:
    """Narrow Admin result-publication response.

    Publication is metadata-only; the stored result payload and provenance are
    intentionally not returned by this mutation endpoint.
    """

    result_id: str
    is_published: bool
    is_default: bool
    published_at: str | None
    dto_version: str = "1"


@dataclass(frozen=True)
class ForecastAdjustmentMetadataResponse:
    adjustment_key: str
    display_name: str
    category: str
    section: str | None
    unit: str = "KRW"
    monthly_baseline_amounts: Mapping[int, float] = field(default_factory=dict)


@dataclass(frozen=True)
class ForecastInputMetadataResponse:
    base_model_id: str
    manufacturing: tuple[ForecastAdjustmentMetadataResponse, ...]
    sga: tuple[ForecastAdjustmentMetadataResponse, ...]
    reason_max_length: int = 500
    dto_version: str = "1"


@dataclass(frozen=True)
class ForecastInputIssue:
    code: str
    message: str
    severity: str = "ERROR"
    blocking: bool = True
    source_sheet: str | None = None
    source_row: int | None = None
    field: str | None = None


@dataclass(frozen=True)
class ForecastSalesPreviewRow:
    month: int
    product_code: str
    product_name: str
    product_group: str
    quantity: float
    amount: float
    source_sheet: str
    source_row: int


@dataclass(frozen=True)
class ForecastBusinessProductionPreviewRow:
    month: int
    process: str
    product_group: str
    quantity: float
    unit: str
    source_sheet: str
    source_row: int


@dataclass(frozen=True)
class ForecastInputUnitSummary:
    unit: str
    row_count: int
    quantity_total: float


@dataclass(frozen=True)
class ForecastInputPreviewResponse:
    valid: bool
    blocking: bool
    source_filename: str
    sales_rows: tuple[ForecastSalesPreviewRow, ...]
    business_production_rows: tuple[ForecastBusinessProductionPreviewRow, ...]
    issues: tuple[ForecastInputIssue, ...]
    sales_summary: tuple[ForecastInputUnitSummary, ...]
    production_summary: tuple[ForecastInputUnitSummary, ...]
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
    execution_state: str
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
    execution_state: str
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
class ViewerAnalysisResultOptionResponse:
    result_id: str
    label: str
    completed_at: str
    published_at: str


@dataclass(frozen=True)
class ViewerAnalysisResultListResponse:
    results: tuple[ViewerAnalysisResultOptionResponse, ...]
    dto_version: str = "1"


@dataclass(frozen=True)
class AnalysisPresentationIdentityResponse:
    result_id: str
    job_id: str
    baseline_model_id: str
    comparison_model_id: str
    baseline_model_name: str
    comparison_model_name: str
    start_month: int
    end_month: int
    baseline_sales_fx: float
    comparison_sales_fx: float
    result_schema_version: str
    completed_at: str
    is_published: bool
    is_default: bool
    published_at: str | None


@dataclass(frozen=True)
class AnalysisPresentationKpiResponse:
    baseline_revenue: float
    comparison_revenue: float
    revenue_delta: float
    baseline_operating_profit: float
    comparison_operating_profit: float
    operating_profit_delta: float
    effects_total: float
    residual: float


@dataclass(frozen=True)
class AnalysisDrilldownRowResponse:
    row_id: str
    label: str
    unit: str
    baseline: float | None
    comparison: float | None
    delta: float | None
    profit_effect: float | None
    note: str
    section: str | None = None


@dataclass(frozen=True)
class AnalysisDrilldownResponse:
    kind: str
    available: bool
    rows: tuple[AnalysisDrilldownRowResponse, ...]
    unavailable_reason: str | None = None


@dataclass(frozen=True)
class AnalysisPresentationEffectResponse:
    code: str
    label: str
    category: str
    profit_effect: float
    description: str
    drilldown: AnalysisDrilldownResponse


@dataclass(frozen=True)
class AnalysisResidualResponse:
    amount: float
    classification: str
    display_label: str


@dataclass(frozen=True)
class AnalysisProductGroupResponse:
    code: str
    display_name: str
    quantity_unit: str
    baseline_quantity: float
    comparison_quantity: float
    baseline_revenue: float
    comparison_revenue: float


@dataclass(frozen=True)
class AnalysisActivityResponse:
    process: str
    production_basis: str
    unit: str
    baseline: float
    comparison: float
    delta: float


@dataclass(frozen=True)
class AnalysisExecutiveSummaryResponse:
    operating_profit_delta: float
    top_positive_effects: tuple[AnalysisPresentationEffectResponse, ...]
    top_negative_effects: tuple[AnalysisPresentationEffectResponse, ...]
    residual: AnalysisResidualResponse


@dataclass(frozen=True)
class AnalysisPresentationResponse:
    identity: AnalysisPresentationIdentityResponse
    kpis: AnalysisPresentationKpiResponse
    effects: tuple[AnalysisPresentationEffectResponse, ...]
    residual: AnalysisResidualResponse
    product_groups: tuple[AnalysisProductGroupResponse, ...]
    manufacturing_activities: tuple[AnalysisActivityResponse, ...]
    executive_summary: AnalysisExecutiveSummaryResponse
    currency_unit: str = "KRW"
    dto_version: str = "1"


@dataclass(frozen=True)
class PnlDashboardResponse:
    result_id: str
    job_id: str
    identity: dict[str, Any]
    kpis: dict[str, Any]
    monthly_series: tuple[dict[str, Any], ...]
    pnl_statement: tuple[dict[str, Any], ...]
    manufacturing: dict[str, Any]
    sga: dict[str, Any]
    product_groups: tuple[dict[str, Any], ...]
    key_facts: dict[str, Any]
    result_schema_version: str
    completed_at: str
    published_at: str
    currency_unit: str = "KRW"
    dto_version: str = "1"


@dataclass(frozen=True)
class CalculationHistoryItem:
    job_id: str
    result_id: str | None
    status: str
    baseline_model_id: str
    baseline_model_name: str
    comparison_model_id: str
    comparison_model_name: str
    start_month: int | None
    end_month: int | None
    attempt: int
    max_attempts: int
    created_at: str
    completed_at: str | None
    error_code: str | None
    error_message: str | None
    is_published: bool
    is_default: bool = False
    published_at: str | None = None


@dataclass(frozen=True)
class CalculationHistoryResponse:
    items: tuple[CalculationHistoryItem, ...]
    next_before_created_at: str | None
    next_before_job_id: str | None
    dto_version: str = "1"


@dataclass(frozen=True)
class SessionTicket:
    """Internal transport handoff; place session_id only in a secure cookie."""

    session_id: str = field(repr=False)
    session: SessionResponse
