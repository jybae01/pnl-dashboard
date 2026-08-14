from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

from ..provenance import ResultProvenance
from .dto import ModelUploadRequest
from .model_ingestion import (
    ModelIngestionCleanupRequiredError,
    ModelIngestionConflictError,
    ModelIngestionFinalizeUncertainError,
    ModelIngestionGateway,
    ModelIngestionInProgressError,
    ModelIngestionReservation,
)
from .forecast_orchestration import (
    ForecastFinalizeUncertainError, ForecastGenerateRequest, ForecastGateway, ForecastReservation,
)


class GatewayError(RuntimeError):
    pass


class GatewayValidationError(GatewayError):
    pass


class GatewayModelNotFoundError(GatewayError):
    pass


class GatewayIdempotencyConflictError(GatewayError):
    pass


class GatewayTransientError(GatewayError):
    pass


@dataclass(frozen=True)
class SubmissionRecord:
    job_id: str
    status: str
    idempotency_replayed: bool


class BffApplicationGateway(Protocol):
    def submit_analysis(
        self,
        *,
        baseline_model_id: str,
        comparison_model_id: str,
        start_month: int,
        end_month: int,
        baseline_sales_fx: float,
        comparison_sales_fx: float,
        idempotency_actor: str,
        idempotency_key: str,
        provenance: ResultProvenance,
        max_attempts: int,
    ) -> SubmissionRecord: ...

    def get_job_status(self, job_id: str) -> Mapping[str, Any] | None: ...

    def get_admin_result_preview(self, result_id: str) -> Mapping[str, Any] | None: ...

    def get_viewer_result(
        self,
        result_id: str,
        *,
        supported_result_schema_versions: Sequence[str],
    ) -> Mapping[str, Any] | None: ...

    def validate_result_availability(
        self,
        result_id: str,
        *,
        supported_result_schema_versions: Sequence[str],
    ) -> bool: ...

    def get_admin_evidence_payload(
        self, result_id: str, *, supported_result_schema_versions: Sequence[str]
    ) -> Mapping[str, Any] | None: ...

    def get_viewer_evidence_payload(
        self, result_id: str, *, supported_result_schema_versions: Sequence[str]
    ) -> Mapping[str, Any] | None: ...

    def get_admin_analysis_presentation(
        self, result_id: str, *, supported_result_schema_versions: Sequence[str]
    ) -> Mapping[str, Any] | None: ...

    def get_viewer_analysis_presentation(
        self, result_id: str, *, supported_result_schema_versions: Sequence[str]
    ) -> Mapping[str, Any] | None: ...

    def get_viewer_pnl_dashboard(
        self, *, supported_result_schema_versions: Sequence[str]
    ) -> Mapping[str, Any] | None: ...

    def list_calculation_history(
        self, *, limit: int, before_created_at: str | None, before_job_id: str | None
    ) -> list[Mapping[str, Any]]: ...

    def download_model_source(self, bucket: str, path: str) -> bytes: ...


def _data(response: Any) -> Any:
    if hasattr(response, "data"):
        return response.data
    if isinstance(response, Mapping):
        return response.get("data", response)
    return response


def _first(response: Any) -> dict[str, Any] | None:
    value = _data(response)
    if isinstance(value, list):
        return dict(value[0]) if value else None
    return dict(value) if value else None


def _bounded_payload(row: Mapping[str, Any] | None) -> Mapping[str, Any] | None:
    if row is None:
        return None
    payload = row.get("payload")
    if not isinstance(payload, Mapping):
        raise GatewayTransientError("bounded RPC returned an invalid shape")
    return dict(payload)


