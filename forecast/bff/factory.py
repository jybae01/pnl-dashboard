from __future__ import annotations

from typing import Any, Mapping, Sequence

from ..provenance import ResultProvenance
from .application import (
    AnalysisModelListService,
    AnalysisSubmissionService,
    JobQueryService,
    ResultPublicationService,
    ResultQueryService,
    TrustedBffApplication,
    WorkerAdministrationService,
)
from .auth import AccessCodeSessionService, SessionStore
from ..preflight import ExcelPreflightValidator
from .gateway import SupabaseBffApplicationGateway, SupabaseModelIngestionGateway, SupabaseForecastGateway
from .forecast_orchestration import ForecastGenerationService, V1_FORECAST_SYNC_MAX_MONTHS
from .forecast_input_metadata import ForecastInputMetadataService
from .forecast_input_preview import ForecastInputPreviewService
from .production_allocation import ForecastProductionAllocationService
from .forecast_download import ForecastWorkbookDownloadService
from .evidence_history import CalculationHistoryService, EvidenceDeliveryService
from .analysis_presentation import AnalysisPresentationService
from .pnl_dashboard import PnlDashboardService
from .model_ingestion import (
    ModelIngestionService,
    ModelManagementService,
    ModelPublicationService,
)
from ..persistence.supabase import SupabaseResultPublicationRepository
from .persistent_delete import PersistentDeleteService, SupabasePersistentDeleteGateway
from .pnl_reporting_ingestion import (
    PnlReportingIngestionService,
    SupabasePnlReportingGateway,
)
from .pnl_reporting_read import PnlReportingViewerService, SupabasePnlReportingReadGateway
from .pnl_reporting_template import PnlReportingTemplateService


def create_supabase_bff_application(
    *,
    supabase_client: Any,
    viewer_code: str,
    admin_code: str,
    actor_namespace_secret: str,
    provenance: ResultProvenance,
    supported_result_schema_versions: Sequence[str] | None = None,
    session_ttl_seconds: int = 8 * 60 * 60,
    max_attempts: int = 3,
    model_repository: Any | None = None,
    model_mapping: Mapping[str, Any] | None = None,
    mapping_path: str | None = None,
    forecast_merchandise_mapping: Mapping[str, Any] | None = None,
    forecast_merchandise_mapping_path: str | None = None,
    session_store: SessionStore | None = None,
    forecast_max_concurrency: int = 1,
    forecast_permit_lease_seconds: int = 1200,
    forecast_max_execution_seconds: int = 900,
    forecast_enabled: bool = False,
    forecast_sync_max_months: int = V1_FORECAST_SYNC_MAX_MONTHS,
    workbook_validator: Any | None = None,
    worker_control: Any | None = None,
) -> TrustedBffApplication:
    """Compose the server-only BFF boundary from explicit trusted inputs.

    No environment variable is read here, so merely defining a Supabase secret
    cannot switch the existing local backend. The later HTTP adapter owns
    Secure/HttpOnly/SameSite cookie transport and must never serialize the
    Supabase client or the internal SessionTicket.session_id in JSON.
    """

    sessions = AccessCodeSessionService(
        viewer_code=viewer_code,
        admin_code=admin_code,
        actor_namespace_secret=actor_namespace_secret,
        ttl_seconds=session_ttl_seconds,
        store=session_store,
    )
    gateway = SupabaseBffApplicationGateway(supabase_client)
    versions = tuple(supported_result_schema_versions or (provenance.result_schema_version,))
    ingestion_gateway = SupabaseModelIngestionGateway(supabase_client)
    model_capabilities = model_repository is not None and model_mapping is not None
    return TrustedBffApplication(
        sessions=sessions,
        submissions=AnalysisSubmissionService(
            sessions,
            gateway,
            provenance,
            max_attempts=max_attempts,
            worker_control=worker_control,
        ),
        jobs=JobQueryService(sessions, gateway, worker_control),
        results=ResultQueryService(
            sessions,
            gateway,
            supported_result_schema_versions=versions,
        ),
        models=(
            AnalysisModelListService(sessions, model_repository)
            if model_repository is not None else None
        ),
        model_management=(
            ModelManagementService(sessions, model_repository)
            if model_capabilities else None
        ),
        model_ingestion=(
            ModelIngestionService(
                sessions,
                model_repository,
                ingestion_gateway,
                workbook_validator or ExcelPreflightValidator(model_mapping),
                provenance,
            )
            if model_capabilities else None
        ),
        model_publication=(
            ModelPublicationService(sessions, model_repository, ingestion_gateway)
            if model_capabilities else None
        ),
        result_publication=ResultPublicationService(
            sessions,
            SupabaseResultPublicationRepository(supabase_client),
        ),
        evidence=(
            EvidenceDeliveryService(
                sessions,
                gateway,
                provenance,
                mapping_path=mapping_path,
                supported_result_schema_versions=versions,
            )
            if mapping_path else None
        ),
        history=CalculationHistoryService(sessions, gateway),
        presentation=AnalysisPresentationService(
            sessions,
            gateway,
            provenance,
            supported_result_schema_versions=versions,
        ),
        pnl_dashboard=PnlDashboardService(
            sessions,
            gateway,
            supported_result_schema_versions=versions,
        ),
        forecast_generation=(
            ForecastGenerationService(
                sessions, SupabaseForecastGateway(
                    supabase_client, max_concurrency=forecast_max_concurrency,
                    permit_lease_seconds=forecast_permit_lease_seconds,
                ), provenance, mapping_path, model_mapping,
                max_execution_seconds=forecast_max_execution_seconds,
                max_sync_months=forecast_sync_max_months,
                merchandise_mapping_path=forecast_merchandise_mapping_path,
                merchandise_mapping=forecast_merchandise_mapping,
            ) if forecast_enabled and model_capabilities and mapping_path else None
        ),
        forecast_input_metadata=(
            ForecastInputMetadataService(sessions, model_repository, model_mapping, provenance)
            if forecast_enabled and model_capabilities and mapping_path else None
        ),
        # Template/preview validation is a pure business-input capability and
        # does not require a model repository or the synchronous Forecast
        # execution gate.  Keep it available to Admin even when calculation is
        # disabled so operators can validate a workbook before enabling scope.
        forecast_input_preview=ForecastInputPreviewService(sessions),
        forecast_production_allocation=(
            ForecastProductionAllocationService(
                sessions, model_repository, model_mapping, provenance
            )
            if forecast_enabled and model_capabilities and mapping_path else None
        ),
        forecast_download=(
            ForecastWorkbookDownloadService(sessions, gateway)
            if forecast_enabled else None
        ),
        worker_administration=(
            WorkerAdministrationService(sessions, worker_control)
            if worker_control is not None else None
        ),
        persistent_delete=PersistentDeleteService(
            sessions, SupabasePersistentDeleteGateway(supabase_client)
        ),
        pnl_reporting_ingestion=PnlReportingIngestionService(
            sessions, SupabasePnlReportingGateway(supabase_client)
        ),
        pnl_reporting_read=PnlReportingViewerService(
            sessions, SupabasePnlReportingReadGateway(supabase_client)
        ),
        pnl_reporting_template=PnlReportingTemplateService(sessions),
    )
