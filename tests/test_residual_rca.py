from __future__ import annotations

from hashlib import sha256
from pathlib import Path

import pytest
from openpyxl import load_workbook

from forecast.analysis.residual_rca import analyze_residual_rca
from forecast.comparison import GenericComparisonEngine, PeriodOption

try:
    from tests.test_golden_analysis_adapter import _build_workbook, _meta
except ModuleNotFoundError:
    from test_golden_analysis_adapter import _build_workbook, _meta


ROOT = Path(__file__).resolve().parents[1]


def _rca(*, cover_other_cogs: bool = True):
    effects = [
        {"code": "sales_quantity", "profit_effect": 30.0},
        {"code": "sales_mix", "profit_effect": 10.0},
        {"code": "sales_price", "profit_effect": 50.0},
        {"code": "sales_fx", "profit_effect": 5.0},
        {"code": "tariff", "profit_effect": 0.0},
        {"code": "material_total", "profit_effect": -20.0},
        {"code": "manufacturing_realized", "profit_effect": -5.0},
        {"code": "inventory_timing", "profit_effect": -5.0},
        {"code": "sga_variable", "profit_effect": 5.0},
        {"code": "sga_fixed", "profit_effect": 0.0},
    ]
    basis = {
        "basis_gap": 0.0,
        "manufacturing_activity_effect": -2.0,
        "manufacturing_unit_effect": -3.0,
        "manufacturing_fixed_effect": 0.0,
        "component_details": [],
        "gap_classification": [
            {
                "classification": "UNEXPLAINED",
                "amount": 0.0,
                "source_coverage": "NOT_APPLICABLE",
                "reason": "No current-cost basis remainder",
            }
        ],
        "unexplained_amount": 0.0,
    }
    comparison_bases = {
        "goods_cogs": 110.0,
        "other_cogs": 30.0 if cover_other_cogs else 20.0,
    }
    return analyze_residual_rca(
        baseline_pnl={
            "revenue": 1_000.0,
            "cogs": 600.0,
            "selling_expense": 100.0,
            "general_admin": 100.0,
            "operating_profit": 200.0,
        },
        comparison_pnl={
            "revenue": 1_100.0,
            "cogs": 650.0,
            "selling_expense": 90.0,
            "general_admin": 110.0,
            "operating_profit": 250.0,
        },
        baseline_effect_bases={"goods_cogs": 100.0, "other_cogs": 20.0},
        comparison_effect_bases=comparison_bases,
        effects=effects,
        sales_analysis={
            "totals": {
                "displayed_sales_price_effect": 55.0,
                "transport_effect": -5.0,
            }
        },
        material_analysis={"nonwoven_jpy": -4.0},
        inventory_analysis={
            "base_manufactured_cogs": 400.0,
            "comparison_manufactured_cogs": 430.0,
            "manufactured_cogs_effect": -30.0,
            "current_cost_basis_analysis": basis,
        },
        sga_accounts=[],
        source_rows={
            "pnl_rows": {
                "revenue": 1248,
                "cogs": 1268,
                "selling_expense": 1302,
                "general_admin": 1303,
                "operating_profit": 1306,
            },
            "effect_rows": {
                "goods_cogs": 1289,
                "other_cogs": 1292,
                "paid_supply_cancel": 1293,
                "customs_refund": 1294,
                "obsolescence": 1295,
            },
            "inventory_rows": {
                "finished_goods_cogs": 1269,
                "semi_finished_goods_cogs": 1280,
                "labor": 289,
                "manufacturing_expense": 296,
            },
        },
        months=(1,),
        period_label="1월",
        operating_profit_delta=50.0,
        effects_total=sum(item["profit_effect"] for item in effects),
        residual=-20.0,
    )


