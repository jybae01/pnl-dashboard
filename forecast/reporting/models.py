from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
from typing import Any

from .registry import MONTH_KEYS


class DatasetType(str, Enum):
    PLAN = "PLAN"
    ACTUAL = "ACTUAL"


class ValidationSeverity(str, Enum):
    BLOCKING = "BLOCKING"
    WARNING = "WARNING"
    INFO = "INFO"


class ValidationErrorCode(str, Enum):
    INVALID_TEMPLATE = "INVALID_TEMPLATE"
    UNSUPPORTED_TEMPLATE_VERSION = "UNSUPPORTED_TEMPLATE_VERSION"
    MISSING_SHEET = "MISSING_SHEET"
    INVALID_HEADER = "INVALID_HEADER"
    MISSING_KEY = "MISSING_KEY"
    DUPLICATE_KEY = "DUPLICATE_KEY"
    UNKNOWN_KEY = "UNKNOWN_KEY"
    LABEL_MISMATCH = "LABEL_MISMATCH"
    UNIT_MISMATCH = "UNIT_MISMATCH"
    CATEGORY_MISMATCH = "CATEGORY_MISMATCH"
    PRODUCT_GROUP_MISMATCH = "PRODUCT_GROUP_MISMATCH"
    INVALID_VALUE = "INVALID_VALUE"
    PLAN_MONTH_MISSING = "PLAN_MONTH_MISSING"
    ACTUAL_MONTH_MISSING = "ACTUAL_MONTH_MISSING"
    ACTUAL_FUTURE_VALUE_PRESENT = "ACTUAL_FUTURE_VALUE_PRESENT"
    INVALID_ACTUAL_THROUGH = "INVALID_ACTUAL_THROUGH"
    INVALID_DATASET_TYPE = "INVALID_DATASET_TYPE"
    INVALID_REPORTING_YEAR = "INVALID_REPORTING_YEAR"
    UNEXPECTED_SHEET = "UNEXPECTED_SHEET"
    SHEET_ORDER_CHANGED = "SHEET_ORDER_CHANGED"
    ROW_ORDER_CHANGED = "ROW_ORDER_CHANGED"
    HELPER_VALUE_CHANGED = "HELPER_VALUE_CHANGED"
    UNEXPECTED_CONTENT = "UNEXPECTED_CONTENT"


CanonicalNumber = int | float


@dataclass(frozen=True)
class ValidationIssue:
    severity: ValidationSeverity
    error_code: ValidationErrorCode
    safe_message: str
    sheet: str | None = None
    row_key: str | None = None
    product_group_key: str | None = None
    display_label: str | None = None
    month: int | None = None
    field: str | None = None


@dataclass(frozen=True)
class CanonicalMonthlySeries:
    key: str
    values: tuple[CanonicalNumber | None, ...]

    def __post_init__(self) -> None:
        if len(self.values) != len(MONTH_KEYS):
            raise ValueError("canonical monthly series must contain exactly 12 values")

    def to_dict(self) -> dict[str, CanonicalNumber | None]:
        return dict(zip(MONTH_KEYS, self.values, strict=True))


@dataclass(frozen=True)
class CanonicalProductGroup:
    product_group_key: str
    metrics: tuple[CanonicalMonthlySeries, ...]

    def to_dict(self) -> dict[str, dict[str, CanonicalNumber | None]]:
        return {metric.key: metric.to_dict() for metric in self.metrics}


@dataclass(frozen=True)
class CanonicalSheet:
    name: str
    rows: tuple[CanonicalMonthlySeries, ...] = ()
    product_groups: tuple[CanonicalProductGroup, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        if self.product_groups:
            return {
                group.product_group_key: group.to_dict()
                for group in self.product_groups
            }
        return {row.key: row.to_dict() for row in self.rows}


@dataclass(frozen=True)
class PnlReportingCanonicalInput:
    template_version: str
    dataset_type: DatasetType
    reporting_year: int
    actual_through_month: int | None
    sheets: tuple[CanonicalSheet, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "template_version": self.template_version,
            "dataset_type": self.dataset_type.value,
            "reporting_year": self.reporting_year,
            "actual_through_month": self.actual_through_month,
            "sheets": {sheet.name: sheet.to_dict() for sheet in self.sheets},
        }

    def to_json(self) -> str:
        return json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
            sort_keys=True,
        )


@dataclass(frozen=True)
class PnlReportingValidationResult:
    canonical_payload: PnlReportingCanonicalInput | None
    issues: tuple[ValidationIssue, ...]

    @property
    def valid(self) -> bool:
        return self.canonical_payload is not None and not self.errors

    @property
    def errors(self) -> tuple[ValidationIssue, ...]:
        return tuple(
            issue for issue in self.issues
            if issue.severity is ValidationSeverity.BLOCKING
        )

    @property
    def warnings(self) -> tuple[ValidationIssue, ...]:
        return tuple(
            issue for issue in self.issues
            if issue.severity is ValidationSeverity.WARNING
        )

    @property
    def infos(self) -> tuple[ValidationIssue, ...]:
        return tuple(
            issue for issue in self.issues
            if issue.severity is ValidationSeverity.INFO
        )

    @property
    def error_count(self) -> int:
        return len(self.errors)

    @property
    def warning_count(self) -> int:
        return len(self.warnings)
