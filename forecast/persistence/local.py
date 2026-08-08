from __future__ import annotations

import json
import threading
import uuid
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from ..engine import ForecastResult
from ..provenance import ResultProvenance
from ..storage import ModelMeta, ModelRegistry, ResultStore
from .contracts import (
    CalculationJob,
    CalculationResultWrite,
    ClaimedJob,
    JobStatus,
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    # Lease tests and local workers may use short visibility windows. Keep
    # microseconds so serialization never shortens a lease by almost a second.
    return value.isoformat(timespec="microseconds")


class LocalModelRepositoryAdapter:
    """Repository facade over the existing JSON/XLSX ModelRegistry."""

    def __init__(self, registry: ModelRegistry, default_provenance: ResultProvenance | None = None):
        self.registry = registry
        self.default_provenance = default_provenance

    def list(self) -> list[ModelMeta]:
        return self.registry.list()

    def get(self, model_id: str) -> ModelMeta:
        return self.registry.get(model_id)

    def get_default(
        self,
        *,
        year: int | None = None,
        exclude_model_id: str | None = None,
    ) -> ModelMeta:
        candidates = [
            item for item in self.list()
            if item.id != exclude_model_id and (year is None or item.year == year)
        ]
        selected = next((item for item in candidates if item.is_default and item.is_published), None)
        selected = selected or next((item for item in candidates if item.is_published), None)
        if selected is None:
            raise KeyError("published default model")
        return selected

    def path(self, model_id: str) -> Path:
        return self.registry.path(model_id)

    def add(self, content: bytes, **metadata: Any) -> ModelMeta:
        if self.default_provenance:
            metadata.setdefault("mapping_status", "published")
            metadata.setdefault("mapping_version", self.default_provenance.mapping_version)
            metadata.setdefault("mapping_hash", self.default_provenance.mapping_hash)
        return self.registry.add(content, **metadata)

    def set_publication(
        self,
        model_id: str,
        *,
        is_published: bool,
        is_default: bool = False,
    ) -> ModelMeta:
        return self.registry.set_publication(
            model_id,
            is_published=is_published,
            is_default=is_default,
        )


class LocalResultRepositoryAdapter:
    """Compatibility facade over latest_confirmed.json ResultStore."""

    def __init__(self, store: ResultStore, default_provenance: ResultProvenance | None = None):
        self.store = store
        self.default_provenance = default_provenance

    def confirm(self, result: ForecastResult, **provenance: Any) -> None:
        defaults = self.default_provenance.as_dict() if self.default_provenance else {}
        self.store.confirm(result, **{**defaults, **provenance})

    def load(self) -> dict[str, Any] | None:
        return self.store.load()

    def load_completed(self) -> dict[str, Any] | None:
        directory = self.store.directory / "jobs" / "calculation_results"
        if not directory.exists():
            return None
        payloads: list[dict[str, Any]] = []
        for path in directory.glob("*.json"):
            try:
                row = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError, TypeError):
                continue
            if row.get("is_published"):
                payloads.append(row)
        if not payloads:
            return None
        row = max(
            payloads,
            key=lambda item: (bool(item.get("is_default")), str(item.get("created_at") or "")),
        )
        payload = dict(row.get("result") or {})
        payload.update({key: value for key, value in row.items() if key != "result"})
        return payload