class SupabaseBffApplicationGateway:
    """Server-only adapter for the narrow Migration 005 RPC surface."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def submit_analysis(
        self,
        *,
        baseline_model_id: str,
        comparison_model_id: str,
        start_month: int,
        end_month: int,
        baseline_sales_fx: float,
        comparison_sales_fx: float,
        idempotency_actor: str,
        idempotency_key: str,
        provenance: ResultProvenance,
        max_attempts: int,
    ) -> SubmissionRecord:
        try:
            row = _first(self._client.rpc(
                "create_durable_calculation_job_idempotent",
                {
                    "p_baseline_model_id": baseline_model_id,
                    "p_comparison_model_id": comparison_model_id,
                    "p_start_month": start_month,
                    "p_end_month": end_month,
                    "p_baseline_sales_fx": baseline_sales_fx,
                    "p_comparison_sales_fx": comparison_sales_fx,
                    "p_idempotency_actor": idempotency_actor,
                    "p_idempotency_key": idempotency_key,
                    "p_engine_version": provenance.engine_version,
                    "p_mapping_version": provenance.mapping_version,
                    "p_mapping_hash": provenance.mapping_hash,
                    "p_result_schema_version": provenance.result_schema_version,
                    "p_max_attempts": max_attempts,
                },
            ).execute())
        except Exception as exc:
            self._raise_mapped(exc)
        if row is None:
            raise GatewayTransientError("idempotent job RPC returned no row")
        return SubmissionRecord(
            job_id=str(row["job_id"]),
            status=str(row["status"]),
            idempotency_replayed=bool(row["idempotency_replayed"]),
        )

    def get_job_status(self, job_id: str) -> Mapping[str, Any] | None:
        return self._read("get_calculation_job_status_by_id", {"p_job_id": job_id})

    def get_admin_result_preview(self, result_id: str) -> Mapping[str, Any] | None:
        return self._read(
            "get_calculation_result_admin_preview_by_id",
            {"p_result_id": result_id},
        )

    def get_viewer_result(
        self,
        result_id: str,
        *,
        supported_result_schema_versions: Sequence[str],
    ) -> Mapping[str, Any] | None:
        return self._read(
            "get_available_calculation_result_by_id",
            {
                "p_result_id": result_id,
                "p_supported_result_schema_versions": list(supported_result_schema_versions),
            },
        )

    def validate_result_availability(
        self,
        result_id: str,
        *,
        supported_result_schema_versions: Sequence[str],
    ) -> bool:
        try:
            value = _data(self._client.rpc(
                "validate_calculation_result_availability",
                {
                    "p_result_id": result_id,
                    "p_supported_result_schema_versions": list(
                        supported_result_schema_versions
                    ),
                },
            ).execute())
        except Exception as exc:
            raise GatewayTransientError("availability RPC failed") from exc
        if isinstance(value, list):
            value = value[0] if value else False
        if isinstance(value, Mapping):
            if len(value) != 1:
                raise GatewayTransientError("availability RPC returned an invalid shape")
            value = next(iter(value.values()))
        return bool(value)

    def get_admin_evidence_payload(
        self, result_id: str, *, supported_result_schema_versions: Sequence[str]
    ) -> Mapping[str, Any] | None:
        row = self._read("get_bounded_evidence_admin", {
            "p_result_id": result_id,
            "p_supported_result_schema_versions": list(supported_result_schema_versions),
        })
        return _bounded_payload(row)

    def get_viewer_evidence_payload(
        self, result_id: str, *, supported_result_schema_versions: Sequence[str]
    ) -> Mapping[str, Any] | None:
        row = self._read("get_bounded_evidence_viewer", {
            "p_result_id": result_id,
            "p_supported_result_schema_versions": list(supported_result_schema_versions),
        })
        return _bounded_payload(row)

    def get_admin_analysis_presentation(
        self, result_id: str, *, supported_result_schema_versions: Sequence[str]
    ) -> Mapping[str, Any] | None:
        return self._read("get_calculation_result_presentation_admin_by_id", {
            "p_result_id": result_id,
            "p_supported_result_schema_versions": list(supported_result_schema_versions),
        })

    def get_viewer_analysis_presentation(
        self, result_id: str, *, supported_result_schema_versions: Sequence[str]
    ) -> Mapping[str, Any] | None:
        return self._read("get_calculation_result_presentation_viewer_by_id", {
            "p_result_id": result_id,
            "p_supported_result_schema_versions": list(supported_result_schema_versions),
        })

    def get_viewer_pnl_dashboard(
        self, *, supported_result_schema_versions: Sequence[str]
    ) -> Mapping[str, Any] | None:
        return self._read("get_pnl_dashboard_viewer", {
            "p_supported_result_schema_versions": list(supported_result_schema_versions),
        })

    def list_calculation_history(
        self, *, limit: int, before_created_at: str | None, before_job_id: str | None
    ) -> list[Mapping[str, Any]]:
        try:
            value = _data(self._client.rpc("list_calculation_history_admin", {
                "p_limit": limit,
                "p_before_created_at": before_created_at,
                "p_before_job_id": before_job_id,
            }).execute())
        except Exception as exc:
            raise GatewayTransientError("history RPC failed") from exc
        if not isinstance(value, list):
            raise GatewayTransientError("history RPC returned an invalid shape")
        rows = [dict(row) for row in value]
        result_ids = [str(row["result_id"]) for row in rows if row.get("result_id")]
        if not result_ids:
            return rows

        # The history RPC intentionally exposes only the publication flag.  A
        # single narrow table read enriches completed rows with the independent
        # default/timestamp metadata, avoiding an N+1 result-preview sequence.
        try:
            publication_rows = _data(
                self._client.table("calculation_results")
                .select("id,is_default,published_at")
                .in_("id", result_ids)
                .execute()
            )
        except Exception as exc:
            raise GatewayTransientError("result publication lookup failed") from exc
        if not isinstance(publication_rows, list):
            raise GatewayTransientError("result publication lookup returned an invalid shape")
        by_id: dict[str, Mapping[str, Any]] = {}
        for row in publication_rows:
            if isinstance(row, Mapping) and row.get("id"):
                by_id[str(row["id"])] = row
        for row in rows:
            result_id = row.get("result_id")
            if not result_id:
                # Queued/running/failed history rows legitimately have no
                # calculation result yet and therefore no publication state.
                continue
            metadata = by_id.get(str(result_id))
            if metadata is None:
                # A completed history row's result must still exist: silently
                # defaulting publication metadata would misrepresent the
                # Dashboard eligibility state.  Fail closed instead.
                raise GatewayTransientError("result publication lookup missing result")
            if not isinstance(metadata.get("is_default"), bool):
                raise GatewayTransientError("result publication lookup returned invalid flags")
            if metadata["is_default"] and row.get("is_published") is not True:
                raise GatewayTransientError("result publication lookup returned inconsistent flags")
            published_at = metadata.get("published_at")
            if published_at is not None and not isinstance(published_at, (str,)):
                published_at = str(published_at)
            row["is_default"] = metadata["is_default"]
            row["published_at"] = published_at
        return rows

    def download_model_source(self, bucket: str, path: str) -> bytes:
        try:
            return bytes(self._client.storage.from_(bucket).download(path))
        except Exception as exc:
            raise GatewayTransientError("model source download failed") from exc

    def _read(self, name: str, params: Mapping[str, Any]) -> Mapping[str, Any] | None:
        try:
            return _first(self._client.rpc(name, dict(params)).execute())
        except Exception as exc:
            raise GatewayTransientError(f"{name} failed") from exc

    @staticmethod
    def _raise_mapped(exc: Exception) -> None:
        message = str(getattr(exc, "message", "") or exc)
        normalized = message.lower()
        if "idempotency_conflict" in normalized:
            raise GatewayIdempotencyConflictError("idempotency conflict") from exc
        if "model does not exist" in normalized:
            raise GatewayModelNotFoundError("model not found") from exc
        if any(token in normalized for token in (
            "must be", "is required", "invalid", "same year", "sha-256",
            "mapping provenance", "different",
        )):
            raise GatewayValidationError("analysis request was rejected") from exc
        raise GatewayTransientError("Supabase operation failed") from exc


class SupabaseModelIngestionGateway(ModelIngestionGateway):
    """Trusted-server adapter for Migration 007 and the private source bucket."""

    bucket = "pnl-models"

    def __init__(self, client: Any) -> None:
        self._client = client

    def reserve(
        self,
        *,
        actor: str,
        request: ModelUploadRequest,
        workbook_sha256: str,
        period_types: Mapping[str, str],
        provenance: ResultProvenance,
    ) -> ModelIngestionReservation:
        try:
            row = _first(self._client.rpc("reserve_model_ingestion", {
                "p_idempotency_actor": actor,
                "p_idempotency_key": request.idempotency_key,
                "p_name": request.name,
                "p_model_type": request.model_type,
                "p_model_year": request.model_year,
                "p_version": request.version,
                "p_file_name": request.file_name,
                "p_workbook_sha256": workbook_sha256,
                "p_period_types": dict(period_types),
                "p_mapping_version": provenance.mapping_version,
                "p_mapping_hash": provenance.mapping_hash,
            }).execute())
        except Exception as exc:
            message = str(exc).upper()
            if "IDEMPOTENCY_CONFLICT" in message:
                raise ModelIngestionConflictError from exc
            if "INGESTION_CLEANUP_REQUIRED" in message:
                raise ModelIngestionCleanupRequiredError from exc
            raise
        if row is None:
            raise RuntimeError("model ingestion reservation returned no row")
        status = str(row.get("ingestion_status") or "")
        if status == "in_progress":
            raise ModelIngestionInProgressError
        return ModelIngestionReservation(
            ingestion_id=str(row["ingestion_id"]),
            model_id=str(row["model_id"]),
            status=status,
            lease_token=(str(row["lease_token"]) if row.get("lease_token") else None),
            idempotency_replayed=bool(row.get("idempotency_replayed")),
        )

    def upload_source(self, model_id: str, source: Path, workbook_sha256: str) -> None:
        path = _model_source_path(model_id)
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
            # Recover a lost success response only when the canonical object is exact.
            try:
                self.verify_source(model_id, workbook_sha256)
                return
            except Exception:
                raise upload_exc

    def verify_source(self, model_id: str, workbook_sha256: str) -> None:
        payload = self._client.storage.from_(self.bucket).download(_model_source_path(model_id))
        if hashlib.sha256(bytes(payload)).hexdigest() != workbook_sha256:
            raise ValueError("stored source SHA-256 mismatch")

    def finalize(self, reservation: ModelIngestionReservation) -> Mapping[str, Any]:
        finalize_error: Exception | None = None
        try:
            row = _first(self._client.rpc("finalize_model_ingestion", {
                "p_ingestion_id": reservation.ingestion_id,
                "p_lease_token": reservation.lease_token,
            }).execute())
        except Exception as finalize_exc:
            finalize_error = finalize_exc
            row = None
        if row is None:
            try:
                row = _first(self._client.rpc("get_completed_model_ingestion", {
                    "p_ingestion_id": reservation.ingestion_id,
                }).execute())
            except Exception as recovery_exc:
                raise ModelIngestionFinalizeUncertainError from recovery_exc
            if row is None:
                if finalize_error is not None:
                    raise finalize_error
                raise RuntimeError("model ingestion finalization returned no row")
            try:
                self.verify_source(reservation.model_id, str(row["workbook_sha256"]))
            except Exception as integrity_exc:
                raise ModelIngestionFinalizeUncertainError from integrity_exc
        return row

    def remove_source(self, model_id: str) -> None:
        source_path = _model_source_path(model_id)
        bucket = self._client.storage.from_(self.bucket)
        bucket.remove([source_path])
        parent, name = source_path.rsplit("/", 1)
        remaining = bucket.list(parent, {"search": name, "limit": 10})
        if any(str(item.get("name")) == name for item in (remaining or [])):
            raise RuntimeError("Storage cleanup could not be verified")

    def record_failure(
        self,
        reservation: ModelIngestionReservation,
        *,
        cleanup_succeeded: bool,
        error_code: str,
        error_detail: Mapping[str, Any],
    ) -> None:
        self._client.rpc("record_model_ingestion_failure", {
            "p_ingestion_id": reservation.ingestion_id,
            "p_lease_token": reservation.lease_token,
            "p_cleanup_succeeded": cleanup_succeeded,
            "p_error_code": error_code,
            "p_error_detail": dict(error_detail),
        }).execute()

    def heartbeat(self, reservation: ModelIngestionReservation) -> None:
        self._client.rpc("heartbeat_model_ingestion", {
            "p_ingestion_id": reservation.ingestion_id,
            "p_lease_token": reservation.lease_token,
        }).execute()


def _model_source_path(model_id: str) -> str:
    normalized = str(uuid.UUID(str(model_id)))
    return f"models/{normalized}/source.xlsx"


class SupabaseForecastGateway(ForecastGateway):
    """Server-only Forecast operation and private Storage adapter."""

    bucket = "pnl-models"

    def __init__(self, client: Any, *, max_concurrency: int = 1, permit_lease_seconds: int = 1200) -> None:
        self._client = client
        self._max_concurrency = max_concurrency
        self._permit_lease_seconds = permit_lease_seconds

    def reserve(self, *, actor: str, request: ForecastGenerateRequest,
                payload: Mapping[str, Any], fingerprint: str,
                provenance: Any) -> ForecastReservation:
        row = _first(self._client.rpc("reserve_forecast_generation", {
            "p_idempotency_actor": actor,
            "p_idempotency_key": request.idempotency_key,
            "p_request_fingerprint": fingerprint,
            "p_request_payload": dict(payload),
            "p_base_model_id": request.base_model_id,
            "p_model_year": request.model_year,
            "p_mapping_version": provenance.mapping_version,
            "p_mapping_hash": provenance.mapping_hash,
            "p_engine_version": provenance.engine_version,
            "p_result_schema_version": provenance.result_schema_version,
        }).execute())
        if row is None:
            raise RuntimeError("forecast reservation returned no row")
        return ForecastReservation(
            generation_id=str(row["generation_id"]), model_id=str(row["model_id"]),
            status=str(row["generation_status"]),
            lease_token=str(row["lease_token"]) if row.get("lease_token") else None,
            replayed=bool(row.get("idempotency_replayed")),
            base_bucket=str(row["base_workbook_bucket"]),
            base_path=str(row["base_workbook_path"]),
            base_sha256=str(row["base_workbook_sha256"]),
        )

    def download_base(self, reservation: ForecastReservation) -> bytes:
        return bytes(self._client.storage.from_(reservation.base_bucket).download(reservation.base_path))

    def upload_generated(self, model_id: str, path: Path, sha256: str) -> None:
        target = _model_source_path(model_id)
        try:
            with path.open("rb") as payload:
                self._client.storage.from_(self.bucket).upload(path=target, file=payload,
                    file_options={"content-type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "upsert": "false"})
        except Exception as exc:
            try:
                self.verify_generated(model_id, sha256)
                return
            except Exception:
                raise exc

    def verify_generated(self, model_id: str, sha256: str) -> None:
        payload = bytes(self._client.storage.from_(self.bucket).download(_model_source_path(model_id)))
        if hashlib.sha256(payload).hexdigest() != sha256:
            raise ValueError("stored forecast SHA-256 mismatch")

    def finalize(self, reservation: ForecastReservation, *, sha256: str, name: str,
                 model_year: int, version: str, file_name: str,
                 period_types: Mapping[str, str], provenance: Any) -> Mapping[str, Any]:
        error: Exception | None = None
        try:
            row = _first(self._client.rpc("finalize_forecast_generation", {
                "p_generation_id": reservation.generation_id,
                "p_lease_token": reservation.lease_token,
                "p_generated_workbook_sha256": sha256,
                "p_name": name, "p_model_year": model_year, "p_version": version,
                "p_file_name": file_name, "p_period_types": dict(period_types),
                "p_mapping_version": provenance.mapping_version,
                "p_mapping_hash": provenance.mapping_hash,
                "p_engine_version": provenance.engine_version,
            }).execute())
        except Exception as exc:
            error = exc
            row = None
        if row is None:
            try:
                row = _first(self._client.rpc("get_completed_forecast_generation", {
                    "p_generation_id": reservation.generation_id,
                }).execute())
            except Exception as recovery_exc:
                raise ForecastFinalizeUncertainError from recovery_exc
            if row is None:
                if error: raise error
                raise RuntimeError("forecast finalization returned no row")
            try:
                self.verify_generated(reservation.model_id, str(row["workbook_sha256"]))
            except Exception as integrity_exc:
                raise ForecastFinalizeUncertainError from integrity_exc
        return row

    def remove_generated(self, model_id: str) -> None:
        source = _model_source_path(model_id)
        bucket = self._client.storage.from_(self.bucket)
        bucket.remove([source])
        parent, name = source.rsplit("/", 1)
        if any(str(item.get("name")) == name for item in (bucket.list(parent, {"search": name, "limit": 10}) or [])):
            raise RuntimeError("forecast cleanup could not be verified")

    def record_failure(self, reservation: ForecastReservation, *, cleanup_succeeded: bool,
                       error_code: str) -> None:
        self._client.rpc("record_forecast_generation_failure", {
            "p_generation_id": reservation.generation_id,
            "p_lease_token": reservation.lease_token,
            "p_cleanup_succeeded": cleanup_succeeded,
            "p_error_code": error_code,
        }).execute()

    def get_model(self, model_id: str) -> Mapping[str, Any] | None:
        return _first(self._client.table("models").select(
            "id,name,model_year,start_month,end_month,is_published,is_default,workbook_sha256,"
            "source_kind,source_model_id,forecast_generation_id,generation_input_fingerprint"
        ).eq("id", model_id).limit(1).execute())

    def acquire_execution_permit(self, operation_id: str) -> str:
        row = _first(self._client.rpc("acquire_forecast_execution_permit", {
            "p_operation_id": operation_id,
            "p_max_concurrency": self._max_concurrency,
            "p_lease_seconds": self._permit_lease_seconds,
        }).execute())
        if row is None or not row.get("lease_token"):
            raise RuntimeError("forecast permit acquisition returned no lease")
        return str(row["lease_token"])

    def renew_execution_permit(self, operation_id: str, lease_token: str) -> None:
        self._client.rpc("renew_forecast_execution_permit", {
            "p_operation_id": operation_id,
            "p_lease_token": lease_token,
            "p_lease_seconds": self._permit_lease_seconds,
        }).execute()

    def release_execution_permit(self, operation_id: str, lease_token: str) -> None:
        self._client.rpc("release_forecast_execution_permit", {
            "p_operation_id": operation_id,
            "p_lease_token": lease_token,
        }).execute()
