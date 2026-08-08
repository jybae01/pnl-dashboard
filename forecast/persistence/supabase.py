from __future__ import annotations

import uuid
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from ..mapping_config import MappingStatus, MappingVersion
from ..provenance import ResultProvenance
from ..storage import ModelMeta
from ..workbook import extract_period_types, infer_workbook_year
from .contracts import (
    CalculationJob,
    CalculationResultWrite,
    ClaimedJob,
    JobStatus,
)


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


def _row_to_model(row: Mapping[str, Any]) -> ModelMeta:
    published = bool(row.get("is_published", row.get("confirmed", False)))
    return ModelMeta(
        id=str(row["id"]),
        name=str(row["name"]),
        model_type=str(row["model_type"]),
        year=int(row.get("model_year", row.get("year"))),
        start_month=int(row.get("start_month", 1)),
        end_month=int(row.get("end_month", 12)),
        created_date=str(row.get("created_date") or ""),
        version=str(row.get("version") or "V1"),
        confirmed=published,
        file_name=str(row.get("file_name") or "model.xlsx"),
        uploaded_at=str(row.get("uploaded_at") or row.get("created_at") or ""),
        regional_sales_monthly=dict(row.get("regional_sales_monthly") or {}),
        tariff_applicable_rate=float(row.get("tariff_applicable_rate", 0.10)),
        tariff_rate=float(row.get("tariff_rate", 0.13)),
        tariff_adjustment_monthly=dict(row.get("tariff_adjustment_monthly") or {}),
        tariff_in_workbook=bool(row.get("tariff_in_workbook", False)),
        period_types=dict(row.get("period_types") or {}),
        is_published=published,
        is_default=bool(row.get("is_default", False)),
        mapping_status=str(row.get("mapping_status") or ("published" if published else "draft")),
        mapping_version=str(row.get("mapping_version") or "legacy"),
        mapping_hash=str(row.get("mapping_hash") or ""),
    )


def _row_to_job(row: Mapping[str, Any]) -> CalculationJob:
    return CalculationJob(
        id=str(row["id"]),
        model_id=str(row["model_id"]),
        status=JobStatus(str(row["status"])),
        storage_bucket=str(row["storage_bucket"]),
        storage_path=str(row["storage_path"]),
        engine_version=str(row["engine_version"]),
        mapping_version=str(row["mapping_version"]),
        mapping_hash=str(row["mapping_hash"]),
        result_schema_version=str(row["result_schema_version"]),
        upload_completed_at=row.get("upload_completed_at"),
        attempt=int(row.get("attempt", 0)),
        max_attempts=int(row.get("max_attempts", 3)),
        claimed_by=row.get("claimed_by"),
        claim_token=str(row["claim_token"]) if row.get("claim_token") else None,
        heartbeat_at=row.get("heartbeat_at"),
        lease_expires_at=row.get("lease_expires_at"),
        error_code=row.get("error_code"),
        error_message=row.get("error_message"),
        error_detail=dict(row.get("error_detail") or {}),
        created_by=str(row["created_by"]) if row.get("created_by") else None,
        created_at=str(row.get("created_at") or ""),
        updated_at=str(row.get("updated_at") or ""),
    )


