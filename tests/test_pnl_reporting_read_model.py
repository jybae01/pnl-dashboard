from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from forecast.reporting import (
    DatasetType,
    KPI_REGISTRY,
    PairIntegrityCode,
    ReportingPairIntegrityError,
    ReportingState,
    build_pnl_reporting_read_model,
    build_reporting_state,
    custom_range_key,
)
from forecast.reporting.formulas import (
    accounting_cogs_total,
    admin_other_total,
    admin_total,
    asp,
    gross_profit,
    manufacturing_total,
    operating_profit,
    ratio_percent,
    revenue_total,
    sales_other_total,
    sales_total,
    sga_total,
    sum_required,
    variance_rate,
)
from forecast.reporting.formatting import (
    format_monetary,
    format_number,
    format_percentage_point,
    format_rate,
)
from forecast.reporting.models import (
    CanonicalMonthlySeries,
    CanonicalProductGroup,
    CanonicalSheet,
    PnlReportingCanonicalInput,
)
from forecast.reporting.registry import (
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
)


PLAN_PNL = {
    "rev_product": 100,
    "rev_semi": 20,
    "rev_merch": 10,
    "rev_other": 5,
    "rev_rebate": -5,
    "cogs_product": 50,
    "cogs_semi": 10,
    "cogs_merch": 5,
    "cogs_other": 2,
    "cogs_inventory_loss": 3,
    "adjusted_operating_profit": 40,
}
ACTUAL_PNL = {
    **PLAN_PNL,
    "rev_product": 110,
    "adjusted_operating_profit": 45,
}
PLAN_COGS = {"mfg_material": 10, "mfg_labor": 5, "mfg_outsourcing": 3, "mfg_other": 2}
ACTUAL_COGS = {"mfg_material": 12, "mfg_labor": 5, "mfg_outsourcing": 3, "mfg_other": 2}
SGA_VALUES = {
    "admin_labor": 10,
    "admin_depr": 2,
    "admin_rnd": 3,
    "admin_fee": 1,
    "admin_other_1": 1,
    "admin_other_2": 1,
    "admin_other_3": 1,
    "admin_other_4": 1,
    "sales_freight": 2,
    "sales_commission": 1,
    "sales_brand": 1,
    "sales_labor": 2,
    "sales_sample": 1,
    "sales_bad_debt": 1,
    "sales_sundry": 1,
    "sales_other_1": 1,
    "sales_other_2": 1,
    "sales_other_3": 1,
}


def _product_value(group: str, key: str, dataset_type: DatasetType) -> int:
    if group == "NEW_BUSINESS":
        values = {"revenue": 8, "cogs": 5, "sga": 1}
    else:
        values = {"revenue": 10, "volume": 100, "cogs": 6, "sga": 1}
    value = values[key]
    if dataset_type is DatasetType.ACTUAL and key == "revenue":
        value += 1
    return value


