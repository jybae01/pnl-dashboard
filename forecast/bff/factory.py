from __future__ import annotations

from typing import Any, Mapping, Sequence

from ..provenance import ResultProvenance
from .application import (
    AnalysisModelListService,
    AnalysisSubmissionService,
    JobQueryService,
    ResultQueryService,
    TrustedBffApplication,
)
from .auth import AccessCodeSessionService
from ..preflight import ExcelPreflightValidator
from .gateway import SupabaseBffApplicationGateway, SupabaseModelIngestionGateway
from .evidence_history import CalculationHistoryService, EvidenceDeliveryService
from .analysis_presentation import AnalysisPresentationService
from .pnl_dashboard import PnlDashboardService
from .model_ingestion import (
    ModelIngestionService,
    ModelManagementService,
    ModelPublicationService,
)


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
        ),
        jobs=JobQueryService(sessions, gateway),
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
                ExcelPreflightValidator(model_mapping),
                provenance,
            )
            if model_capabilities else None
        ),
        model_publication=(
            ModelPublicationService(sessions, model_repository, ingestion_gateway)
            if model_capabilities else None
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
    )
