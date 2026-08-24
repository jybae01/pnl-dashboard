from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
from types import MappingProxyType
from typing import Callable, Mapping, Sequence, TypeAlias

from .formatting import (
    NULL_TEXT,
    format_monetary,
    format_number,
    format_percentage_point,
    format_rate,
    optional_monetary_text,
    optional_rate_text,
)
from .formulas import (
    NullableNumber,
    accounting_cogs_total,
    admin_other_total,
    admin_total,
    asp,
    difference,
    gross_profit,
    manufacturing_total,
    operating_profit,
    ratio_percent,
    revenue_total,
    sales_other_total,
    sales_total,
    sga_total,
    sum_required_iter,
    variance_rate,
)
from .models import DatasetType, PnlReportingCanonicalInput
from .registry import (
    MANUFACTURING_COGS_ROWS,
    MONTHLY_PNL_ROWS,
    PRODUCT_GROUPS,
    PRODUCT_PNL_ROWS,
    SGA_ROWS,
    SHEET_MANUFACTURING_COGS,
    SHEET_MONTHLY_PNL,
    SHEET_PRODUCT_PNL,
    SHEET_SGA,
    TEMPLATE_VERSION,
    ProductRowDefinition,
    RowDefinition,
)


Series: TypeAlias = tuple[NullableNumber, ...]
Aggregate: TypeAlias = Callable[[str, Series, int, int], NullableNumber]


class ReportingState(str, Enum):
    MISSING_BOTH = "MISSING_BOTH"
    MISSING_PLAN = "MISSING_PLAN"
    MISSING_ACTUAL = "MISSING_ACTUAL"
    READY = "READY"


class PairIntegrityCode(str, Enum):
    PLAN_DATASET_TYPE = "PLAN_DATASET_TYPE"
    ACTUAL_DATASET_TYPE = "ACTUAL_DATASET_TYPE"
    REPORTING_YEAR_MISMATCH = "REPORTING_YEAR_MISMATCH"
    TEMPLATE_VERSION_MISMATCH = "TEMPLATE_VERSION_MISMATCH"
    UNSUPPORTED_TEMPLATE_VERSION = "UNSUPPORTED_TEMPLATE_VERSION"
    INVALID_PLAN_ACTUAL_THROUGH = "INVALID_PLAN_ACTUAL_THROUGH"
    INVALID_ACTUAL_THROUGH = "INVALID_ACTUAL_THROUGH"
    MISSING_REQUIRED_SOURCE = "MISSING_REQUIRED_SOURCE"
    ACTUAL_FUTURE_VALUE_PRESENT = "ACTUAL_FUTURE_VALUE_PRESENT"
    INVALID_CANONICAL_SOURCE = "INVALID_CANONICAL_SOURCE"