def _payload(
    dataset_type: DatasetType,
    *,
    through: int | None = None,
    year: int = 2026,
    version: str = TEMPLATE_VERSION,
    overrides: dict[tuple[str, ...], int | float | None] | None = None,
) -> PnlReportingCanonicalInput:
    overrides = overrides or {}

    def series(sheet: str, key: str, base: int | float, group: str | None = None) -> CanonicalMonthlySeries:
        values = []
        for month in range(1, 13):
            available = dataset_type is DatasetType.PLAN or (through is not None and month <= through)
            override_key = (sheet, group, key, str(month)) if group else (sheet, key, str(month))
            values.append(overrides.get(override_key, base) if available else None)
        return CanonicalMonthlySeries(key, tuple(values))

    pnl_source = PLAN_PNL if dataset_type is DatasetType.PLAN else ACTUAL_PNL
    cogs_source = PLAN_COGS if dataset_type is DatasetType.PLAN else ACTUAL_COGS
    product_groups = []
    for group in PRODUCT_GROUPS:
        product_groups.append(
            CanonicalProductGroup(
                group.key,
                tuple(
                    series(
                        SHEET_PRODUCT_PNL,
                        definition.key,
                        _product_value(group.key, definition.key, dataset_type),
                        group.key,
                    )
                    for definition in PRODUCT_PNL_ROWS
                    if definition.product_group_key == group.key and definition.is_input
                ),
            )
        )
    return PnlReportingCanonicalInput(
        template_version=version,
        dataset_type=dataset_type,
        reporting_year=year,
        actual_through_month=through,
        sheets=(
            CanonicalSheet(
                SHEET_MONTHLY_PNL,
                rows=tuple(
                    series(SHEET_MONTHLY_PNL, definition.key, pnl_source[definition.key])
                    for definition in MONTHLY_PNL_ROWS
                    if definition.is_input
                ),
            ),
            CanonicalSheet(
                SHEET_MANUFACTURING_COGS,
                rows=tuple(
                    series(SHEET_MANUFACTURING_COGS, definition.key, cogs_source[definition.key])
                    for definition in MANUFACTURING_COGS_ROWS
                    if definition.is_input
                ),
            ),
            CanonicalSheet(
                SHEET_SGA,
                rows=tuple(
                    series(SHEET_SGA, definition.key, SGA_VALUES[definition.key])
                    for definition in SGA_ROWS
                    if definition.is_input
                ),
            ),
            CanonicalSheet(SHEET_PRODUCT_PNL, product_groups=tuple(product_groups)),
        ),
    )


def _report(through: int = 6, *, plan_overrides=None, actual_overrides=None):
    return build_pnl_reporting_read_model(
        _payload(DatasetType.PLAN, overrides=plan_overrides),
        _payload(DatasetType.ACTUAL, through=through, overrides=actual_overrides),
    )


def _row(rows, key: str):
    return next(row for row in rows if row.key == key)


def _segment(report, key: str):
    return next(segment for segment in report.product_segments if segment.key == key)


def test_formula_register_and_hard_null_zero_contract():
    assert revenue_total(1, 2, 3, 4, -1) == 9
    assert accounting_cogs_total(1, 2, 3, 4, 5) == 15
    assert manufacturing_total(1, 2, 3, 4) == 10
    assert admin_other_total(1, 2, 3, 4) == 10
    assert admin_total(1, 2, 3, 4, 5) == 15
    assert sales_other_total(1, 2, 3) == 6
    assert sales_total(1, 2, 3, 4, 5, 6, 7, 8) == 36
    assert sga_total(10, 20) == 30
    assert gross_profit(100, 70) == 30
    assert operating_profit(30, 12) == 18
    assert sum_required(0, 0) == 0
    assert sum_required(1, None) is None
    assert ratio_percent(0, 10) == 0
    assert ratio_percent(1, 0) is None
    assert ratio_percent(None, 10) is None
    assert variance_rate(0, 10) == -100
    assert variance_rate(10, 0) is None
    assert asp(100_000_000, 400) == 250_000
    assert asp(1, 0) is None
    assert asp(None, 10) is None


def test_display_formatting_matches_frozen_rules():
    assert format_monetary(1_000_000) == "1"
    assert format_monetary(100_000_000) == "100"
    assert format_monetary(0) == "0"
    assert format_number(None) == "—"
    assert format_number(0) == "0"
    assert format_number(-0.0) == "0"
    assert format_number(12_000) == "12,000"
    assert format_number(500, signed=True) == "+500"
    assert format_rate(80.666) == "80.67%"
    assert format_percentage_point(-1.874) == "-1.87%p"


def test_reporting_state_gap_matrix_and_ready_pair():
    plan = _payload(DatasetType.PLAN)
    actual = _payload(DatasetType.ACTUAL, through=6)
    assert build_reporting_state(None, None).state is ReportingState.MISSING_BOTH
    assert build_reporting_state(None, actual).state is ReportingState.MISSING_PLAN
    assert build_reporting_state(plan, None).state is ReportingState.MISSING_ACTUAL
    ready = build_reporting_state(plan, actual)
    assert ready.state is ReportingState.READY
    assert ready.pair is not None and ready.pair.actual_through_month == 6


