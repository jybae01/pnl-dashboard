from __future__ import annotations

import json
import shutil
import uuid
from datetime import datetime
from dataclasses import asdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .engine import ForecastResult
from .workbook import extract_period_types, infer_workbook_year, summarize_period_types


@dataclass
class ModelMeta:
    id: str
    name: str
    model_type: str
    year: int
    start_month: int
    end_month: int
    created_date: str
    version: str
    confirmed: bool
    file_name: str
    uploaded_at: str
    regional_sales_monthly: dict[str, float] = field(default_factory=dict)
    tariff_applicable_rate: float = 0.10
    tariff_rate: float = 0.13
    tariff_adjustment_monthly: dict[str, float] = field(default_factory=dict)
    tariff_in_workbook: bool = False
    # Added after the original models.json schema. The default keeps existing
    # registrations readable while allowing new uploads to retain Data!3's
    # month-by-month 실적/추정/계획 metadata.
    period_types: dict[str, str] = field(default_factory=dict)
    # ``confirmed`` is retained as a compatibility alias while persistence
    # migrates to the explicit publication/default flags used by Supabase.
    is_published: bool = False
    is_default: bool = False
    mapping_status: str = "published"
    mapping_version: str = "legacy"
    mapping_hash: str = ""

    def __post_init__(self) -> None:
        # A legacy caller can still construct metadata with confirmed=True.
        # Never turn that published record back into a draft merely because
        # the newer field was absent from its original JSON payload.
        published = bool(self.is_published or self.confirmed)
        self.is_published = published
        self.confirmed = published
        if self.is_default and not published:
            raise ValueError("a default model must be published")

    @property
    def basis_period(self) -> str:
        return f"{self.year}-{self.start_month:02d}~{self.year}-{self.end_month:02d}"

    @property
    def period_composition(self) -> str:
        return summarize_period_types(self.period_types)

    @property
    def period_type_summary(self) -> str:
        """Backward-friendly alias for views that call this a summary."""
        return self.period_composition

    def tariff_for_months(self, months: tuple[int, ...]) -> float:
        if self.tariff_adjustment_monthly:
            return sum(float(self.tariff_adjustment_monthly.get(str(month), 0)) for month in months)
        sales = sum(float(self.regional_sales_monthly.get(str(month), 0)) for month in months)
        return sales * self.tariff_applicable_rate * self.tariff_rate


@dataclass
class BaselineMeta:
    name: str
    file_name: str
    year: int
    actual_through_month: int
    version: str
    uploaded_at: str