class ReportingPairIntegrityError(ValueError):
    def __init__(self, code: PairIntegrityCode, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ReportingDatasetPair:
    plan: PnlReportingCanonicalInput
    actual: PnlReportingCanonicalInput

    def __post_init__(self) -> None:
        _validate_pair(self.plan, self.actual)

    @property
    def reporting_year(self) -> int:
        return self.plan.reporting_year

    @property
    def actual_through_month(self) -> int:
        value = self.actual.actual_through_month
        if value is None:  # guarded by _validate_pair; keeps the type precise
            raise ReportingPairIntegrityError(
                PairIntegrityCode.INVALID_ACTUAL_THROUGH,
                "ACTUAL actual_through_month is required",
            )
        return value


@dataclass(frozen=True)
class ReportingStateResult:
    state: ReportingState
    pair: ReportingDatasetPair | None = None


@dataclass(frozen=True)
class PeriodIdentity:
    period_key: str
    month: int
    label: str
    actual_available: bool


@dataclass(frozen=True)
class DisplayCell:
    value: NullableNumber
    text: str
    tone: str = "neutral"
    emphasis: str = "normal"


@dataclass(frozen=True)
class ComparisonReadModel:
    plan: NullableNumber
    actual: NullableNumber
    delta: NullableNumber
    variance_rate: NullableNumber
    is_rate_row: bool
    cells: tuple[DisplayCell, DisplayCell, DisplayCell, DisplayCell]


@dataclass(frozen=True)
class KpiReadModel:
    key: str
    label: str
    amount: NullableNumber
    amount_text: str | None
    unit_text: str
    annual_plan: NullableNumber
    ytd_plan: NullableNumber
    ytd_actual: NullableNumber
    progress: NullableNumber
    progress_text: str | None
    achievement: NullableNumber
    achievement_text: str | None
    tone: str


@dataclass(frozen=True)
class KpiDefinition:
    key: str
    label: str
    favorable_direction: str


KPI_REGISTRY = (
    KpiDefinition("revenue", "매출액", "higher"),
    KpiDefinition("operating_profit", "영업이익", "higher"),
    KpiDefinition("adjusted_operating_profit", "조정 영업이익", "higher"),
)


@dataclass(frozen=True)
class TrendMonthReadModel:
    period_key: str
    month: int
    label: str
    actual_available: bool
    actual_revenue_available: bool
    plan_revenue: NullableNumber
    actual_revenue: NullableNumber
    plan_revenue_text: str | None
    actual_revenue_text: str | None
    plan_operating_profit: NullableNumber
    actual_operating_profit: NullableNumber
    actual_operating_margin: NullableNumber
    plan_operating_profit_text: str | None
    actual_operating_profit_text: str | None
    actual_operating_margin_text: str | None
    plan_adjusted_operating_profit: NullableNumber
    actual_adjusted_operating_profit: NullableNumber
    actual_adjusted_operating_margin: NullableNumber
    plan_adjusted_operating_profit_text: str | None
    actual_adjusted_operating_profit_text: str | None
    actual_adjusted_operating_margin_text: str | None


@dataclass(frozen=True)
class MonthlyDataRowReadModel:
    key: str
    label: str
    tone: str
    cells: tuple[DisplayCell, ...]


@dataclass(frozen=True)
class TableRowReadModel:
    key: str
    label: str
    unit: str
    level: int
    kind: str
    parent_key: str | None
    collapsible: bool
    comparison_by_period: Mapping[str, ComparisonReadModel]
    compare_by_period: Mapping[str, tuple[DisplayCell, ...]]
    ytd: ComparisonReadModel
    actual_values: tuple[NullableNumber, ...]
    actual_only: tuple[DisplayCell, ...]
    custom_range_comparisons: Mapping[str, ComparisonReadModel]
    custom_by_range: Mapping[str, tuple[DisplayCell, ...]]


@dataclass(frozen=True)
class SgaRowReadModel(TableRowReadModel):
    category: str = ""


@dataclass(frozen=True)
class CogsMonthReadModel:
    period_key: str
    month: int
    label: str
    actual_available: bool
    amount: NullableNumber
    amount_text: str
    revenue_share: NullableNumber
    revenue_share_text: str


@dataclass(frozen=True)
class CogsYtdReadModel:
    through_month: int
    amount: NullableNumber
    amount_text: str
    revenue_share: NullableNumber
    revenue_share_text: str


@dataclass(frozen=True)
class CogsRowReadModel:
    key: str
    label: str
    kind: str
    months: tuple[CogsMonthReadModel, ...]
    ytd: CogsYtdReadModel
    cells: tuple[DisplayCell, ...]


@dataclass(frozen=True)
class ProductSegmentReadModel:
    key: str
    label: str
    business_unit: str | None
    dimension_label: str | None
    rows: tuple[TableRowReadModel, ...]


@dataclass(frozen=True)
class PnlReportingReadModel:
    report_key: str
    year: int
    template_version: str
    actual_through_month: int
    available_years: tuple[int, ...]
    periods: tuple[PeriodIdentity, ...]
    selected_period_key: str
    actual_period_keys: tuple[str, ...]
    default_custom_range_key: str
    kpis: tuple[KpiReadModel, ...]
    monthly_trends: tuple[TrendMonthReadModel, ...]
    monthly_data_rows: tuple[MonthlyDataRowReadModel, ...]
    pnl_rows: tuple[TableRowReadModel, ...]
    cogs_rows: tuple[CogsRowReadModel, ...]
    sga_rows: tuple[SgaRowReadModel, ...]
    product_segments: tuple[ProductSegmentReadModel, ...]


def build_reporting_state(
    plan: PnlReportingCanonicalInput | None,
    actual: PnlReportingCanonicalInput | None,
) -> ReportingStateResult:
    if plan is None and actual is None:
        return ReportingStateResult(ReportingState.MISSING_BOTH)
    if plan is None:
        return ReportingStateResult(ReportingState.MISSING_PLAN)
    if actual is None:
        return ReportingStateResult(ReportingState.MISSING_ACTUAL)
    pair = ReportingDatasetPair(plan, actual)
    return ReportingStateResult(ReportingState.READY, pair)


def build_pnl_reporting_read_model(
    plan: PnlReportingCanonicalInput | ReportingDatasetPair,
    actual: PnlReportingCanonicalInput | None = None,
) -> PnlReportingReadModel:
    pair = plan if isinstance(plan, ReportingDatasetPair) else ReportingDatasetPair(plan, _require_actual(actual))
    year = pair.reporting_year
    through = pair.actual_through_month
    plan_source = _CanonicalAccessor(pair.plan)
    actual_source = _CanonicalAccessor(pair.actual)

    plan_sga = _derive_sga(plan_source)
    actual_sga = _derive_sga(actual_source)
    plan_products = _derive_products(plan_source)
    actual_products = _derive_products(actual_source)
    plan_pnl = _derive_pnl(plan_source, plan_sga, plan_products)
    actual_pnl = _derive_pnl(actual_source, actual_sga, actual_products)
    plan_cogs = _derive_manufacturing_cogs(plan_source)
    actual_cogs = _derive_manufacturing_cogs(actual_source)

    periods = tuple(
        PeriodIdentity(
            period_key=_period_key(year, month),
            month=month,
            label=f"{month}월",
            actual_available=month <= through,
        )
        for month in range(1, 13)
    )
    pnl_rows = _build_table_rows(
        MONTHLY_PNL_ROWS,
        plan_pnl,
        actual_pnl,
        year,
        through,
        _pnl_aggregate,
    )
    sga_table_rows = _build_table_rows(
        SGA_ROWS,
        plan_sga,
        actual_sga,
        year,
        through,
        _plain_aggregate,
    )
    sga_rows = tuple(
        SgaRowReadModel(**row.__dict__, category=definition.category or "")
        for row, definition in zip(sga_table_rows, SGA_ROWS, strict=True)
    )
    product_segments = _build_product_segments(
        plan_products,
        actual_products,
        year,
        through,
    )

    return PnlReportingReadModel(
        report_key=f"pnl-reporting:{year}:{TEMPLATE_VERSION}:{through:02d}",
        year=year,
        template_version=pair.plan.template_version,
        actual_through_month=through,
        available_years=(year,),
        periods=periods,
        selected_period_key=_period_key(year, through),
        actual_period_keys=tuple(_period_key(year, month) for month in range(1, through + 1)),
        default_custom_range_key=_range_key(1, through),
        kpis=_build_kpis(plan_pnl, actual_pnl, through),
        monthly_trends=_build_trends(plan_pnl, actual_pnl, periods),
        monthly_data_rows=_build_monthly_data_rows(plan_pnl, actual_pnl, through),
        pnl_rows=pnl_rows,
        cogs_rows=_build_cogs_rows(actual_cogs, actual_pnl["revenue"], year, through),
        sga_rows=sga_rows,
        product_segments=product_segments,
    )


def _require_actual(actual: PnlReportingCanonicalInput | None) -> PnlReportingCanonicalInput:
    if actual is None:
        raise TypeError("actual canonical input is required")
    return actual


def _validate_pair(plan: PnlReportingCanonicalInput, actual: PnlReportingCanonicalInput) -> None:
    if plan.dataset_type is not DatasetType.PLAN:
        raise ReportingPairIntegrityError(
            PairIntegrityCode.PLAN_DATASET_TYPE,
            "PLAN input must have dataset_type PLAN",
        )
    if actual.dataset_type is not DatasetType.ACTUAL:
        raise ReportingPairIntegrityError(
            PairIntegrityCode.ACTUAL_DATASET_TYPE,
            "ACTUAL input must have dataset_type ACTUAL",
        )
    if plan.actual_through_month is not None:
        raise ReportingPairIntegrityError(
            PairIntegrityCode.INVALID_PLAN_ACTUAL_THROUGH,
            "PLAN actual_through_month must be null",
        )
    if plan.reporting_year != actual.reporting_year:
        raise ReportingPairIntegrityError(
            PairIntegrityCode.REPORTING_YEAR_MISMATCH,
            "PLAN and ACTUAL reporting years must match",
        )
    if plan.template_version != actual.template_version:
        raise ReportingPairIntegrityError(
            PairIntegrityCode.TEMPLATE_VERSION_MISMATCH,
            "PLAN and ACTUAL template versions must match",
        )
    if plan.template_version != TEMPLATE_VERSION:
        raise ReportingPairIntegrityError(
            PairIntegrityCode.UNSUPPORTED_TEMPLATE_VERSION,
            f"unsupported reporting template version: {plan.template_version}",
        )
    _validate_actual_source(actual)
    _validate_required_sources(plan)
    _validate_required_sources(actual)


def validate_reporting_dataset(payload: PnlReportingCanonicalInput) -> None:
    """Validate one persisted canonical source without inventing its missing pair."""

    if payload.template_version != TEMPLATE_VERSION:
        raise ReportingPairIntegrityError(
            PairIntegrityCode.UNSUPPORTED_TEMPLATE_VERSION,
            f"unsupported reporting template version: {payload.template_version}",
        )
    if payload.dataset_type is DatasetType.PLAN:
        if payload.actual_through_month is not None:
            raise ReportingPairIntegrityError(
                PairIntegrityCode.INVALID_PLAN_ACTUAL_THROUGH,
                "PLAN actual_through_month must be null",
            )
    elif payload.dataset_type is DatasetType.ACTUAL:
        _validate_actual_source(payload)
    else:
        raise ReportingPairIntegrityError(
            PairIntegrityCode.PLAN_DATASET_TYPE,
            "reporting input must have dataset_type PLAN or ACTUAL",
        )
    _validate_persisted_canonical_source(payload)


def _validate_actual_source(actual: PnlReportingCanonicalInput) -> None:
    through = actual.actual_through_month
    if not isinstance(through, int) or isinstance(through, bool) or not 1 <= through <= 12:
        raise ReportingPairIntegrityError(
            PairIntegrityCode.INVALID_ACTUAL_THROUGH,
            "ACTUAL actual_through_month must be an integer from 1 through 12",
        )
    for series in _all_series(actual):
        if any(value is not None for value in series.values[through:]):
            raise ReportingPairIntegrityError(
                PairIntegrityCode.ACTUAL_FUTURE_VALUE_PRESENT,
                f"ACTUAL future values must be null: {series.key}",
            )


def _validate_required_sources(payload: PnlReportingCanonicalInput) -> None:
    source = _CanonicalAccessor(payload)
    for sheet, definitions in (
        (SHEET_MONTHLY_PNL, MONTHLY_PNL_ROWS),
        (SHEET_MANUFACTURING_COGS, MANUFACTURING_COGS_ROWS),
        (SHEET_SGA, SGA_ROWS),
    ):
        for definition in definitions:
            if definition.is_input:
                source.row(sheet, definition.key)
    for definition in PRODUCT_PNL_ROWS:
        if definition.is_input:
            source.product(definition.product_group_key, definition.key)


def _validate_persisted_canonical_source(payload: PnlReportingCanonicalInput) -> None:
    expected_sheet_names = {
        SHEET_MONTHLY_PNL,
        SHEET_MANUFACTURING_COGS,
        SHEET_SGA,
        SHEET_PRODUCT_PNL,
    }
    sheet_names = [sheet.name for sheet in payload.sheets]
    if len(sheet_names) != len(expected_sheet_names) or set(sheet_names) != expected_sheet_names:
        _invalid_canonical("canonical sheets do not match the V1 schema")
    sheets = {sheet.name: sheet for sheet in payload.sheets}

    for sheet_name, definitions in (
        (SHEET_MONTHLY_PNL, MONTHLY_PNL_ROWS),
        (SHEET_MANUFACTURING_COGS, MANUFACTURING_COGS_ROWS),
        (SHEET_SGA, SGA_ROWS),
    ):
        sheet = sheets[sheet_name]
        expected_keys = {definition.key for definition in definitions if definition.is_input}
        actual_keys = [row.key for row in sheet.rows]
        if (
            sheet.product_groups
            or len(actual_keys) != len(expected_keys)
            or set(actual_keys) != expected_keys
        ):
            _invalid_canonical(f"canonical rows do not match the V1 schema: {sheet_name}")

    product_sheet = sheets[SHEET_PRODUCT_PNL]
    expected_groups = {group.key for group in PRODUCT_GROUPS}
    actual_groups = [group.product_group_key for group in product_sheet.product_groups]
    if (
        product_sheet.rows
        or len(actual_groups) != len(expected_groups)
        or set(actual_groups) != expected_groups
    ):
        _invalid_canonical("canonical product groups do not match the V1 schema")
    for group in product_sheet.product_groups:
        expected_metrics = {
            definition.key
            for definition in PRODUCT_PNL_ROWS
            if definition.product_group_key == group.product_group_key and definition.is_input
        }
        actual_metrics = [metric.key for metric in group.metrics]
        if len(actual_metrics) != len(expected_metrics) or set(actual_metrics) != expected_metrics:
            _invalid_canonical(
                f"canonical product metrics do not match the V1 schema: {group.product_group_key}"
            )

    through = 12 if payload.dataset_type is DatasetType.PLAN else payload.actual_through_month
    if not isinstance(through, int) or isinstance(through, bool):
        _invalid_canonical("canonical applicable month range is invalid")
    for series in _all_series(payload):
        for value in series.values[:through]:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                _invalid_canonical(f"canonical applicable value is invalid: {series.key}")
            if isinstance(value, float) and not math.isfinite(value):
                _invalid_canonical(f"canonical applicable value is non-finite: {series.key}")


def _invalid_canonical(message: str) -> None:
    raise ReportingPairIntegrityError(PairIntegrityCode.INVALID_CANONICAL_SOURCE, message)


def _all_series(payload: PnlReportingCanonicalInput):
    for sheet in payload.sheets:
        yield from sheet.rows
        for group in sheet.product_groups:
            yield from group.metrics


class _CanonicalAccessor:
    def __init__(self, payload: PnlReportingCanonicalInput) -> None:
        self._rows: dict[str, dict[str, Series]] = {}
        self._products: dict[str, dict[str, Series]] = {}
        for sheet in payload.sheets:
            if sheet.product_groups:
                self._products = {
                    group.product_group_key: {
                        metric.key: metric.values for metric in group.metrics
                    }
                    for group in sheet.product_groups
                }
            else:
                self._rows[sheet.name] = {row.key: row.values for row in sheet.rows}

    def row(self, sheet: str, key: str) -> Series:
        try:
            return self._rows[sheet][key]
        except KeyError as exc:
            raise ReportingPairIntegrityError(
                PairIntegrityCode.MISSING_REQUIRED_SOURCE,
                f"missing canonical source: {sheet}/{key}",
            ) from exc

    def product(self, group: str, key: str) -> Series:
        try:
            return self._products[group][key]
        except KeyError as exc:
            raise ReportingPairIntegrityError(
                PairIntegrityCode.MISSING_REQUIRED_SOURCE,
                f"missing canonical product source: {group}/{key}",
            ) from exc


def _series_formula(function: Callable[..., NullableNumber], *series: Series) -> Series:
    return tuple(function(*(values[index] for values in series)) for index in range(12))


def _derive_sga(source: _CanonicalAccessor) -> dict[str, Series]:
    values = {definition.key: source.row(SHEET_SGA, definition.key) for definition in SGA_ROWS if definition.is_input}
    values["admin_other"] = _series_formula(
        admin_other_total,
        values["admin_other_1"],
        values["admin_other_2"],
        values["admin_other_3"],
        values["admin_other_4"],
    )
    values["admin"] = _series_formula(
        admin_total,
        values["admin_labor"],
        values["admin_depr"],
        values["admin_rnd"],
        values["admin_fee"],
        values["admin_other"],
    )
    values["sales_other"] = _series_formula(
        sales_other_total,
        values["sales_other_1"],
        values["sales_other_2"],
        values["sales_other_3"],
    )
    values["sales"] = _series_formula(
        sales_total,
        values["sales_freight"],
        values["sales_commission"],
        values["sales_brand"],
        values["sales_labor"],
        values["sales_sample"],
        values["sales_bad_debt"],
        values["sales_sundry"],
        values["sales_other"],
    )
    values["sga_total"] = _series_formula(sga_total, values["admin"], values["sales"])
    return values


def _derive_products(source: _CanonicalAccessor) -> dict[str, dict[str, Series]]:
    output: dict[str, dict[str, Series]] = {}
    for group in PRODUCT_GROUPS:
        values = {
            definition.key: source.product(group.key, definition.key)
            for definition in PRODUCT_PNL_ROWS
            if definition.product_group_key == group.key and definition.is_input
        }
        revenue = values["revenue"]
        cogs = values["cogs"]
        sga = values["sga"]
        values["cogs_ratio"] = _series_formula(ratio_percent, cogs, revenue)
        values["gross_profit"] = _series_formula(gross_profit, revenue, cogs)
        values["gross_margin"] = _series_formula(ratio_percent, values["gross_profit"], revenue)
        values["operating_profit"] = _series_formula(operating_profit, values["gross_profit"], sga)
        values["operating_margin"] = _series_formula(ratio_percent, values["operating_profit"], revenue)
        if group.quantity_unit is not None:
            values["asp"] = _series_formula(asp, revenue, values["volume"])
        output[group.key] = values
    return output


def _derive_pnl(
    source: _CanonicalAccessor,
    sga: Mapping[str, Series],
    products: Mapping[str, Mapping[str, Series]],
) -> dict[str, Series]:
    values = {
        definition.key: source.row(SHEET_MONTHLY_PNL, definition.key)
        for definition in MONTHLY_PNL_ROWS
        if definition.is_input
    }
    values["revenue"] = _series_formula(
        revenue_total,
        values["rev_product"],
        values["rev_semi"],
        values["rev_merch"],
        values["rev_other"],
        values["rev_rebate"],
    )
    values["sales_volume"] = (None,) * 12
    for group_key, row_key in (("SW", "volume_sw"), ("BW", "volume_bw"), ("LC", "volume_lc"), ("FS", "volume_fs")):
        values[row_key] = products[group_key]["volume"]
    values["cogs"] = _series_formula(
        accounting_cogs_total,
        values["cogs_product"],
        values["cogs_semi"],
        values["cogs_merch"],
        values["cogs_other"],
        values["cogs_inventory_loss"],
    )
    values["cogs_ratio"] = _series_formula(ratio_percent, values["cogs"], values["revenue"])
    values["gross_profit"] = _series_formula(gross_profit, values["revenue"], values["cogs"])
    values["gross_margin"] = _series_formula(ratio_percent, values["gross_profit"], values["revenue"])
    values["sga"] = sga["sga_total"]
    values["operating_profit"] = _series_formula(operating_profit, values["gross_profit"], values["sga"])
    values["operating_margin"] = _series_formula(ratio_percent, values["operating_profit"], values["revenue"])
    values["adjusted_operating_margin"] = _series_formula(
        ratio_percent,
        values["adjusted_operating_profit"],
        values["revenue"],
    )
    return values


def _derive_manufacturing_cogs(source: _CanonicalAccessor) -> dict[str, Series]:
    values = {
        definition.key: source.row(SHEET_MANUFACTURING_COGS, definition.key)
        for definition in MANUFACTURING_COGS_ROWS
        if definition.is_input
    }
    values["mfg_total"] = _series_formula(
        manufacturing_total,
        values["mfg_material"],
        values["mfg_labor"],
        values["mfg_outsourcing"],
        values["mfg_other"],
    )
    return values


def _aggregate_series(series: Series, start: int, end: int) -> NullableNumber:
    return sum_required_iter(series[start - 1:end])


def _plain_aggregate(_key: str, series: Series, start: int, end: int) -> NullableNumber:
    return _aggregate_series(series, start, end)


def _pnl_aggregate(key: str, series: Series, start: int, end: int, rows: Mapping[str, Series] | None = None) -> NullableNumber:
    if rows is None:
        return _aggregate_series(series, start, end)
    if key == "sales_volume":
        return None
    ratios = {
        "cogs_ratio": ("cogs", "revenue"),
        "gross_margin": ("gross_profit", "revenue"),
        "operating_margin": ("operating_profit", "revenue"),
        "adjusted_operating_margin": ("adjusted_operating_profit", "revenue"),
    }
    if key in ratios:
        numerator, denominator = ratios[key]
        return ratio_percent(
            _aggregate_series(rows[numerator], start, end),
            _aggregate_series(rows[denominator], start, end),
        )
    return _aggregate_series(series, start, end)


def _product_aggregate(key: str, series: Series, start: int, end: int, rows: Mapping[str, Series]) -> NullableNumber:
    if key == "asp":
        return asp(
            _aggregate_series(rows["revenue"], start, end),
            _aggregate_series(rows["volume"], start, end),
        )
    ratios = {
        "cogs_ratio": ("cogs", "revenue"),
        "gross_margin": ("gross_profit", "revenue"),
        "operating_margin": ("operating_profit", "revenue"),
    }
    if key in ratios:
        numerator, denominator = ratios[key]
        return ratio_percent(
            _aggregate_series(rows[numerator], start, end),
            _aggregate_series(rows[denominator], start, end),
        )
    return _aggregate_series(series, start, end)


def _build_table_rows(
    definitions: Sequence[RowDefinition | ProductRowDefinition],
    plan_rows: Mapping[str, Series],
    actual_rows: Mapping[str, Series],
    year: int,
    through: int,
    aggregate: Aggregate,
    *,
    product: bool = False,
    custom_cell_count: int = 4,
    rate_decimals: int = 1,
) -> tuple[TableRowReadModel, ...]:
    child_keys = {definition.parent_key for definition in definitions if isinstance(definition, RowDefinition) and definition.parent_key}
    result: list[TableRowReadModel] = []
    for definition in definitions:
        plan_series = plan_rows[definition.key]
        actual_series = actual_rows[definition.key]
        is_rate = definition.unit == "%"
        is_monetary = definition.unit == "백만원"

        def aggregate_value(rows: Mapping[str, Series], series: Series, start: int, end: int) -> NullableNumber:
            if product:
                return _product_aggregate(definition.key, series, start, end, rows)
            if aggregate is _pnl_aggregate:
                return _pnl_aggregate(definition.key, series, start, end, rows)
            return aggregate(definition.key, series, start, end)

        ytd = _comparison(
            aggregate_value(plan_rows, plan_series, 1, through),
            aggregate_value(actual_rows, actual_series, 1, through),
            is_rate=is_rate,
            is_monetary=is_monetary,
            emphasis="strong" if definition.kind in {"header", "total"} else "normal",
            rate_decimals=rate_decimals,
        )
        comparison_by_period: dict[str, ComparisonReadModel] = {}
        compare_by_period: dict[str, tuple[DisplayCell, ...]] = {}
        for month in range(1, 13):
            comparison = _comparison(
                plan_series[month - 1],
                actual_series[month - 1] if month <= through else None,
                is_rate=is_rate,
                is_monetary=is_monetary,
                emphasis="strong" if definition.kind in {"header", "total"} else "normal",
                rate_decimals=rate_decimals,
            )
            key = _period_key(year, month)
            comparison_by_period[key] = comparison
            # The comparison table exposes a monthly comparison followed by
            # the cumulative comparison through that selected month.  Do not
            # reuse the latest-actual YTD value here: that value is the
            # separate row.ytd/actual-only latest-through semantics and would
            # make every selected period display the same cumulative figures.
            period_ytd = _comparison(
                aggregate_value(plan_rows, plan_series, 1, month),
                aggregate_value(actual_rows, actual_series, 1, month)
                if month <= through
                else None,
                is_rate=is_rate,
                is_monetary=is_monetary,
                emphasis="strong" if definition.kind in {"header", "total"} else "normal",
                rate_decimals=rate_decimals,
            )
            compare_by_period[key] = comparison.cells + period_ytd.cells

        actual_values = tuple(actual_series[:through]) + (
            aggregate_value(actual_rows, actual_series, 1, through),
        )
        actual_only = tuple(
            _value_cell(
                value,
                is_rate=is_rate,
                is_monetary=is_monetary,
                emphasis="strong" if definition.kind in {"header", "total"} else "normal",
                rate_decimals=rate_decimals,
            )
            for value in actual_values
        )
        custom_comparisons: dict[str, ComparisonReadModel] = {}
        custom_cells: dict[str, tuple[DisplayCell, ...]] = {}
        for start in range(1, 13):
            for end in range(start, 13):
                plan_value = aggregate_value(plan_rows, plan_series, start, end)
                actual_value = (
                    aggregate_value(actual_rows, actual_series, start, end)
                    if end <= through
                    else None
                )
                comparison = _comparison(
                    plan_value,
                    actual_value,
                    is_rate=is_rate,
                    is_monetary=is_monetary,
                    emphasis="strong" if definition.kind in {"header", "total"} else "normal",
                    rate_decimals=rate_decimals,
                )
                range_key = _range_key(start, end)
                custom_comparisons[range_key] = comparison
                custom_cells[range_key] = comparison.cells[:custom_cell_count]

        result.append(
            TableRowReadModel(
                key=definition.key,
                label=definition.label,
                unit=definition.unit,
                level=definition.level,
                kind=definition.kind,
                parent_key=definition.parent_key if isinstance(definition, RowDefinition) else None,
                collapsible=definition.key in child_keys,
                comparison_by_period=MappingProxyType(comparison_by_period),
                compare_by_period=MappingProxyType(compare_by_period),
                ytd=ytd,
                actual_values=actual_values,
                actual_only=actual_only,
                custom_range_comparisons=MappingProxyType(custom_comparisons),
                custom_by_range=MappingProxyType(custom_cells),
            )
        )
    return tuple(result)


def _comparison(
    plan: NullableNumber,
    actual: NullableNumber,
    *,
    is_rate: bool,
    is_monetary: bool,
    emphasis: str,
    rate_decimals: int,
) -> ComparisonReadModel:
    delta = difference(actual, plan)
    rate = delta if is_rate else variance_rate(actual, plan)
    if is_rate:
        cells = (
            _value_cell(plan, is_rate=True, emphasis=emphasis, rate_decimals=rate_decimals),
            _value_cell(actual, is_rate=True, emphasis=emphasis, rate_decimals=rate_decimals),
            _value_cell(delta, is_percentage_point=True, signed=True, emphasis=emphasis, rate_decimals=rate_decimals),
            _value_cell(rate, is_percentage_point=True, signed=True, emphasis=emphasis, rate_decimals=rate_decimals),
        )
    else:
        cells = (
            _value_cell(plan, is_monetary=is_monetary, emphasis=emphasis),
            _value_cell(actual, is_monetary=is_monetary, emphasis=emphasis),
            _value_cell(delta, is_monetary=is_monetary, signed=True, emphasis=emphasis),
            _value_cell(rate, is_rate=True, signed=True, emphasis=emphasis, rate_decimals=rate_decimals),
        )
    return ComparisonReadModel(plan, actual, delta, rate, is_rate, cells)


def _value_cell(
    value: NullableNumber,
    *,
    is_rate: bool = False,
    is_monetary: bool = False,
    is_percentage_point: bool = False,
    signed: bool = False,
    emphasis: str = "normal",
    rate_decimals: int = 1,
) -> DisplayCell:
    if is_percentage_point:
        text = format_percentage_point(value, signed=signed, decimals=rate_decimals)
    elif is_rate:
        text = format_rate(value, signed=signed, decimals=rate_decimals)
    elif is_monetary:
        text = format_monetary(value, signed=signed)
    else:
        text = format_number(value, signed=signed)
    return DisplayCell(value=value, text=text, emphasis=emphasis)


def _build_kpis(
    plan: Mapping[str, Series],
    actual: Mapping[str, Series],
    through: int,
) -> tuple[KpiReadModel, ...]:
    output: list[KpiReadModel] = []
    for definition in KPI_REGISTRY:
        key = definition.key
        annual_plan = _pnl_aggregate(key, plan[key], 1, 12, plan)
        ytd_plan = _pnl_aggregate(key, plan[key], 1, through, plan)
        ytd_actual = _pnl_aggregate(key, actual[key], 1, through, actual)
        amount = ytd_actual
        progress = ratio_percent(ytd_actual, annual_plan)
        achievement = ratio_percent(ytd_actual, ytd_plan)
        delta = difference(ytd_actual, ytd_plan)
        tone = _kpi_tone(delta, definition.favorable_direction)
        output.append(
            KpiReadModel(
                key=key,
                label=definition.label,
                amount=amount,
                amount_text=optional_monetary_text(amount),
                unit_text="백만원",
                annual_plan=annual_plan,
                ytd_plan=ytd_plan,
                ytd_actual=ytd_actual,
                progress=progress,
                progress_text=optional_rate_text(progress),
                achievement=achievement,
                achievement_text=optional_rate_text(achievement),
                tone=tone,
            )
        )
    return tuple(output)


def _kpi_tone(delta: NullableNumber, favorable_direction: str) -> str:
    if delta is None or delta == 0:
        return "neutral"
    if favorable_direction != "higher":
        raise ValueError(f"unsupported KPI favorable direction: {favorable_direction}")
    return "favorable" if delta > 0 else "unfavorable"


def _build_trends(
    plan: Mapping[str, Series],
    actual: Mapping[str, Series],
    periods: Sequence[PeriodIdentity],
) -> tuple[TrendMonthReadModel, ...]:
    output: list[TrendMonthReadModel] = []
    for index, period in enumerate(periods):
        available = period.actual_available
        actual_revenue = actual["revenue"][index] if available else None
        actual_op = actual["operating_profit"][index] if available else None
        actual_op_margin = actual["operating_margin"][index] if available else None
        actual_adjusted = actual["adjusted_operating_profit"][index] if available else None
        actual_adjusted_margin = actual["adjusted_operating_margin"][index] if available else None
        output.append(
            TrendMonthReadModel(
                period_key=period.period_key,
                month=period.month,
                label=period.label,
                actual_available=available,
                actual_revenue_available=available,
                plan_revenue=plan["revenue"][index],
                actual_revenue=actual_revenue,
                plan_revenue_text=optional_monetary_text(plan["revenue"][index]),
                actual_revenue_text=optional_monetary_text(actual_revenue),
                plan_operating_profit=plan["operating_profit"][index],
                actual_operating_profit=actual_op,
                actual_operating_margin=actual_op_margin,
                plan_operating_profit_text=optional_monetary_text(plan["operating_profit"][index]),
                actual_operating_profit_text=optional_monetary_text(actual_op),
                actual_operating_margin_text=optional_rate_text(actual_op_margin),
                plan_adjusted_operating_profit=plan["adjusted_operating_profit"][index],
                actual_adjusted_operating_profit=actual_adjusted,
                actual_adjusted_operating_margin=actual_adjusted_margin,
                plan_adjusted_operating_profit_text=optional_monetary_text(plan["adjusted_operating_profit"][index]),
                actual_adjusted_operating_profit_text=optional_monetary_text(actual_adjusted),
                actual_adjusted_operating_margin_text=optional_rate_text(actual_adjusted_margin),
            )
        )
    return tuple(output)


def _build_monthly_data_rows(
    plan: Mapping[str, Series],
    actual: Mapping[str, Series],
    through: int,
) -> tuple[MonthlyDataRowReadModel, ...]:
    definitions = (
        ("revenue_plan", "매출액 계획", "revenue-plan", plan["revenue"], False, False),
        ("revenue_actual", "매출액 실적", "revenue-actual", actual["revenue"], True, False),
        ("operating_plan", "영업이익 계획", "operating-plan", plan["operating_profit"], False, False),
        ("operating_actual", "영업이익 실적", "operating-actual", actual["operating_profit"], True, False),
        ("operating_margin", "영업이익률", "operating-margin", actual["operating_margin"], True, True),
        ("adjusted_plan", "조정 영업이익 계획", "adjusted-plan", plan["adjusted_operating_profit"], False, False),
        ("adjusted_actual", "조정 영업이익 실적", "adjusted-actual", actual["adjusted_operating_profit"], True, False),
        ("adjusted_margin", "조정 영업이익률", "adjusted-margin", actual["adjusted_operating_margin"], True, True),
    )
    rows: list[MonthlyDataRowReadModel] = []
    for key, label, tone, values, actual_only, rate in definitions:
        cells = tuple(
            DisplayCell(
                value=values[index] if not actual_only or index < through else None,
                text=(
                    format_rate(values[index] if not actual_only or index < through else None, decimals=1)
                    if rate
                    else format_monetary(values[index] if not actual_only or index < through else None)
                ),
            )
            for index in range(12)
        )
        rows.append(MonthlyDataRowReadModel(key, label, tone, cells))
    return tuple(rows)


def _build_cogs_rows(
    actual_cogs: Mapping[str, Series],
    actual_revenue: Series,
    year: int,
    through: int,
) -> tuple[CogsRowReadModel, ...]:
    output: list[CogsRowReadModel] = []
    ytd_revenue = _aggregate_series(actual_revenue, 1, through)
    for definition in MANUFACTURING_COGS_ROWS:
        series = actual_cogs[definition.key]
        months: list[CogsMonthReadModel] = []
        cells: list[DisplayCell] = []
        for month in range(1, 13):
            available = month <= through
            amount = series[month - 1] if available else None
            share = ratio_percent(amount, actual_revenue[month - 1]) if available else None
            amount_text = format_monetary(amount)
            share_text = format_rate(share, decimals=1)
            months.append(
                CogsMonthReadModel(
                    period_key=_period_key(year, month),
                    month=month,
                    label=f"{month}월",
                    actual_available=available,
                    amount=amount,
                    amount_text=amount_text,
                    revenue_share=share,
                    revenue_share_text=share_text,
                )
            )
            cells.extend((DisplayCell(amount, amount_text), DisplayCell(share, share_text)))
        ytd_amount = _aggregate_series(series, 1, through)
        ytd_share = ratio_percent(ytd_amount, ytd_revenue)
        ytd = CogsYtdReadModel(
            through_month=through,
            amount=ytd_amount,
            amount_text=format_monetary(ytd_amount),
            revenue_share=ytd_share,
            revenue_share_text=format_rate(ytd_share, decimals=1),
        )
        cells.extend((DisplayCell(ytd_amount, ytd.amount_text), DisplayCell(ytd_share, ytd.revenue_share_text)))
        output.append(
            CogsRowReadModel(
                key=definition.key,
                label=definition.label,
                kind=definition.kind,
                months=tuple(months),
                ytd=ytd,
                cells=tuple(cells),
            )
        )
    return tuple(output)


def _build_product_segments(
    plan_products: Mapping[str, Mapping[str, Series]],
    actual_products: Mapping[str, Mapping[str, Series]],
    year: int,
    through: int,
) -> tuple[ProductSegmentReadModel, ...]:
    output: list[ProductSegmentReadModel] = []
    for group in PRODUCT_GROUPS:
        definitions = tuple(row for row in PRODUCT_PNL_ROWS if row.product_group_key == group.key)
        rows = _build_table_rows(
            definitions,
            plan_products[group.key],
            actual_products[group.key],
            year,
            through,
            _plain_aggregate,
            product=True,
            custom_cell_count=3,
            rate_decimals=1,
        )
        output.append(
            ProductSegmentReadModel(
                key=group.key,
                label=group.display,
                business_unit=group.quantity_unit,
                dimension_label=None if group.quantity_unit is None else group.dimension,
                rows=rows,
            )
        )
    return tuple(output)


def _period_key(year: int, month: int) -> str:
    return f"{year}-{month:02d}"


def _range_key(start: int, end: int) -> str:
    if not 1 <= start <= end <= 12:
        raise ValueError("range must satisfy 1 <= start <= end <= 12")
    return f"{start}월:{end}월"


def custom_range_key(start: int, end: int) -> str:
    """Public deterministic key for one of the 78 materialized ranges."""

    return _range_key(start, end)