class LocalCalculationJobRepository:
    """File-backed lifecycle adapter; it is not a background worker runner.

    It mirrors the durable queue contract for local development and tests.  A
    long-running claim loop, workbook parsing and calculation remain Phase 2.
    """

    def __init__(self, directory: str | Path):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.jobs_file = self.directory / "calculation_jobs.json"
        self.results_directory = self.directory / "calculation_results"
        self.results_directory.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def _load(self) -> list[CalculationJob]:
        if not self.jobs_file.exists():
            return []
        rows = json.loads(self.jobs_file.read_text(encoding="utf-8"))
        return [CalculationJob(**{**row, "status": JobStatus(row["status"])}) for row in rows]

    def _save(self, jobs: list[CalculationJob]) -> None:
        rows = []
        for job in jobs:
            row = asdict(job)
            row["status"] = job.status.value
            rows.append(row)
        temporary = self.jobs_file.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.jobs_file)

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
    ) -> CalculationJob:
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least one")
        now = _iso(_utc_now())
        with self._lock:
            jobs = self._load()
            job = CalculationJob(
                id=str(uuid.uuid4()),
                model_id=model_id,
                status=JobStatus.PENDING,
                storage_bucket=storage_bucket,
                storage_path=storage_path,
                engine_version=provenance.engine_version,
                mapping_version=provenance.mapping_version,
                mapping_hash=provenance.mapping_hash,
                result_schema_version=provenance.result_schema_version,
                upload_completed_at=now,
                max_attempts=max_attempts,
                analysis_request=dict(analysis_request or {}),
                queue_message_id=max((item.queue_message_id or 0 for item in jobs), default=0) + 1,
                queue_enqueued_at=now,
                created_by=created_by,
                created_at=now,
                updated_at=now,
            )
            self._save([*jobs, job])
        return job

    def get(self, job_id: str) -> CalculationJob:
        with self._lock:
            return next(job for job in self._load() if job.id == job_id)

    def claim_next(self, worker_id: str, *, lease_seconds: int = 300) -> ClaimedJob | None:
        if not worker_id.strip() or lease_seconds < 1:
            raise ValueError("worker_id and a positive lease are required")
        now = _utc_now()
        with self._lock:
            jobs = self._load()
            for index, job in enumerate(jobs):
                stale = (
                    job.status is JobStatus.PROCESSING
                    and job.lease_expires_at is not None
                    and datetime.fromisoformat(job.lease_expires_at) <= now
                )
                claimable = (
                    job.upload_completed_at is not None
                    and (job.status is JobStatus.PENDING or stale)
                )
                if not claimable or job.attempt >= job.max_attempts:
                    continue
                token = str(uuid.uuid4())
                updated = CalculationJob(**{
                    **asdict(job),
                    "status": JobStatus.PROCESSING,
                    "attempt": job.attempt + 1,
                    "claimed_by": worker_id,
                    "claim_token": token,
                    "heartbeat_at": _iso(now),
                    "lease_expires_at": _iso(now + timedelta(seconds=lease_seconds)),
                    "error_code": None,
                    "error_message": None,
                    "error_detail": {},
                    "updated_at": _iso(now),
                })
                jobs[index] = updated
                self._save(jobs)
                return ClaimedJob(job=updated, claim_token=token)
        return None

    def heartbeat(self, claim: ClaimedJob, *, lease_seconds: int = 300) -> bool:
        now = _utc_now()
        with self._lock:
            jobs = self._load()
            for index, job in enumerate(jobs):
                if (
                    job.id == claim.job.id
                    and job.status is JobStatus.PROCESSING
                    and job.claim_token == claim.claim_token
                    and job.lease_expires_at
                    and datetime.fromisoformat(job.lease_expires_at) > now
                ):
                    jobs[index] = CalculationJob(**{
                        **asdict(job),
                        "heartbeat_at": _iso(now),
                        "lease_expires_at": _iso(now + timedelta(seconds=lease_seconds)),
                        "updated_at": _iso(now),
                    })
                    self._save(jobs)
                    return True
        return False

    def complete(self, claim: ClaimedJob, result: CalculationResultWrite) -> str:
        self._assert_matching_provenance(claim, result)
        result_id = str(uuid.uuid4())
        now = _utc_now()
        with self._lock:
            jobs = self._load()
            index, job = self._active_claim(jobs, claim)
            result_payload = {
                "id": result_id,
                "job_id": job.id,
                "model_id": job.model_id,
                "result": result.payload,
                **result.provenance.as_dict(),
                "workbook_bucket": result.workbook_bucket,
                "workbook_path": result.workbook_path,
                "is_published": result.publish,
                "is_default": result.make_default,
                "created_at": _iso(now),
            }
            if result.make_default and not result.publish:
                raise ValueError("a default result must be published")
            result_file = self.results_directory / f"{job.id}.json"
            result_file.write_text(
                json.dumps(result_payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            jobs[index] = CalculationJob(**{
                **asdict(job),
                "status": JobStatus.COMPLETED,
                "heartbeat_at": _iso(now),
                "lease_expires_at": None,
                "queue_archived_at": _iso(now),
                "updated_at": _iso(now),
            })
            self._save(jobs)
        return result_id

    def fail(
        self,
        claim: ClaimedJob,
        *,
        error_code: str,
        error_message: str,
        error_detail: dict[str, Any] | None = None,
        retryable: bool = False,
    ) -> JobStatus:
        now = _utc_now()
        with self._lock:
            jobs = self._load()
            index, job = self._active_claim(jobs, claim)
            next_status = (
                JobStatus.PENDING
                if retryable and job.attempt < job.max_attempts
                else JobStatus.FAILED
            )
            jobs[index] = CalculationJob(**{
                **asdict(job),
                "status": next_status,
                "claimed_by": None,
                "claim_token": None,
                "heartbeat_at": _iso(now),
                "lease_expires_at": None,
                "error_code": error_code,
                "error_message": error_message,
                "error_detail": error_detail or {},
                "queue_archived_at": _iso(now) if next_status is JobStatus.FAILED else None,
                "updated_at": _iso(now),
            })
            self._save(jobs)
            return next_status

    def archive(self, claim: ClaimedJob) -> bool:
        return self._settle_message(claim, delete=False)

    def delete_message(self, claim: ClaimedJob) -> bool:
        return self._settle_message(claim, delete=True)

    def _settle_message(self, claim: ClaimedJob, *, delete: bool) -> bool:
        now = _utc_now()
        with self._lock:
            jobs = self._load()
            for index, job in enumerate(jobs):
                if job.id != claim.job.id or job.claim_token != claim.claim_token:
                    continue
                if job.queue_message_id is None or job.queue_archived_at is not None:
                    return False
                jobs[index] = CalculationJob(**{
                    **asdict(job),
                    "queue_message_id": None if delete else job.queue_message_id,
                    "queue_archived_at": _iso(now),
                    "updated_at": _iso(now),
                })
                self._save(jobs)
                return True
        return False

    @staticmethod
    def _active_claim(jobs: list[CalculationJob], claim: ClaimedJob) -> tuple[int, CalculationJob]:
        for index, job in enumerate(jobs):
            if job.id == claim.job.id:
                if job.status is not JobStatus.PROCESSING or job.claim_token != claim.claim_token:
                    raise RuntimeError("job claim is no longer active")
                return index, job
        raise KeyError(claim.job.id)

    @staticmethod
    def _assert_matching_provenance(claim: ClaimedJob, result: CalculationResultWrite) -> None:
        expected = (
            claim.job.engine_version,
            claim.job.mapping_version,
            claim.job.mapping_hash,
            claim.job.result_schema_version,
        )
        actual = (
            result.provenance.engine_version,
            result.provenance.mapping_version,
            result.provenance.mapping_hash,
            result.provenance.result_schema_version,
        )
        if actual != expected:
            raise ValueError("result provenance does not match the claimed job")