@pytest.mark.parametrize(
    ("plan", "actual", "code"),
    [
        (_payload(DatasetType.ACTUAL, through=6), _payload(DatasetType.ACTUAL, through=6), PairIntegrityCode.PLAN_DATASET_TYPE),
        (_payload(DatasetType.PLAN), _payload(DatasetType.PLAN), PairIntegrityCode.ACTUAL_DATASET_TYPE),
        (replace(_payload(DatasetType.PLAN), actual_through_month=1), _payload(DatasetType.ACTUAL, through=6), PairIntegrityCode.INVALID_PLAN_ACTUAL_THROUGH),
        (_payload(DatasetType.PLAN), _payload(DatasetType.ACTUAL, through=6, year=2025), PairIntegrityCode.REPORTING_YEAR_MISMATCH),
        (_payload(DatasetType.PLAN), _payload(DatasetType.ACTUAL, through=6, version="OTHER"), PairIntegrityCode.TEMPLATE_VERSION_MISMATCH),
        (_payload(DatasetType.PLAN, version="OTHER"), _payload(DatasetType.ACTUAL, through=6, version="OTHER"), PairIntegrityCode.UNSUPPORTED_TEMPLATE_VERSION),
        (_payload(DatasetType.PLAN), _payload(DatasetType.ACTUAL, through=None), PairIntegrityCode.INVALID_ACTUAL_THROUGH),
    ],
)
def test_ready_pair_integrity_errors_are_not_reporting_gaps(plan, actual, code):
    with pytest.raises(ReportingPairIntegrityError) as caught:
        build_reporting_state(plan, actual)
    assert caught.value.code is code


def test_pair_rejects_future_actual_values():
    actual = _payload(DatasetType.ACTUAL, through=6)
    first_sheet = actual.sheets[0]
    first_row = first_sheet.rows[0]
    changed_row = replace(first_row, values=first_row.values[:6] + (99,) + first_row.values[7:])
    changed_sheet = replace(first_sheet, rows=(changed_row, *first_sheet.rows[1:]))
    changed = replace(actual, sheets=(changed_sheet, *actual.sheets[1:]))
    with pytest.raises(ReportingPairIntegrityError) as caught:
        build_pnl_reporting_read_model(_payload(DatasetType.PLAN), changed)
    assert caught.value.code is PairIntegrityCode.ACTUAL_FUTURE_VALUE_PRESENT


@pytest.mark.parametrize("through", [1, 6, 12])
def test_actual_through_matrix_is_dynamic_across_every_read_model(through):
    report = _report(through)
    assert len(report.periods) == 12
    assert [period.actual_available for period in report.periods] == [month <= through for month in range(1, 13)]
    assert len(report.actual_period_keys) == through
    assert len(report.monthly_trends) == 12
    assert sum(month.actual_available for month in report.monthly_trends) == through
    assert sum(month.actual_operating_margin is not None for month in report.monthly_trends) == through
    assert sum(month.actual_adjusted_operating_margin is not None for month in report.monthly_trends) == through
    assert len(report.pnl_rows) == 25
    assert len(report.sga_rows) == 23
    assert all(len(row.actual_only) == through + 1 for row in report.pnl_rows)
    assert all(len(row.actual_only) == through + 1 for row in report.sga_rows)
    assert all(len(row.actual_only) == through + 1 for segment in report.product_segments for row in segment.rows)
    assert _row(report.pnl_rows, "revenue").ytd.actual == 140 * through
    assert _row(report.sga_rows, "sga_total").ytd.actual == 32 * through
    assert _row(_segment(report, "SW").rows, "revenue").ytd.actual == 11 * through
    assert len(report.cogs_rows) == 5
    assert all(len(row.months) == 12 for row in report.cogs_rows)
    assert all(sum(month.actual_available for month in row.months) == through for row in report.cogs_rows)
    assert _row(report.cogs_rows, "mfg_material").ytd.amount == 12 * through


