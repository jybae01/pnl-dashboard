from __future__ import annotations

from dataclasses import asdict
from hashlib import sha256
from io import BytesIO
from pathlib import Path

from openpyxl import load_workbook

from forecast.analysis_export import build_comparison_audit_workbook
from forecast.comparison import GenericComparisonEngine, PeriodOption
from forecast.evidence_reporting import REPORT_SHEETS, audit_reporting_workbook

try:
    from tests.test_golden_analysis_adapter import _build_workbook, _meta
except ModuleNotFoundError:
    from test_golden_analysis_adapter import _build_workbook, _meta


ROOT = Path(__file__).resolve().parents[1]


def _row_with_value(ws, column: str, value: object) -> int:
    return next(
        row for row in range(1, ws.max_row + 1)
        if ws[f"{column}{row}"].value == value
    )


def _analysis_result(tmp_path: Path):
    baseline = tmp_path / "baseline.xlsx"
    comparison = tmp_path / "comparison.xlsx"
    _build_workbook(baseline, comparison=False)
    _build_workbook(comparison, comparison=True)
    engine = GenericComparisonEngine(ROOT / "config" / "model_mapping.json")
    result = engine.compare(
        _meta("base"),
        baseline,
        _meta("comparison"),
        comparison,
        PeriodOption("M2026_01", "2026-01", (1,), "사용자정의"),
        baseline_sales_fx=1_400.0,
        comparison_sales_fx=1_450.0,
    )
    return result, baseline, comparison


