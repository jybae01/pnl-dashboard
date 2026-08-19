from __future__ import annotations

import math
import uuid
from dataclasses import dataclass, fields, is_dataclass, replace
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping, Protocol, Sequence

from ..reporting.models import (
    CanonicalMonthlySeries,
    CanonicalProductGroup,
    CanonicalSheet,
    DatasetType,
    PnlReportingCanonicalInput,
)
from ..reporting.read_model import (
    ReportingPairIntegrityError,
    ReportingState,
    build_pnl_reporting_read_model,
    build_reporting_state,
    validate_reporting_dataset,
)
from ..reporting.registry import MONTH_KEYS, SHEET_PRODUCT_PNL, TEMPLATE_VERSION
from .auth import AccessCodeSessionService
from .errors import ApiErrorCode, BffError


DTO_VERSION = "1"
CANONICAL_SCHEMA_VERSION = "PNL_REPORTING_CANONICAL_V1"
_PRODUCT_ROW_COUNTS = {
    "SW": 10,
    "BW": 10,
    "LC": 10,
    "FS": 10,
    "NEW_BUSINESS": 8,
}


class PnlReportingReadGatewayError(RuntimeError):
    pass


class PnlReportingReadIntegrityError(ValueError):
    pass


class PnlReportingReadGateway(Protocol):
    def load_active(self, reporting_year: int | None) -> Mapping[str, Any]: ...


@dataclass(frozen=True)
class ActiveReportingDataset:
    dataset_id: str
    dataset_type: DatasetType
    reporting_year: int
    canonical_schema_version: str
    template_version: str
    actual_through_month: int | None
    canonical_payload: PnlReportingCanonicalInput
    uploaded_at: str
    uploaded_at_instant: datetime


@dataclass(frozen=True)
class ActiveReportingSnapshot:
    available_years: tuple[int, ...]
    plan: ActiveReportingDataset | None
    actual: ActiveReportingDataset | None


