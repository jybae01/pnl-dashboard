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
        return self._read("get_calculation_result_evidence_admin_by_id", {
            "p_result_id": result_id,
            "p_supported_result_schema_versions": list(supported_result_schema_versions),
        })

    def get_viewer_evidence_payload(
        self, result_id: str, *, supported_result_schema_versions: Sequence[str]
    ) -> Mapping[str, Any] | None:
        return self._read("get_calculation_result_evidence_viewer_by_id", {
            "p_result_id": result_id,
            "p_supported_result_schema_versions": list(supported_result_schema_versions),
        })

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
        return [dict(row) for row in value]

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


def _model_source_path(model_id: str) -> str:
    normalized = str(uuid.UUID(str(model_id)))
    return f"models/{normalized}/source.xlsx"