def test_residual_rca_closes_direct_bridge_and_classified_components():
    result = _rca()

    assert result["status"] == "PASS"
    assert result["direct_op_bridge"]["base"]["validation"] == "PASS"
    assert result["direct_op_bridge"]["comparison"]["validation"] == "PASS"
    assert result["direct_op_bridge"]["validation"] == "PASS"
    assert result["classified_total"] == pytest.approx(result["existing_residual"])
    assert result["difference"] == pytest.approx(0.0)
    assert result["unexplained"] == pytest.approx(0.0)
    assert result["plug_created"] is False
    assert all(item["status"] == "PASS" for item in result["checks"])


def test_effect_map_has_one_additive_parent_and_non_additive_children():
    result = _rca()
    effect_map = {item["effect_code"]: item for item in result["effect_to_pnl_map"]}

    assert effect_map["sales_price"]["additive"] is True
    assert effect_map["freight_adjustment"]["additive"] is False
    assert effect_map["freight_adjustment"]["parent"] == "sales_price"
    assert effect_map["freight_adjustment"]["rca_allocation"] is True
    assert effect_map["nonwoven_jpy"]["amount"] == pytest.approx(-4.0)
    assert effect_map["nonwoven_price_ex_fx"]["additive"] is False
    assert effect_map["materials_ex_nonwoven"]["additive"] is False
    assert effect_map["mcm_policy"]["additive"] is False
    assert effect_map["mcm_policy"]["rca_allocation"] is False
    assert effect_map["mcm_policy"]["amount"] is None
    assert effect_map["manufacturing_activity"]["amount"] == pytest.approx(-2.0)
    assert effect_map["goods_cogs"]["additive"] is False
    assert effect_map["other_cogs_scope_total"]["additive"] is False
    assert effect_map["paid_supply_cancel"]["parent"] == "other_cogs_scope_total"
    assert effect_map["current_cost_basis_gap"]["additive"] is False
    assert result["double_count_assertions"] == {
        key: "PASS" for key in result["double_count_assertions"]
    }


def test_uncovered_source_amount_stays_explicitly_unexplained():
    result = _rca(cover_other_cogs=False)
    unexplained = next(
        item for item in result["components"] if item["classification"] == "UNEXPLAINED"
    )

    assert unexplained["amount"] == pytest.approx(-10.0)
    assert unexplained["source_coverage"] == "NONE"
    assert "Other COGS component coverage" in unexplained["source_reference"]
    assert result["classified_total"] == pytest.approx(result["existing_residual"])
    assert result["difference"] == pytest.approx(0.0)


def test_comparison_engine_persists_fixture_rca_without_mutating_sources(tmp_path):
    base_path = tmp_path / "base.xlsx"
    comparison_path = tmp_path / "comparison.xlsx"
    _build_workbook(base_path)
    _build_workbook(comparison_path, comparison=True)

    for path, selling, general_admin, operating_profit in (
        (base_path, 80.0, 62.0, -42.0),
        (comparison_path, 80.0, 59.0, -39.0),
    ):
        workbook = load_workbook(path)
        data = workbook["Data"]
        data["E1302"] = selling
        data["E1303"] = general_admin
        data["E1306"] = operating_profit
        workbook.save(path)

    before = {
        path: sha256(path.read_bytes()).hexdigest()
        for path in (base_path, comparison_path)
    }
    result = GenericComparisonEngine(ROOT / "config" / "model_mapping.json").compare(
        _meta("base"),
        base_path,
        _meta("comparison"),
        comparison_path,
        PeriodOption("M01", "1월", (1,), "월"),
        baseline_sales_fx=1_000.0,
        comparison_sales_fx=1_100.0,
    )
    after = {
        path: sha256(path.read_bytes()).hexdigest()
        for path in (base_path, comparison_path)
    }

    assert before == after
    assert result.operating_profit_delta == pytest.approx(3.0)
    assert result.residual_analysis["status"] == "PASS"
    assert result.residual_analysis["classified_total"] == pytest.approx(
        result.residual
    )
    assert result.residual_analysis["difference"] == pytest.approx(0.0)
    assert result.residual_analysis["unexplained"] == pytest.approx(0.0)
    assert result.residual_analysis["plug_created"] is False
    assert all(
        item["status"] == "PASS" for item in result.residual_analysis["checks"]
    )