class BaselineStore:
    """Stores the administrator-selected workbook used for forecast runs."""

    def __init__(self, directory: str | Path):
        self.directory = Path(directory)
        self.workbook_file = self.directory / "baseline.xlsx"
        self.meta_file = self.directory / "baseline.json"
        self.directory.mkdir(parents=True, exist_ok=True)

    def load(self) -> BaselineMeta | None:
        if not self.workbook_file.exists() or not self.meta_file.exists():
            return None
        return BaselineMeta(**json.loads(self.meta_file.read_text(encoding="utf-8")))

    def activate(
        self,
        content: bytes,
        *,
        name: str,
        file_name: str,
        year: int,
        actual_through_month: int,
        version: str,
    ) -> BaselineMeta:
        meta = BaselineMeta(
            name=name.strip() or Path(file_name).stem,
            file_name=file_name,
            year=int(year),
            actual_through_month=int(actual_through_month),
            version=version.strip() or "V1",
            uploaded_at=datetime.now().astimezone().isoformat(timespec="seconds"),
        )
        temporary = self.directory / "baseline.uploading.xlsx"
        temporary.write_bytes(content)
        temporary.replace(self.workbook_file)
        self.meta_file.write_text(
            json.dumps(asdict(meta), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return meta


class ModelRegistry:
    def __init__(self, directory: str | Path):
        self.directory = Path(directory)
        self.files = self.directory / "models"
        self.index = self.directory / "models.json"
        self.files.mkdir(parents=True, exist_ok=True)

    def list(self) -> list[ModelMeta]:
        if not self.index.exists(): return []
        payload = json.loads(self.index.read_text(encoding="utf-8"))
        models = []
        for item in sorted(payload, key=lambda row: row.get("uploaded_at", ""), reverse=True):
            # models.json files created before period_types was introduced do
            # not contain the field. Keep their original range/year values and
            # supply only the new field's dataclass default.
            normalized = dict(item)
            normalized.setdefault("period_types", {})
            normalized.setdefault("is_published", bool(normalized.get("confirmed", False)))
            normalized.setdefault("confirmed", bool(normalized.get("is_published", False)))
            normalized.setdefault("is_default", False)
            normalized.setdefault("mapping_status", "published" if normalized["is_published"] else "draft")
            normalized.setdefault("mapping_version", "legacy")
            normalized.setdefault("mapping_hash", "")
            models.append(ModelMeta(**normalized))
        return models

    def get(self, model_id: str) -> ModelMeta:
        return next(item for item in self.list() if item.id == model_id)

    def path(self, model_id: str) -> Path:
        return self.files / model_id / "model.xlsx"

    def add(self, content: bytes, *, name: str, model_type: str, year: int | None = None,
            start_month: int = 1, end_month: int = 12, created_date: str | None = None,
            version: str = "V1", confirmed: bool = False, file_name: str = "model.xlsx",
            regional_sales_monthly: dict[str, float] | None = None,
            tariff_applicable_rate: float = 0.10, tariff_rate: float = 0.13,
            tariff_adjustment_monthly: dict[str, float] | None = None,
            tariff_in_workbook: bool = False,
            period_types: dict[str, str] | None = None,
            is_published: bool | None = None, is_default: bool = False,
            mapping_status: str | None = None, mapping_version: str = "legacy",
            mapping_hash: str = "") -> ModelMeta:
        # Golden Models always contain all twelve month columns. Keep these
        # legacy fields for comparison-engine compatibility, but no longer let
        # upload callers define a partial range.
        resolved_start_month, resolved_end_month = 1, 12
        resolved_published = bool(confirmed if is_published is None else is_published)
        if is_default and not resolved_published:
            raise ValueError("a default model must be published")
        model_id = uuid.uuid4().hex
        folder = self.files / model_id
        folder.mkdir(parents=True, exist_ok=False)
        workbook_path = folder / "model.xlsx"
        workbook_path.write_bytes(content)
        detected_period_types = period_types if period_types is not None else extract_period_types(workbook_path)
        resolved_year = int(year) if year is not None else infer_workbook_year(workbook_path)
        resolved_mapping_status = mapping_status or ("published" if resolved_published else "draft")
        meta = ModelMeta(
            id=model_id,
            name=name.strip(),
            model_type=model_type,
            year=resolved_year,
            start_month=resolved_start_month,
            end_month=resolved_end_month,
            created_date=created_date or datetime.now().date().isoformat(),
            version=version.strip() or "V1",
            confirmed=resolved_published,
            file_name=file_name,
            uploaded_at=datetime.now().astimezone().isoformat(timespec="seconds"),
            regional_sales_monthly={
                str(key): float(value) for key, value in (regional_sales_monthly or {}).items()
            },
            tariff_applicable_rate=float(tariff_applicable_rate),
            tariff_rate=float(tariff_rate),
            tariff_adjustment_monthly={
                str(key): float(value) for key, value in (tariff_adjustment_monthly or {}).items()
            },
            tariff_in_workbook=bool(tariff_in_workbook),
            period_types={
                str(key): str(value) for key, value in (detected_period_types or {}).items()
            },
            is_published=resolved_published,
            is_default=bool(is_default),
            mapping_status=resolved_mapping_status,
            mapping_version=str(mapping_version or "legacy"),
            mapping_hash=str(mapping_hash or ""),
        )
        records = [asdict(item) for item in self.list()]
        if meta.is_default:
            for record in records:
                record["is_default"] = False
        records.append(asdict(meta))
        self.index.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
        return meta

    def set_publication(self, model_id: str, *, is_published: bool, is_default: bool = False) -> ModelMeta:
        if is_default and not is_published:
            raise ValueError("a default model must be published")
        records = [asdict(item) for item in self.list()]
        found = False
        for record in records:
            if is_default:
                record["is_default"] = False
            if record["id"] == model_id:
                record["confirmed"] = bool(is_published)
                record["is_published"] = bool(is_published)
                record["is_default"] = bool(is_default)
                found = True
        if not found:
            raise KeyError(model_id)
        self.index.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
        return self.get(model_id)


class ResultStore:
    def __init__(self, directory: str | Path):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.result_file = self.directory / "latest_confirmed.json"
        self.workbook_file = self.directory / "latest_confirmed.xlsx"

    def confirm(
        self,
        result: ForecastResult,
        *,
        engine_version: str = "legacy-local",
        mapping_version: str = "legacy",
        mapping_hash: str = "",
        result_schema_version: str = "1",
        job_id: str | None = None,
        model_id: str | None = None,
    ) -> None:
        payload = asdict(result)
        payload["workbook_path"] = str(self.workbook_file)
        payload.update({
            "engine_version": engine_version,
            "mapping_version": mapping_version,
            "mapping_hash": mapping_hash,
            "result_schema_version": result_schema_version,
            "job_id": job_id,
            "model_id": model_id,
        })
        self.result_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        shutil.copy2(result.workbook_path, self.workbook_file)

    def save_payload(
        self,
        payload: dict[str, Any],
        *,
        engine_version: str,
        mapping_version: str,
        mapping_hash: str,
        result_schema_version: str,
        job_id: str | None = None,
        model_id: str | None = None,
    ) -> None:
        """Persist a JSON result with the same provenance envelope as Supabase.

        This method intentionally does not copy a workbook.  It is used by the
        Phase 1 local job adapter while the durable worker executor remains a
        Phase 2 concern.
        """
        stored = dict(payload)
        stored.update({
            "engine_version": engine_version,
            "mapping_version": mapping_version,
            "mapping_hash": mapping_hash,
            "result_schema_version": result_schema_version,
            "job_id": job_id,
            "model_id": model_id,
        })
        self.result_file.write_text(json.dumps(stored, ensure_ascii=False, indent=2), encoding="utf-8")

    def load(self) -> dict | None:
        if not self.result_file.exists(): return None
        return json.loads(self.result_file.read_text(encoding="utf-8"))
