from pathlib import Path

import pytest

from forecast.workbook import GoldenWorkbook
from scripts.golden_model_validation import (
    build_comparison,
    validate_excel_calculated_pair,
    validate_single_driver_scenarios,
)


ROOT = Path(__file__).resolve().parents[1]
MAPPING = ROOT / "config" / "model_mapping.json"
PRIVATE_MODEL = ROOT / "models" / "golden_model.xlsx"
LOCAL_MODEL = ROOT / "★손익추정 시뮬레이션_rev1_1~6월 실적 입력_v1.3.xlsx"


def _golden_model() -> Path:
    model = PRIVATE_MODEL if PRIVATE_MODEL.is_file() else LOCAL_MODEL
    if not model.is_file():
        pytest.skip("private Golden Model is not available")
    return model


def test_average_removes_all_known_golden_fallbacks():
    diagnostics = GoldenWorkbook(_golden_model()).formula_diagnostics()
    assert diagnostics["workbook_formula_count"] == 14_569
    assert diagnostics["evaluator_success_count"] == 14_569
    assert diagnostics["cached_fallback_count"] == 0
    assert diagnostics["cached_numeric_mismatch_count"] == 0


def test_synthetic_comparison_keeps_k106_denominator_valid(tmp_path):
    base = _golden_model()
    comparison = tmp_path / "synthetic.xlsx"
    build_comparison(base, comparison, MAPPING)
    workbook = GoldenWorkbook(comparison)
    diagnostics = workbook.formula_diagnostics()
    assert float(workbook.value("K104")) > 0
    assert not any(row["address"] == "K106" for row in diagnostics["fallbacks"])
    acceptance = validate_excel_calculated_pair(base, comparison, MAPPING)
    gate = acceptance["excel_pair_acceptance"]
    assert gate["level_2_workbook_propagation"] == "CHECK"
    assert gate["cached_freshness"]["comparison"]["cached_mismatch_cells"]
    assert gate["status"] == "CHECK"


def test_sales_quantity_controlled_pair_has_no_nontarget_effect(tmp_path):
    report = validate_single_driver_scenarios(
        _golden_model(), tmp_path, MAPPING, scenario_codes={"sales_quantity"}
    )
    scenario = report["scenarios"][0]
    assert scenario["unexpected_effects"] == {}
    assert abs(scenario["residual"]) <= 1.0


def test_excel_calculated_pair_mode_is_explicitly_blocked_without_pair():
    assert validate_excel_calculated_pair(None, None, MAPPING)["status"] == (
        "BLOCKED_NO_EXCEL_CALCULATED_PAIR"
    )