def test_kpis_have_exact_order_latest_amount_ytd_definitions_and_tones():
    report = _report(6)
    assert [(item.key, item.favorable_direction) for item in KPI_REGISTRY] == [
        ("revenue", "higher"),
        ("operating_profit", "higher"),
        ("adjusted_operating_profit", "higher"),
    ]
    assert [kpi.key for kpi in report.kpis] == ["revenue", "operating_profit", "adjusted_operating_profit"]
    revenue, op, adjusted = report.kpis
    assert (revenue.amount, revenue.amount_text) == (140, "0")
    assert (revenue.annual_plan, revenue.ytd_plan, revenue.ytd_actual) == (1560, 780, 840)
    assert revenue.progress == pytest.approx(840 / 1560 * 100)
    assert revenue.achievement == pytest.approx(840 / 780 * 100)
    assert revenue.progress_text == "53.8%"
    assert revenue.achievement_text == "107.7%"
    assert revenue.tone == "favorable"
    assert (op.amount, op.ytd_plan, op.ytd_actual, op.tone) == (38, 168, 228, "favorable")
    assert (adjusted.amount, adjusted.ytd_plan, adjusted.ytd_actual, adjusted.tone) == (45, 240, 270, "favorable")


def test_kpi_zero_denominators_are_null_and_zero_delta_is_neutral():
    zero_plan_revenue = {
        (SHEET_MONTHLY_PNL, key, str(month)): 0
        for key in ("rev_product", "rev_semi", "rev_merch", "rev_other", "rev_rebate")
        for month in range(1, 13)
    }
    report = _report(6, plan_overrides=zero_plan_revenue)
    revenue = report.kpis[0]
    assert revenue.annual_plan == 0
    assert revenue.ytd_plan == 0
    assert revenue.progress is None and revenue.progress_text is None
    assert revenue.achievement is None and revenue.achievement_text is None

    neutral = _report(6, actual_overrides={
        (SHEET_MONTHLY_PNL, "rev_product", str(month)): 100 for month in range(1, 7)
    }).kpis[0]
    assert neutral.ytd_actual == neutral.ytd_plan
    assert neutral.tone == "neutral"
    unfavorable = _report(6, actual_overrides={
        (SHEET_MONTHLY_PNL, "rev_product", str(month)): 90 for month in range(1, 7)
    }).kpis[0]
    assert unfavorable.tone == "unfavorable"


def test_latest_registered_actual_zero_is_a_valid_kpi_amount():
    actual_zero = {
        (SHEET_MONTHLY_PNL, key, "1"): 0
        for key in ("rev_product", "rev_semi", "rev_merch", "rev_other", "rev_rebate")
    }
    revenue = _report(1, actual_overrides=actual_zero).kpis[0]
    assert revenue.amount == 0
    assert revenue.amount_text == "0"
    assert revenue.progress == 0
    assert revenue.progress_text == "0.0%"


def test_trend_is_twelve_months_percentage_points_and_zero_is_available():
    zero_month = {}
    for key in PLAN_PNL:
        zero_month[(SHEET_MONTHLY_PNL, key, "5")] = 0
    for key in SGA_VALUES:
        zero_month[(SHEET_SGA, key, "5")] = 0
    report = _report(6, actual_overrides=zero_month)
    may = report.monthly_trends[4]
    july = report.monthly_trends[6]
    assert may.actual_available is True and may.actual_revenue_available is True
    assert may.actual_revenue == 0 and may.actual_revenue_text == "0"
    assert may.actual_operating_margin is None
    assert may.actual_operating_margin_text is None
    assert july.actual_available is False
    assert july.actual_revenue is None and july.actual_revenue_text is None
    assert july.actual_adjusted_operating_margin is None
    assert report.monthly_trends[0].actual_operating_margin == pytest.approx(38 / 140 * 100)
    assert report.monthly_trends[0].actual_operating_margin > 1
    assert sum(month.actual_operating_margin is not None for month in report.monthly_trends) == 5


def test_monthly_data_table_has_exact_eight_rows_and_future_dash_metadata():
    report = _report(6)
    assert [row.label for row in report.monthly_data_rows] == [
        "매출액 계획",
        "매출액 실적",
        "영업이익 계획",
        "영업이익 실적",
        "영업이익률",
        "조정 영업이익 계획",
        "조정 영업이익 실적",
        "조정 영업이익률",
    ]
    assert all(len(row.cells) == 12 for row in report.monthly_data_rows)
    assert report.monthly_data_rows[0].cells[11].value == 130
    assert report.monthly_data_rows[1].cells[5].text == "0"
    assert report.monthly_data_rows[1].cells[6].value is None
    assert report.monthly_data_rows[1].cells[6].text == "—"
    assert report.monthly_data_rows[4].cells[0].text == "27.1%"


