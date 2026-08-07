from __future__ import annotations

import json
import shutil
import uuid
from datetime import datetime
from dataclasses import asdict
from dataclasses import dataclass, field
from pathlib import Path

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
            period_types: dict[str, str] | None = None) -> ModelMeta:
        # Golden Models always contain all twelve month columns. Keep these
        # legacy fields for comparison-engine compatibility, but no longer let
        # upload callers define a partial range.
        resolved_start_month, resolved_end_month = 1, 12
        model_id = uuid.uuid4().hex
        folder = self.files / model_id
        folder.mkdir(parents=True, exist_ok=False)
        workbook_path = folder / "model.xlsx"
        workbook_path.write_bytes(content)
        detected_period_types = period_types if period_types is not None else extract_period_types(workbook_path)
        resolved_year = int(year) if year is not None else infer_workbook_year(workbook_path)
        meta = ModelMeta(
            id=model_id,
            name=name.strip(),
            model_type=model_type,
            year=resolved_year,
            start_month=resolved_start_month,
            end_month=resolved_end_month,
            created_date=created_date or datetime.now().date().isoformat(),
            version=version.strip() or "V1",
            confirmed=bool(confirmed),
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
        )
        records = [asdict(item) for item in self.list()]
        records.append(asdict(meta))
        self.index.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
        return meta


class ResultStore:
    def __init__(self, directory: str | Path):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.result_file = self.directory / "latest_confirmed.json"
        self.workbook_file = self.directory / "latest_confirmed.xlsx"

    def confirm(self, result: ForecastResult) -> None:
        payload = asdict(result)
        payload["workbook_path"] = str(self.workbook_file)
        self.result_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        shutil.copy2(result.workbook_path, self.workbook_file)

    def load(self) -> dict | None:
        if not self.result_file.exists(): return None
        return json.loads(self.result_file.read_text(encoding="utf-8"))