class SupabasePnlReportingReadGateway(PnlReportingReadGateway):
    """Narrow service-role RPC adapter; it never touches private Storage."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def load_active(self, reporting_year: int | None) -> Mapping[str, Any]:
        try:
            response = self._client.rpc(
                "get_pnl_reporting_viewer_source",
                {"p_reporting_year": reporting_year},
            ).execute()
        except Exception as exc:
            raise PnlReportingReadGatewayError("P&L Reporting read RPC failed") from exc
        value = response.data if hasattr(response, "data") else response
        if isinstance(value, list):
            value = value[0] if len(value) == 1 else None
        if not isinstance(value, Mapping):
            raise PnlReportingReadIntegrityError("P&L Reporting read RPC returned an invalid payload")
        return value


class PnlReportingViewerService:
    def __init__(
        self,
        sessions: AccessCodeSessionService,
        gateway: PnlReportingReadGateway,
    ) -> None:
        self._sessions = sessions
        self._gateway = gateway

    def viewer_read(self, session_id: str, reporting_year: int | None = None) -> dict[str, Any]:
        self._sessions.require_viewer(session_id)
        if reporting_year is not None and (
            not isinstance(reporting_year, int)
            or isinstance(reporting_year, bool)
            or not 2000 <= reporting_year <= 2200
        ):
            raise BffError(
                ApiErrorCode.VALIDATION_ERROR,
                "P&L Reporting request is invalid",
                field_errors={"year": "must be an integer from 2000 through 2200"},
            )
        try:
            source = self._gateway.load_active(reporting_year)
        except PnlReportingReadGatewayError as exc:
            raise BffError(
                ApiErrorCode.TRANSIENT_SYSTEM_ERROR,
                "P&L Reporting is temporarily unavailable",
            ) from exc
        except PnlReportingReadIntegrityError as exc:
            raise BffError(
                ApiErrorCode.INPUT_INTEGRITY_MISMATCH,
                "P&L Reporting data integrity validation failed",
            ) from exc
        try:
            selected_year = _selected_year(source, reporting_year)
            return build_pnl_reporting_viewer_response(source, selected_year)
        except (PnlReportingReadIntegrityError, ReportingPairIntegrityError) as exc:
            raise BffError(
                ApiErrorCode.INPUT_INTEGRITY_MISMATCH,
                "P&L Reporting data integrity validation failed",
            ) from exc
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            raise BffError(
                ApiErrorCode.INPUT_INTEGRITY_MISMATCH,
                "P&L Reporting data integrity validation failed",
            ) from exc


def _selected_year(source: Mapping[str, Any], requested_year: int | None) -> int:
    if not isinstance(source, Mapping):
        raise PnlReportingReadIntegrityError("P&L Reporting source must be an object")
    source_year = _integer(source.get("selected_year"), "selected year")
    if not 2000 <= source_year <= 2200:
        raise PnlReportingReadIntegrityError("selected year is outside the supported range")
    if requested_year is not None:
        if source_year != requested_year:
            raise PnlReportingReadIntegrityError("selected year does not match the request")
        return requested_year
    return source_year


def build_pnl_reporting_viewer_response(
    source: Mapping[str, Any],
    selected_year: int,
) -> dict[str, Any]:
    if not isinstance(source, Mapping):
        raise PnlReportingReadIntegrityError("P&L Reporting source must be an object")
    snapshot = _active_snapshot(source, selected_year)
    plan_payload = snapshot.plan.canonical_payload if snapshot.plan is not None else None
    actual_payload = snapshot.actual.canonical_payload if snapshot.actual is not None else None
    if plan_payload is not None:
        validate_reporting_dataset(plan_payload)
    if actual_payload is not None:
        validate_reporting_dataset(actual_payload)
    reporting = build_reporting_state(plan_payload, actual_payload)

    metadata = _metadata(snapshot, selected_year)
    response: dict[str, Any] = {
        "dtoVersion": DTO_VERSION,
        "state": (
            "DATA_READY" if reporting.state is ReportingState.READY else "REPORTING_GAP"
        ),
        "reportingState": reporting.state.value,
        "metadata": metadata,
        "report": None,
    }
    if reporting.state is not ReportingState.READY:
        return response
    if reporting.pair is None:
        raise PnlReportingReadIntegrityError("READY state omitted its canonical pair")

    report = build_pnl_reporting_read_model(reporting.pair)
    report = replace(report, available_years=snapshot.available_years)
    _validate_report_structure(report)
    response["report"] = _report_dto(report)
    return response


def _active_snapshot(source: Mapping[str, Any], selected_year: int) -> ActiveReportingSnapshot:
    available_years = _available_years(source.get("available_years"))
    raw_datasets = source.get("datasets")
    if not isinstance(raw_datasets, Sequence) or isinstance(raw_datasets, (str, bytes, bytearray)):
        raise PnlReportingReadIntegrityError("active datasets must be an array")

    datasets: dict[DatasetType, ActiveReportingDataset] = {}
    for raw in raw_datasets:
        if not isinstance(raw, Mapping):
            raise PnlReportingReadIntegrityError("active dataset row must be an object")
        dataset = _active_dataset(raw, selected_year)
        if dataset.dataset_type in datasets:
            raise PnlReportingReadIntegrityError("duplicate active dataset type")
        datasets[dataset.dataset_type] = dataset

    if (selected_year in available_years) is not bool(datasets):
        raise PnlReportingReadIntegrityError("selected active year metadata is inconsistent")
    return ActiveReportingSnapshot(
        available_years=available_years,
        plan=datasets.get(DatasetType.PLAN),
        actual=datasets.get(DatasetType.ACTUAL),
    )


def _available_years(value: Any) -> tuple[int, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise PnlReportingReadIntegrityError("available years must be an array")
    years = tuple(_integer(item, "available year") for item in value)
    if any(not 2000 <= year <= 2200 for year in years):
        raise PnlReportingReadIntegrityError("available year is outside the supported range")
    if years != tuple(sorted(set(years), reverse=True)):
        raise PnlReportingReadIntegrityError("available years must be unique and descending")
    return years


def _active_dataset(raw: Mapping[str, Any], selected_year: int) -> ActiveReportingDataset:
    pointer_year = _integer(raw.get("pointer_reporting_year"), "pointer reporting year")
    if pointer_year != selected_year:
        raise PnlReportingReadIntegrityError("active pointer year mismatch")
    pointer_type = _dataset_type(raw.get("pointer_dataset_type"))
    pointer_dataset_id = _uuid(raw.get("pointer_dataset_id"), "pointer dataset id")

    dataset_id = _uuid(raw.get("dataset_id"), "dataset id")
    if dataset_id != pointer_dataset_id:
        raise PnlReportingReadIntegrityError("active pointer target mismatch")
    dataset_type = _dataset_type(raw.get("dataset_type"))
    reporting_year = _integer(raw.get("reporting_year"), "dataset reporting year")
    if dataset_type is not pointer_type or reporting_year != pointer_year:
        raise PnlReportingReadIntegrityError("active pointer identity mismatch")

    schema_version = _text(raw.get("canonical_schema_version"), "canonical schema version")
    if schema_version != CANONICAL_SCHEMA_VERSION:
        raise PnlReportingReadIntegrityError("unsupported canonical schema version")
    template_version = _text(raw.get("template_version"), "template version")
    if template_version != TEMPLATE_VERSION:
        raise PnlReportingReadIntegrityError("unsupported reporting template version")

    through = _nullable_integer(raw.get("actual_through_month"), "actual through month")
    if raw.get("superseded_at") is not None or raw.get("superseded_by_dataset_id") is not None:
        raise PnlReportingReadIntegrityError("active pointer targets a superseded dataset")
    canonical = _canonical_input(raw.get("canonical_payload"))
    if (
        canonical.dataset_type is not dataset_type
        or canonical.reporting_year != reporting_year
        or canonical.template_version != template_version
        or canonical.actual_through_month != through
    ):
        raise PnlReportingReadIntegrityError("canonical payload identity mismatch")
    uploaded_at, uploaded_at_instant = _timestamp(raw.get("uploaded_at"))
    return ActiveReportingDataset(
        dataset_id=dataset_id,
        dataset_type=dataset_type,
        reporting_year=reporting_year,
        canonical_schema_version=schema_version,
        template_version=template_version,
        actual_through_month=through,
        canonical_payload=canonical,
        uploaded_at=uploaded_at,
        uploaded_at_instant=uploaded_at_instant,
    )


def _canonical_input(value: Any) -> PnlReportingCanonicalInput:
    payload = _mapping(value, "canonical payload")
    if set(payload) != {
        "template_version",
        "dataset_type",
        "reporting_year",
        "actual_through_month",
        "sheets",
    }:
        raise PnlReportingReadIntegrityError("canonical payload fields do not match the V1 schema")
    template_version = _text(payload.get("template_version"), "canonical template version")
    dataset_type = _dataset_type(payload.get("dataset_type"))
    reporting_year = _integer(payload.get("reporting_year"), "canonical reporting year")
    through = _nullable_integer(payload.get("actual_through_month"), "canonical actual through month")
    sheets_value = _mapping(payload.get("sheets"), "canonical sheets")

    sheets: list[CanonicalSheet] = []
    for sheet_name, sheet_value in sheets_value.items():
        if not isinstance(sheet_name, str) or not sheet_name:
            raise PnlReportingReadIntegrityError("canonical sheet name is invalid")
        sheet = _mapping(sheet_value, "canonical sheet")
        if sheet_name == SHEET_PRODUCT_PNL:
            groups: list[CanonicalProductGroup] = []
            for group_key, group_value in sheet.items():
                if not isinstance(group_key, str) or not group_key:
                    raise PnlReportingReadIntegrityError("canonical product group key is invalid")
                metrics_value = _mapping(group_value, "canonical product group")
                metrics = tuple(
                    _monthly_series(metric_key, metric_value)
                    for metric_key, metric_value in metrics_value.items()
                )
                groups.append(CanonicalProductGroup(group_key, metrics))
            sheets.append(CanonicalSheet(sheet_name, product_groups=tuple(groups)))
        else:
            rows = tuple(
                _monthly_series(row_key, row_value)
                for row_key, row_value in sheet.items()
            )
            sheets.append(CanonicalSheet(sheet_name, rows=rows))
    return PnlReportingCanonicalInput(
        template_version=template_version,
        dataset_type=dataset_type,
        reporting_year=reporting_year,
        actual_through_month=through,
        sheets=tuple(sheets),
    )


def _monthly_series(key: Any, value: Any) -> CanonicalMonthlySeries:
    if not isinstance(key, str) or not key:
        raise PnlReportingReadIntegrityError("canonical row key is invalid")
    months = _mapping(value, "canonical monthly series")
    if tuple(months.keys()) != MONTH_KEYS:
        raise PnlReportingReadIntegrityError("canonical monthly series must contain ordered Jan-Dec keys")
    return CanonicalMonthlySeries(
        key,
        tuple(_nullable_number(months[month], "canonical monthly value") for month in MONTH_KEYS),
    )


def _metadata(snapshot: ActiveReportingSnapshot, selected_year: int) -> dict[str, Any]:
    present = tuple(item for item in (snapshot.plan, snapshot.actual) if item is not None)
    last_updated = (
        max(present, key=lambda item: item.uploaded_at_instant).uploaded_at if present else None
    )
    return {
        "selectedYear": selected_year,
        "availableYears": list(snapshot.available_years),
        "plan": {
            "exists": snapshot.plan is not None,
            "datasetId": snapshot.plan.dataset_id if snapshot.plan is not None else None,
            "lastUpdated": snapshot.plan.uploaded_at if snapshot.plan is not None else None,
        },
        "actual": {
            "exists": snapshot.actual is not None,
            "datasetId": snapshot.actual.dataset_id if snapshot.actual is not None else None,
            "actualThroughMonth": (
                snapshot.actual.actual_through_month if snapshot.actual is not None else None
            ),
            "lastUpdated": snapshot.actual.uploaded_at if snapshot.actual is not None else None,
        },
        "lastUpdated": last_updated,
    }


def _validate_report_structure(report: Any) -> None:
    if [item.key for item in report.kpis] != [
        "revenue",
        "operating_profit",
        "adjusted_operating_profit",
    ]:
        raise PnlReportingReadIntegrityError("report KPI structure is invalid")
    if len(report.periods) != 12 or len(report.monthly_trends) != 12:
        raise PnlReportingReadIntegrityError("report month structure is invalid")
    if len(report.monthly_data_rows) != 8 or len(report.pnl_rows) != 25:
        raise PnlReportingReadIntegrityError("report P&L structure is invalid")
    if len(report.cogs_rows) != 5 or any(len(row.months) != 12 for row in report.cogs_rows):
        raise PnlReportingReadIntegrityError("report COGS structure is invalid")
    if len(report.sga_rows) != 23:
        raise PnlReportingReadIntegrityError("report SG&A structure is invalid")
    counts = {segment.key: len(segment.rows) for segment in report.product_segments}
    if counts != _PRODUCT_ROW_COUNTS or len(counts) != len(report.product_segments):
        raise PnlReportingReadIntegrityError("report product segment structure is invalid")


def _report_dto(report: Any) -> dict[str, Any]:
    serialized = _json_value(report)
    if not isinstance(serialized, dict):
        raise PnlReportingReadIntegrityError("report serialization failed")
    identity_keys = (
        "reportKey",
        "year",
        "templateVersion",
        "actualThroughMonth",
        "availableYears",
        "periods",
        "selectedPeriodKey",
        "actualPeriodKeys",
        "defaultCustomRangeKey",
    )
    identity = {key: serialized.pop(key) for key in identity_keys}
    return {"identity": identity, **serialized}


def _json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise PnlReportingReadIntegrityError("non-finite report number")
        return value
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return {
            _camel(field.name): _json_value(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise PnlReportingReadIntegrityError("report map key must be text")
            result[key] = _json_value(item)
        return result
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_json_value(item) for item in value]
    raise PnlReportingReadIntegrityError("unsupported report value")


def _camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part[:1].upper() + part[1:] for part in tail)


def _mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise PnlReportingReadIntegrityError(f"{field} must be an object")
    return value


def _dataset_type(value: Any) -> DatasetType:
    if not isinstance(value, str):
        raise PnlReportingReadIntegrityError("dataset type must be text")
    try:
        return DatasetType(value)
    except ValueError as exc:
        raise PnlReportingReadIntegrityError("dataset type is invalid") from exc


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise PnlReportingReadIntegrityError(f"{field} must be non-empty text")
    return value


def _integer(value: Any, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise PnlReportingReadIntegrityError(f"{field} must be an integer")
    return value


def _nullable_integer(value: Any, field: str) -> int | None:
    return None if value is None else _integer(value, field)


def _nullable_number(value: Any, field: str) -> int | float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PnlReportingReadIntegrityError(f"{field} must be numeric or null")
    if isinstance(value, float) and not math.isfinite(value):
        raise PnlReportingReadIntegrityError(f"{field} must be finite")
    return value


def _uuid(value: Any, field: str) -> str:
    try:
        return str(uuid.UUID(str(value)))
    except (TypeError, ValueError, AttributeError) as exc:
        raise PnlReportingReadIntegrityError(f"{field} must be a UUID") from exc


def _timestamp(value: Any) -> tuple[str, datetime]:
    if not isinstance(value, str) or not value:
        raise PnlReportingReadIntegrityError("uploaded timestamp must be text")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PnlReportingReadIntegrityError("uploaded timestamp is invalid") from exc
    if parsed.tzinfo is None:
        raise PnlReportingReadIntegrityError("uploaded timestamp must include a timezone")
    instant = parsed.astimezone(timezone.utc)
    normalized = instant.isoformat().replace("+00:00", "Z")
    return normalized, instant