def test_pnl_registry_order_comparisons_ytd_rate_rows_and_ranges():
    report = _report(6)
    assert [row.key for row in report.pnl_rows] == [definition.key for definition in MONTHLY_PNL_ROWS]
    revenue = _row(report.pnl_rows, "revenue")
    assert revenue.collapsible is True
    assert _row(report.pnl_rows, "sales_volume").collapsible is True
    assert _row(report.pnl_rows, "cogs").collapsible is True
    june = revenue.comparison_by_period["2026-06"]
    assert (june.plan, june.actual, june.delta) == (130, 140, 10)
    assert june.variance_rate == pytest.approx(10 / 130 * 100)
    assert len(revenue.compare_by_period["2026-06"]) == 8
    assert (revenue.ytd.plan, revenue.ytd.actual, revenue.ytd.delta) == (780, 840, 60)
    assert len(revenue.custom_range_comparisons) == 78
    assert revenue.custom_range_comparisons[custom_range_key(1, 6)].actual == 840
    future_range = revenue.custom_range_comparisons[custom_range_key(1, 7)]
    assert future_range.actual is None and future_range.delta is None and future_range.variance_rate is None

    cogs_ratio = _row(report.pnl_rows, "cogs_ratio")
    ratio = cogs_ratio.comparison_by_period["2026-06"]
    assert ratio.plan == pytest.approx(70 / 130 * 100)
    assert ratio.actual == pytest.approx(70 / 140 * 100)
    assert ratio.variance_rate == pytest.approx(ratio.actual - ratio.plan)
    assert ratio.cells[2].text.endswith("%p") and ratio.cells[3].text.endswith("%p")
    with pytest.raises(ValueError):
        custom_range_key(7, 6)


def test_amount_row_plan_zero_has_null_variance_rate():
    plan_zero = {
        (SHEET_MONTHLY_PNL, "cogs_inventory_loss", str(month)): 0 for month in range(1, 13)
    }
    report = _report(6, plan_overrides=plan_zero)
    row = _row(report.pnl_rows, "cogs_inventory_loss")
    comparison = row.comparison_by_period["2026-01"]
    assert comparison.plan == 0 and comparison.actual == 3 and comparison.delta == 3
    assert comparison.variance_rate is None
    assert comparison.cells[3].text == "—"


def test_ytd_is_strict_when_any_source_month_is_null():
    report = _report(6, actual_overrides={(SHEET_MONTHLY_PNL, "rev_product", "3"): None})
    revenue = _row(report.pnl_rows, "revenue")
    assert revenue.ytd.actual is None
    assert revenue.ytd.delta is None
    assert revenue.actual_only[-1].value is None
    assert report.kpis[0].ytd_actual is None


def test_sales_volume_parent_has_no_mixed_quantity_total():
    report = _report(6)
    parent = _row(report.pnl_rows, "sales_volume")
    assert all(value is None for value in parent.actual_values)
    assert all(cell.text == "—" for cell in parent.actual_only)
    assert parent.ytd.plan is None and parent.ytd.actual is None
    assert _row(report.pnl_rows, "volume_sw").ytd.actual == 600
    assert _row(report.pnl_rows, "volume_fs").ytd.actual == 600


def test_cogs_has_five_rows_twelve_months_shares_and_ytd():
    report = _report(6)
    assert [row.key for row in report.cogs_rows] == [definition.key for definition in MANUFACTURING_COGS_ROWS]
    material = _row(report.cogs_rows, "mfg_material")
    assert len(material.months) == 12
    assert material.months[0].amount == 12
    assert material.months[0].revenue_share == pytest.approx(12 / 140 * 100)
    assert material.months[0].revenue_share_text == "8.6%"
    assert material.months[6].actual_available is False
    assert material.months[6].amount is None and material.months[6].amount_text == "—"
    assert material.ytd.amount == 72
    assert material.ytd.revenue_share == pytest.approx(72 / 840 * 100)
    assert len(material.cells) == 26


