from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from ..provenance import ResultProvenance
from ..engine import ForecastResult
from ..storage import ModelMeta


class JobStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True)
class CalculationJob:
    id: str
    model_id: str
    status: JobStatus
    storage_bucket: str
    storage_path: str
    engine_version: str
    mapping_version: str
    mapping_hash: str
    result_schema_version: str
    upload_completed_at: str | None = None
    attempt: int = 0
    max_attempts: int = 3
    claimed_by: str | None = None
    claim_token: str | None = None
    heartbeat_at: str | None = None
    lease_expires_at: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    error_detail: dict[str, Any] = field(default_factory=dict)
    analysis_request: dict[str, Any] = field(default_factory=dict)
    queue_name: str = "calculation_jobs"
    queue_message_id: int | None = None
    queue_enqueued_at: str | None = None
    queue_archived_at: str | None = None
    created_by: str | None = None
    created_at: str = ""
    updated_at: str = ""

    @property
    def provenance(self) -> ResultProvenance:
        return ResultProvenance(
            engine_version=self.engine_version,
            mapping_version=self.mapping_version,
            mapping_hash=self.mapping_hash,
            result_schema_version=self.result_schema_version,
        )


@dataclass(frozen=True)
class ClaimedJob:
    job: CalculationJob
    claim_token: str


@dataclass(frozen=True)
class CalculationResultWrite:
    payload: dict[str, Any]
    provenance: ResultProvenance
    workbook_bucket: str | None = None
    workbook_path: str | None = None
    publish: bool = False
    make_default: bool = False


@runtime_checkable
class ModelRepository(Protocol):
    def list(self) -> list[ModelMeta]: ...

    def get(self, model_id: str) -> ModelMeta: ...

    def get_default(
        self,
        *,
        year: int | None = None,
        exclude_model_id: str | None = None,
    ) -> ModelMeta: ...

    def path(self, model_id: str) -> Path: ...

    def add(self, content: bytes, **metadata: Any) -> ModelMeta: ...

    def set_publication(
        self,
        model_id: str,
        *,
        is_published: bool,
        is_default: bool = False,
    ) -> ModelMeta: ...


@runtime_checkable
class ResultRepository(Protocol):
    """Read side shared by local latest-result and Supabase result adapters."""

    def load(self) -> dict[str, Any] | None: ...

    def load_completed(self) -> dict[str, Any] | None: ...


@runtime_checkable
class LegacyResultPublisher(ResultRepository, Protocol):
    """Compatibility write side for the existing synchronous local workflow.

    Supabase writes are intentionally absent: durable results can only be
    created by completing an active calculation job claim.
    """

    def confirm(self, result: ForecastResult, **provenance: Any) -> None: ...


@runtime_checkable
class CalculationJobQueue(Protocol):
    def enqueue(
        self,
        *,
        model_id: str,
        storage_bucket: str,
        storage_path: str,
        provenance: ResultProvenance,
        created_by: str | None = None,
        max_attempts: int = 3,
        analysis_request: dict[str, Any] | None = None,
    ) -> CalculationJob: ...

    def claim_next(self, worker_id: str, *, lease_seconds: int = 300) -> ClaimedJob | None: ...

    def heartbeat(self, claim: ClaimedJob, *, lease_seconds: int = 300) -> bool: ...

    def complete(self, claim: ClaimedJob, result: CalculationResultWrite) -> str: ...

    def fail(
        self,
        claim: ClaimedJob,
        *,
        error_code: str,
        error_message: str,
        error_detail: dict[str, Any] | None = None,
        retryable: bool = False,
    ) -> JobStatus: ...

    def archive(self, claim: ClaimedJob) -> bool: ...

    def delete_message(self, claim: ClaimedJob) -> bool: ...