def test_build_comparison_audit_workbook_uses_five_tab_formula_lineage(tmp_path):
    result, baseline, comparison = _analysis_result(tmp_path)
    before = {
        baseline: sha256(baseline.read_bytes()).hexdigest(),
        comparison: sha256(comparison.read_bytes()).hexdigest(),
    }
    payload = build_comparison_audit_workbook(
        result=asdict(result),
        sales_rows=result.sales_analysis["rows"],
        sales_totals=result.sales_analysis["totals"],
        baseline_fx=1_400.0,
        comparison_fx=1_450.0,
        baseline_path=baseline,
        comparison_path=comparison,
        mapping_path=ROOT / "config" / "model_mapping.json",
    )
    after = {
        baseline: sha256(baseline.read_bytes()).hexdigest(),
        comparison: sha256(comparison.read_bytes()).hexdigest(),
    }
    assert before == after

    workbook = load_workbook(BytesIO(payload), data_only=False)
    audit = audit_reporting_workbook(workbook)
    assert tuple(workbook.sheetnames) == REPORT_SHEETS
    assert audit["sheet_count"] == 5
    assert audit["formula_count"] >= 400
    assert audit["source_numeric_count"] > 100
    assert audit["hard_coded_derived_duplicates"] == 0
    assert audit["formula_error_count"] == 0
    assert workbook.calculation.calcMode == "auto"
    assert workbook.calculation.fullCalcOnLoad
    assert workbook.calculation.forceFullCalc

    source = workbook["90_원본값"]
    assert [source.cell(5, column).value for column in range(1, 13)] == [
        "Key", "구분", "항목", "Basis / 제품군", "기간", "단위",
        "기준 Source", "기준 원본값", "비교 Source", "비교 원본값", "비고",
        "Hard-code Class",
    ]
    assert all(
        not (isinstance(cell.value, str) and cell.value.startswith("="))
        for row in source.iter_rows()
        for cell in row
    )
    assert {
        source[f"L{row}"].value for row in range(6, source.max_row + 1)
    } <= {"MODEL_SOURCE", "REQUEST_INPUT", "POLICY_INPUT"}
    source_keys = {
        source[f"A{row}"].value: row for row in range(6, source.max_row + 1)
    }
    assert "pnl:operating_profit" in source_keys
    assert "policy:freight_meters_per_pcs" in source_keys
    assert any(key and str(key).startswith("production:SW:") for key in source_keys)
    assert any(
        "Data!E1026" in str(source[f"G{row}"].value)
        for row in range(6, source.max_row + 1)
    )
    assert any(
        "Data!E1051" in str(source[f"G{row}"].value)
        for row in range(6, source.max_row + 1)
    )
    activity_source_rows = [
        row for row in range(6, source.max_row + 1)
        if str(source[f"A{row}"].value).startswith("manufacturing_activity:")
    ]
    assert activity_source_rows
    assert all(
        "+" not in str(source[f"G{row}"].value or "")
        and "+" not in str(source[f"I{row}"].value or "")
        for row in activity_source_rows
    )
    assert sum(
        source[f"G{row}"].value == "Data!E560"
        and source[f"I{row}"].value == "Data!E560"
        for row in range(6, source.max_row + 1)
    ) == 1

    effects = workbook["02_손익영향"]
    effect_codes = {
        effects[f"G{row}"].value: effects[f"C{row}"].value
        for row in range(1, effects.max_row + 1)
        if effects[f"G{row}"].value in {
            "sales_quantity", "sales_mix", "sales_price", "sales_fx", "tariff",
            "material_total", "manufacturing_realized", "inventory_timing",
            "sga_variable", "sga_fixed",
        }
    }
    assert len(effect_codes) == 10
    assert all(
        str(formula).startswith("='03_판매근거'!")
        if code in {"sales_quantity", "sales_mix", "sales_price", "sales_fx", "tariff"}
        else str(formula).startswith("='04_원가근거'!")
        for code, formula in effect_codes.items()
    )
    effects_total = _row_with_value(effects, "C", "Effects Total")
    residual = _row_with_value(effects, "C", "기타 요인")
    reconciliation = _row_with_value(
        effects, "A", "OP Delta = Effects Total + 기타 요인"
    )
    assert effects[f"D{effects_total}"].value.startswith("=SUM(")
    assert effects[f"D{residual}"].value.startswith("=D")
    assert effects[f"F{reconciliation}"].value.startswith("=IF(")

    summary = workbook["01_보고요약"]
    numeric_summary_cells = [
        cell
        for row in summary.iter_rows()
        for cell in row
        if cell.number_format == '#,##0;[Red](#,##0);-'
    ]
    assert numeric_summary_cells
    assert all(
        isinstance(cell.value, str) and cell.value.startswith("='02_손익영향'!")
        for cell in numeric_summary_cells
    )

    sales = workbook["03_판매근거"]
    new_business_row = _row_with_value(sales, "A", "신사업")
    assert sales[f"E{new_business_row}"].value is None
    assert sales[f"F{new_business_row}"].value is None
    assert sales[f"G{new_business_row}"].value is None
    sales_price_row = _row_with_value(sales, "A", "sales_price")
    assert sales[f"C{sales_price_row}"].value.startswith("=")

    cost = workbook["04_원가근거"]
    manufacturing_section = _row_with_value(cost, "A", "C. 제조경비")
    activity_row = manufacturing_section + 2
    assert cost[f"B{activity_row}"].value.startswith("=")
    assert "'90_원본값'!" in cost[f"B{activity_row}"].value
    assert cost[f"D{activity_row}"].value.startswith("=")
    sw_row = _row_with_value(cost, "B", "SW")
    bw_row = _row_with_value(cost, "B", "BW")
    lc_row = _row_with_value(cost, "B", "LC")
    fs_row = _row_with_value(cost, "B", "FS")
    back_row = _row_with_value(cost, "B", "SW+BW+LC")
    assert cost[f"D{sw_row}"].value.startswith("=SUM('90_원본값'!")
    assert cost[f"G{sw_row}"].value.startswith("=SUM('90_원본값'!")
    assert cost[f"I{sw_row}"].value == f'=IF(D{sw_row}=0,"",G{sw_row}*1000/D{sw_row})'
    assert cost[f"D{back_row}"].value == f"=SUM(D{sw_row},D{bw_row},D{lc_row})"
    assert f"D{fs_row}" not in cost[f"D{back_row}"].value
    assert cost[f"I{back_row}"].value == (
        f'=IF(D{back_row}=0,"",G{back_row}*1000/D{back_row})'
    )
    assert any(
        cell.value == "* 생산 수량과 금액: 수불부 기준"
        for row in cost.iter_rows()
        for cell in row
    )

    for name in REPORT_SHEETS:
        sheet = workbook[name]
        assert sheet.freeze_panes
        assert not sheet.sheet_view.showGridLines
        assert sheet.page_setup.orientation in {"portrait", "landscape"}
        assert sheet.page_setup.fitToWidth == 1
        assert sheet.print_area


def test_reporting_sheets_have_no_hard_coded_derived_numeric_cells(tmp_path):
    result, _, _ = _analysis_result(tmp_path)
    payload = build_comparison_audit_workbook(
        result=asdict(result),
        sales_rows=result.sales_analysis["rows"],
        sales_totals=result.sales_analysis["totals"],
        baseline_fx=1_400.0,
        comparison_fx=1_450.0,
        mapping_path=ROOT / "config" / "model_mapping.json",
    )
    workbook = load_workbook(BytesIO(payload), data_only=False)
    assert not {
        f"{sheet.title}!{cell.coordinate}"
        for sheet in workbook.worksheets
        if sheet.title != "90_원본값"
        for row in sheet.iter_rows()
        for cell in row
        if isinstance(cell.value, (int, float)) and not isinstance(cell.value, bool)
    }