def test_cogs_zero_revenue_denominator_is_null_not_zero_percent():
    zero = {}
    for key in PLAN_PNL:
        zero[(SHEET_MONTHLY_PNL, key, "1")] = 0
    report = _report(6, actual_overrides=zero)
    material = _row(report.cogs_rows, "mfg_material")
    assert material.months[0].amount == 12
    assert material.months[0].revenue_share is None
    assert material.months[0].revenue_share_text == "—"


def test_sga_has_exact_registry_hierarchy_and_all_compare_modes():
    report = _report(6)
    assert [row.key for row in report.sga_rows] == [definition.key for definition in SGA_ROWS]
    by_key = {row.key: row for row in report.sga_rows}
    assert by_key["admin"].collapsible is True
    assert by_key["admin_other"].parent_key == "admin"
    assert by_key["admin_other"].collapsible is True
    assert by_key["admin_other_1"].parent_key == "admin_other"
    assert by_key["admin_other_1"].level == 2
    assert by_key["sales"].collapsible is True
    assert by_key["sales_other"].collapsible is True
    assert by_key["sga_total"].kind == "total"
    assert by_key["admin"].comparison_by_period["2026-01"].actual == 20
    assert by_key["sales"].ytd.actual == 72
    assert by_key["sga_total"].ytd.actual == 192
    assert len(by_key["sga_total"].actual_only) == 7
    assert len(by_key["sga_total"].custom_range_comparisons) == 78
    assert by_key["sga_total"].custom_range_comparisons[custom_range_key(1, 6)].actual == 192
    assert by_key["sga_total"].custom_range_comparisons[custom_range_key(1, 7)].actual is None


def test_product_groups_have_exact_rows_units_and_no_fake_new_business_quantity():
    report = _report(6)
    assert [segment.key for segment in report.product_segments] == ["SW", "BW", "LC", "FS", "NEW_BUSINESS"]
    assert {segment.key: len(segment.rows) for segment in report.product_segments} == {
        "SW": 10,
        "BW": 10,
        "LC": 10,
        "FS": 10,
        "NEW_BUSINESS": 8,
    }
    lc = _segment(report, "LC")
    fs = _segment(report, "FS")
    new = _segment(report, "NEW_BUSINESS")
    assert (lc.label, lc.dimension_label, lc.business_unit) == ("4인치 LC", "4-inch", "PCS")
    assert (fs.dimension_label, fs.business_unit) == ("LENGTH", "m")
    assert new.business_unit is None and new.dimension_label is None
    assert {row.key for row in new.rows} == {
        "revenue", "cogs", "cogs_ratio", "gross_profit", "gross_margin", "sga", "operating_profit", "operating_margin"
    }
    assert "volume" not in {row.key for row in new.rows}
    assert "asp" not in {row.key for row in new.rows}
    assert len(lc.rows[0].custom_by_range[custom_range_key(1, 6)]) == 3
    assert lc.rows[0].custom_range_comparisons[custom_range_key(1, 6)].variance_rate is not None
    assert lc.rows[0].custom_range_comparisons[custom_range_key(1, 7)].actual is None


def test_product_asp_and_zero_volume_contract():
    report = _report(6)
    sw_asp = _row(_segment(report, "SW").rows, "asp")
    assert sw_asp.comparison_by_period["2026-01"].plan == pytest.approx(0.1)
    assert sw_asp.comparison_by_period["2026-01"].actual == pytest.approx(0.11)
    assert sw_asp.ytd.actual == pytest.approx(0.11)
    sw_ratio = _row(_segment(report, "SW").rows, "cogs_ratio")
    assert sw_ratio.comparison_by_period["2026-01"].cells[1].text == "54.5%"

    zero_volume = {(SHEET_PRODUCT_PNL, "SW", "volume", "1"): 0}
    report = _report(6, actual_overrides=zero_volume)
    sw_asp = _row(_segment(report, "SW").rows, "asp")
    assert sw_asp.comparison_by_period["2026-01"].actual is None
    assert sw_asp.comparison_by_period["2026-01"].cells[1].text == "—"