class SupabaseModelRepositoryAdapter:
    """Supabase DB/Storage implementation of the legacy model API.

    Streamlit's primary upload path is the Edge Function signed-upload flow.
    ``add`` remains available only as a trusted server-side compatibility path.
    """

    def __init__(self, client: Any, cache_directory: str | Path, *, bucket: str = "pnl-models"):
        self.client = client
        self.cache_directory = Path(cache_directory)
        self.cache_directory.mkdir(parents=True, exist_ok=True)
        self.bucket = bucket

    def list(self) -> list[ModelMeta]:
        response = self.client.table("models").select("*").order("uploaded_at", desc=True).execute()
        return [_row_to_model(row) for row in (_data(response) or [])]

    def get(self, model_id: str) -> ModelMeta:
        row = _first(
            self.client.table("models").select("*").eq("id", model_id).limit(1).execute()
        )
        if row is None:
            raise KeyError(model_id)
        return _row_to_model(row)

    def path(self, model_id: str) -> Path:
        row = _first(
            self.client.table("models")
            .select("workbook_bucket,workbook_path")
            .eq("id", model_id)
            .limit(1)
            .execute()
        )
        if row is None:
            raise KeyError(model_id)
        target = self.cache_directory / model_id / "model.xlsx"
        target.parent.mkdir(parents=True, exist_ok=True)
        content = self.client.storage.from_(row["workbook_bucket"]).download(row["workbook_path"])
        temporary = target.with_suffix(".downloading")
        temporary.write_bytes(content)
        temporary.replace(target)
        return target

    def add(self, content: bytes, **metadata: Any) -> ModelMeta:
        model_id = str(uuid.uuid4())
        temporary = self.cache_directory / f"{model_id}.uploading.xlsx"
        temporary.write_bytes(content)
        try:
            period_types = metadata.get("period_types") or extract_period_types(temporary)
            model_year = metadata.get("year") or infer_workbook_year(temporary)
        finally:
            temporary.unlink(missing_ok=True)
        published = bool(metadata.get("is_published", metadata.get("confirmed", False)))
        is_default = bool(metadata.get("is_default", False))
        if is_default and not published:
            raise ValueError("a default model must be published")
        path = f"models/{model_id}/source.xlsx"
        self.client.storage.from_(self.bucket).upload(
            path,
            content,
            {"content-type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
        )
        row = {
            "id": model_id,
            "name": str(metadata.get("name") or "").strip(),
            "model_type": str(metadata.get("model_type") or ""),
            "model_year": int(model_year),
            "start_month": 1,
            "end_month": 12,
            "created_date": metadata.get("created_date") or datetime.now().date().isoformat(),
            "version": str(metadata.get("version") or "V1"),
            "confirmed": published,
            "is_published": published,
            "is_default": is_default,
            "file_name": str(metadata.get("file_name") or "model.xlsx"),
            "workbook_bucket": self.bucket,
            "workbook_path": path,
            "period_types": period_types,
            "regional_sales_monthly": metadata.get("regional_sales_monthly") or {},
            "tariff_applicable_rate": float(metadata.get("tariff_applicable_rate", 0.10)),
            "tariff_rate": float(metadata.get("tariff_rate", 0.13)),
            "tariff_adjustment_monthly": metadata.get("tariff_adjustment_monthly") or {},
            "tariff_in_workbook": bool(metadata.get("tariff_in_workbook", False)),
            "mapping_status": metadata.get("mapping_status") or ("published" if published else "draft"),
            "mapping_version": str(metadata.get("mapping_version") or "legacy"),
            "mapping_hash": str(metadata.get("mapping_hash") or ""),
        }
        saved = _first(self.client.table("models").insert(row).execute())
        return _row_to_model(saved or row)

    def set_publication(
        self,
        model_id: str,
        *,
        is_published: bool,
        is_default: bool = False,
    ) -> ModelMeta:
        if is_default and not is_published:
            raise ValueError("a default model must be published")
        row = _first(self.client.rpc("set_model_publication", {
            "p_model_id": model_id,
            "p_is_published": bool(is_published),
            "p_is_default": bool(is_default),
        }).execute())
        if row is None:
            raise KeyError(model_id)
        return _row_to_model(row)


class SupabaseCalculationJobRepository:
    def __init__(self, client: Any):
        self.client = client

    def enqueue(
        self,
        *,
        model_id: str,
        storage_bucket: str,
        storage_path: str,
        provenance: ResultProvenance,
        created_by: str | None = None,
        max_attempts: int = 3,
    ) -> CalculationJob:
        row = {
            "model_id": model_id,
            "status": JobStatus.PENDING.value,
            "storage_bucket": storage_bucket,
            "storage_path": storage_path,
            # Direct repository enqueue means the caller has already placed
            # the object. Edge initialization uses the DB RPC instead and
            # remains unclaimable until /jobs/{id}/uploaded verifies Storage.
            "upload_completed_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            **provenance.as_dict(),
            "created_by": created_by,
            "max_attempts": max_attempts,
        }
        saved = _first(self.client.table("calculation_jobs").insert(row).execute())
        if saved is None:
            raise RuntimeError("Supabase did not return the inserted calculation job")
        return _row_to_job(saved)

    def claim_next(self, worker_id: str, *, lease_seconds: int = 300) -> ClaimedJob | None:
        row = _first(self.client.rpc(
            "claim_calculation_job",
            {"p_worker_id": worker_id, "p_lease_seconds": lease_seconds},
        ).execute())
        if row is None:
            return None
        job = _row_to_job(row)
        if not job.claim_token:
            raise RuntimeError("claimed job is missing its claim token")
        return ClaimedJob(job=job, claim_token=job.claim_token)

    def heartbeat(self, claim: ClaimedJob, *, lease_seconds: int = 300) -> bool:
        value = _data(self.client.rpc(
            "heartbeat_calculation_job",
            {
                "p_job_id": claim.job.id,
                "p_claim_token": claim.claim_token,
                "p_lease_seconds": lease_seconds,
            },
        ).execute())
        return bool(value[0] if isinstance(value, list) and value else value)

    def complete(self, claim: ClaimedJob, result: CalculationResultWrite) -> str:
        params = {
            "p_job_id": claim.job.id,
            "p_claim_token": claim.claim_token,
            "p_result": result.payload,
            "p_engine_version": result.provenance.engine_version,
            "p_mapping_version": result.provenance.mapping_version,
            "p_mapping_hash": result.provenance.mapping_hash,
            "p_result_schema_version": result.provenance.result_schema_version,
            "p_workbook_bucket": result.workbook_bucket,
            "p_workbook_path": result.workbook_path,
            "p_is_published": result.publish,
            "p_is_default": result.make_default,
        }
        value = _data(self.client.rpc("complete_calculation_job", params).execute())
        if isinstance(value, list):
            value = value[0] if value else None
        if not value:
            raise RuntimeError("Supabase did not return a calculation result id")
        return str(value)

    def fail(
        self,
        claim: ClaimedJob,
        *,
        error_code: str,
        error_message: str,
        error_detail: dict[str, Any] | None = None,
        retryable: bool = False,
    ) -> JobStatus:
        value = _data(self.client.rpc(
            "fail_calculation_job",
            {
                "p_job_id": claim.job.id,
                "p_claim_token": claim.claim_token,
                "p_error_code": error_code,
                "p_error_message": error_message,
                "p_error_detail": error_detail or {},
                "p_retryable": retryable,
            },
        ).execute())
        if isinstance(value, list):
            value = value[0] if value else None
        return JobStatus(str(value))


class SupabaseResultRepository:
    def __init__(self, client: Any):
        self.client = client

    def load(self) -> dict[str, Any] | None:
        row = _first(
            self.client.table("calculation_results")
            .select("*")
            .eq("is_published", True)
            .order("is_default", desc=True)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if row is None:
            return None
        payload = dict(row.get("result") or {})
        payload.update({
            key: row.get(key)
            for key in (
                "id", "job_id", "model_id", "engine_version", "mapping_version",
                "mapping_hash", "result_schema_version", "workbook_bucket", "workbook_path",
            )
        })
        return payload


class SupabaseMappingConfigRepository:
    def __init__(self, client: Any):
        self.client = client

    def create_draft(self, config_key: str, version: str, content: Mapping[str, Any]) -> MappingVersion:
        draft = MappingVersion.draft(config_key, version, content)
        row = asdict(draft)
        row["status"] = draft.status.value
        saved = _first(self.client.table("app_config").insert(row).execute())
        return self._from_row(saved or row)

    def validate(self, config_key: str, version: str) -> MappingVersion:
        row = _first(self.client.rpc(
            "validate_app_config",
            {"p_config_key": config_key, "p_version": version},
        ).execute())
        if row is None:
            raise KeyError(f"{config_key}@{version}")
        return self._from_row(row)

    def publish(self, config_key: str, version: str, *, is_default: bool = True) -> MappingVersion:
        row = _first(self.client.rpc(
            "publish_app_config",
            {"p_config_key": config_key, "p_version": version, "p_is_default": is_default},
        ).execute())
        if row is None:
            raise KeyError(f"{config_key}@{version}")
        return self._from_row(row)

    def get_published(self, config_key: str) -> MappingVersion | None:
        row = _first(
            self.client.table("app_config")
            .select("*")
            .eq("config_key", config_key)
            .eq("status", MappingStatus.PUBLISHED.value)
            .order("is_default", desc=True)
            .order("published_at", desc=True)
            .limit(1)
            .execute()
        )
        return self._from_row(row) if row else None

    @staticmethod
    def _from_row(row: Mapping[str, Any]) -> MappingVersion:
        return MappingVersion(
            config_key=str(row["config_key"]),
            version=str(row["version"]),
            status=MappingStatus(str(row["status"])),
            content=dict(row.get("content") or {}),
            content_hash=str(row["content_hash"]),
            is_default=bool(row.get("is_default", False)),
            created_at=str(row.get("created_at") or ""),
            validated_at=row.get("validated_at"),
            published_at=row.get("published_at"),
        )
