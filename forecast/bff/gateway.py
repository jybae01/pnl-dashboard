from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol, Sequence

from ..provenance import ResultProvenance


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