def test_raw_won_presentation_scales_only_monetary_values():
    actual_overrides = {
        (SHEET_MONTHLY_PNL, key, "1"): 0
        for key in PLAN_PNL
    }
    actual_overrides.update({
        (SHEET_MONTHLY_PNL, "rev_product", "1"): 100_000_000,
        **{(SHEET_MANUFACTURING_COGS, key, "1"): 0 for key in ACTUAL_COGS},
        (SHEET_MANUFACTURING_COGS, "mfg_material", "1"): 1_000_000,
        **{(SHEET_SGA, key, "1"): 0 for key in SGA_VALUES},
        (SHEET_SGA, "admin_labor", "1"): 1_000_000,
        (SHEET_PRODUCT_PNL, "SW", "revenue", "1"): 100_000_000,
        (SHEET_PRODUCT_PNL, "SW", "volume", "1"): 400,
        (SHEET_PRODUCT_PNL, "SW", "cogs", "1"): 40_000_000,
        (SHEET_PRODUCT_PNL, "SW", "sga", "1"): 10_000_000,
        (SHEET_PRODUCT_PNL, "FS", "volume", "1"): 1_234,
    })
    report = _report(1, actual_overrides=actual_overrides)

    revenue = _row(report.pnl_rows, "revenue").comparison_by_period["2026-01"]
    assert revenue.actual == 100_000_000
    assert revenue.cells[1].text == "100"
    assert report.kpis[0].amount == 100_000_000
    assert report.kpis[0].amount_text == "100"
    assert report.monthly_trends[0].actual_revenue == 100_000_000
    assert report.monthly_trends[0].actual_revenue_text == "100"
    assert _row(report.monthly_data_rows, "revenue_actual").cells[0].text == "100"

    material = _row(report.cogs_rows, "mfg_material")
    assert material.months[0].amount == 1_000_000
    assert material.months[0].amount_text == "1"
    admin_labor = _row(report.sga_rows, "admin_labor").comparison_by_period["2026-01"]
    assert admin_labor.actual == 1_000_000
    assert admin_labor.cells[1].text == "1"

    sw_rows = _segment(report, "SW").rows
    sw_revenue = _row(sw_rows, "revenue").comparison_by_period["2026-01"]
    sw_volume = _row(sw_rows, "volume").comparison_by_period["2026-01"]
    sw_asp = _row(sw_rows, "asp").comparison_by_period["2026-01"]
    sw_cogs_ratio = _row(sw_rows, "cogs_ratio").comparison_by_period["2026-01"]
    assert (sw_revenue.actual, sw_revenue.cells[1].text) == (100_000_000, "100")
    assert (sw_volume.actual, sw_volume.cells[1].text) == (400, "400")
    assert (sw_asp.actual, sw_asp.cells[1].text) == (250_000, "250,000")
    assert sw_cogs_ratio.cells[1].text == "40.0%"

    fs_volume = _row(_segment(report, "FS").rows, "volume").comparison_by_period["2026-01"]
    assert (fs_volume.actual, fs_volume.cells[1].text) == (1_234, "1,234")
    assert _row(report.pnl_rows, "sales_volume").comparison_by_period["2026-01"].actual is None


def test_production_read_model_layer_has_no_forbidden_dependencies():
    root = Path(__file__).parents[1] / "forecast" / "reporting"
    sources = "\n".join(
        (root / name).read_text(encoding="utf-8").lower()
        for name in ("formulas.py", "formatting.py", "read_model.py")
    )
    forbidden = (
        "forecast.analysis",
        "sales_effects",
        "inventory_timing",
        "residual",
        "golden",
        "legacy pnl_dashboard",
        "calculation_results",
        "supabase",
        "forecast.bff",
        "forecast.persistence",
        "forecast.storage",
        "fastapi",
        "flask",
        "session",
    )
    assert not [name for name in forbidden if name in sources]
