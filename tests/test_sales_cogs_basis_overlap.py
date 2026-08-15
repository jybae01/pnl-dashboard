from __future__ import annotations

import pytest

from forecast.analysis.sales_cogs_overlap import (
    analyze_sales_cogs_basis_overlap,
)
from forecast.analysis.schema import PnlRecord


def _trace(period: str, pool: str, group: str, q0: float, q1: float, revenue: float, cogs: float):
    return {
        "period": period,
        "pool": pool,
        "unit": "m" if pool == "LENGTH" else "PCS",
        "product_group": group,
        "base_quantity": q0,
        "comparison_quantity": q1,
        "base_revenue": revenue,
        "comparison_revenue": revenue,
        "base_cogs": cogs,
        "comparison_cogs": cogs,
        "price_effect": 0.0,
        "sales_fx_effect": 0.0,
        "base_source_reference": f"Base:{period}:{group}",
        "comparison_source_reference": f"Comparison:{period}:{group}",
        "validation_status": "SOURCE_MAPPED",
    }


def _analysis():
    periods = ("2026-07", "2026-08", "2026-09")
    traces = []
    pools = []
    inventory = []
    base_pnl = []
    comparison_pnl = []
    for period in periods:
        traces.extend([
            _trace(period, "PCS", "SW", 100, 80, 1_000, 600),
            _trace(period, "PCS", "BW", 100, 120, 2_000, 1_000),
            _trace(period, "PCS", "LC", 0, 0, 0, 0),
            _trace(period, "LENGTH", "FS", 100, 80, 500, 300),
            _trace(period, "PCS", "New Business", 0, 10, 100, 80),
        ])
        pools.extend([
            {
                "period": period,
                "pool": "PCS",
                "unit": "PCS",
                "quantity_effect": 10.0,
                "mix_effect": 110.0,
            },
            {
                "period": period,
                "pool": "LENGTH",
                "unit": "m",
                "quantity_effect": -40.0,
                "mix_effect": 0.0,
            },
        ])
        inventory.append({
            "period": period,
            "base_manufactured_cogs": 1_000.0,
            "comparison_manufactured_cogs": 900.0,
            "manufactured_cogs_effect": 100.0,
            "base_current_manufacturing_cost": 950.0,
            "comparison_current_manufacturing_cost": 900.0,
            "current_manufacturing_cost_effect": 50.0,
            "inventory_timing_effect": 50.0,
            "source_reference": f"Data:{period}",
        })
        base_pnl.append(PnlRecord(period, 1_000, 700, 200))
        comparison_pnl.append(PnlRecord(period, 900, 600, 300))
    effects = [
        {"code": "sales_quantity", "profit_effect": -120.0},
        {"code": "sales_mix", "profit_effect": 360.0},
        {"code": "sales_price", "profit_effect": 0.0},
        {"code": "sales_fx", "profit_effect": 0.0},
        {"code": "tariff", "profit_effect": 0.0},
        {"code": "material_total", "profit_effect": 0.0},
        {"code": "manufacturing_realized", "profit_effect": 0.0},
        {"code": "inventory_timing", "profit_effect": 150.0},
        {"code": "sga_variable", "profit_effect": 0.0},
        {"code": "sga_fixed", "profit_effect": 0.0},
    ]
    return analyze_sales_cogs_basis_overlap(
        sales_analysis={
            "trace_rows": traces,
            "pool_trace_rows": pools,
            "freight_trace_rows": [],
        },
        sales_scope_contract={
            "LC": {
                "status": "MAPPING_GAP_LC_MANUFACTURED_QUANTITY_TOTAL_COGS",
                "quantity_row": 56,
                "amount_row": 1669,
                "cogs_row": 1670,
            }
        },
        inventory_analysis={
            "monthly_details": inventory,
            "source_validation_status": "PASS",
            "scope_validation_status": "PASS",
        },
        effects=effects,
        product_rows=[
            {"code": "SW400", "baseline_quantity": 100, "comparison_quantity": 80, "baseline_amount": 1_000},
            {"code": "SW440", "baseline_quantity": 100, "comparison_quantity": 120, "baseline_amount": 2_000},
            {"code": "BW400", "baseline_quantity": 100, "comparison_quantity": 90, "baseline_amount": 1_000},
            {"code": "BW440", "baseline_quantity": 100, "comparison_quantity": 110, "baseline_amount": 1_500},
        ],
        manufactured_groups=("SW", "BW", "LC", "FS"),
        material_details=[],
        manufacturing_details=[],
        sga_details=[],
        baseline_pnl_records=base_pnl,
        comparison_pnl_records=comparison_pnl,
        sku_source_rows={
            "SW400": {"quantity_row": 32, "amount_row": 33},
            "SW440": {"quantity_row": 38, "amount_row": 39},
            "BW400": {"quantity_row": 44, "amount_row": 45},
            "BW440": {"quantity_row": 50, "amount_row": 51},
        },
        months=(7, 8, 9),
        period_label="7~9월",
        operating_profit_delta=300.0,
        effects_total=390.0,
        residual=-90.0,
        residual_analysis={
            "components": [
                {
                    "component_id": "sales_formula_basis_gap",
                    "amount": 75.0,
                }
            ]
        },
    )


def test_revenue_gp_and_embedded_cogs_components_reconcile() -> None:
    result = _analysis()
    july_pcs = next(
        row for row in result["pool_rows"]
        if row["period"] == "2026-07" and row["pool"] == "PCS"
    )
    july_length = next(
        row for row in result["pool_rows"]
        if row["period"] == "2026-07" and row["pool"] == "LENGTH"
    )

    assert july_pcs["revenue_basis_mix"] == pytest.approx(200.0)
    assert july_pcs["matched_gp_mix"] == pytest.approx(120.0)
    assert july_pcs["embedded_cogs_mix_expense_delta"] == pytest.approx(80.0)
    assert july_length["revenue_basis_quantity"] == pytest.approx(-100.0)
    assert july_length["matched_gp_quantity"] == pytest.approx(-40.0)
    assert july_length["embedded_cogs_quantity_expense_delta"] == pytest.approx(-60.0)
    assert result["summary"]["embedded_sales_cogs_expense_delta"] == pytest.approx(60.0)
    assert result["summary"]["overlap_profit_candidate"] == pytest.approx(-60.0)
    assert result["summary"]["slice5a_sales_formula_basis_gap"] == pytest.approx(75.0)
    assert result["summary"]["basis_gap_after_embedded_candidate"] == pytest.approx(15.0)
    assert result["summary"]["embedded_candidate_coverage_ratio"] == pytest.approx(0.8)


def test_month_pool_scope_and_counterfactuals_are_separate() -> None:
    result = _analysis()

    assert {row["period"] for row in result["pool_rows"]} == {
        "2026-07", "2026-08", "2026-09"
    }
    assert {row["pool"] for row in result["pool_rows"]} == {"PCS", "LENGTH"}
    assert all(row["product_group"] != "New Business" for row in result["detail_rows"])
    assert all(
        (row["pool"], row["unit"]) in {("PCS", "PCS"), ("LENGTH", "m")}
        for row in result["detail_rows"]
    )
    july_pcs = next(
        row for row in result["pool_rows"]
        if row["period"] == "2026-07" and row["pool"] == "PCS"
    )
    assert july_pcs["official_vs_matched_gp_quantity_difference"] != 0
    assert july_pcs["official_vs_matched_gp_mix_difference"] != 0
    assert july_pcs["official_vs_matched_gp_scope_difference"] == pytest.approx(0.0)
    cumulative = {
        row["option"]: row
        for row in result["option_rows"] if row["period"] == "7~9월"
    }
    assert cumulative["CURRENT"]["effects_total"] == pytest.approx(390.0)
    assert cumulative["CURRENT"]["residual"] == pytest.approx(-90.0)
    assert cumulative["OPTION_A"]["effects_total"] == pytest.approx(450.0)
    assert cumulative["OPTION_B"]["effects_total"] == pytest.approx(450.0)
    assert cumulative["OPTION_A"]["residual"] == pytest.approx(-150.0)
    assert cumulative["OPTION_B"]["residual"] == pytest.approx(-150.0)
    assert cumulative["OPTION_C"] == {
        **cumulative["CURRENT"],
        "option": "OPTION_C",
        "counterfactual_only": True,
    }


def test_partial_overlap_and_intra_group_source_limit_are_explicit() -> None:
    result = _analysis()

    assert result["status"] == "PASS"
    assert result["verdict"] == "PARTIAL_OVERLAP"
    assert result["counterfactual_only"] is True
    assert result["production_formula_mutated"] is False
    assert result["recommendation"] == "OPTION_C_PENDING_SCOPE_RECONCILIATION"
    assert result["scope"]["mapping_gaps"] == [
        "MAPPING_GAP_LC_MANUFACTURED_QUANTITY_TOTAL_COGS"
    ]
    lc = next(
        row for row in result["detail_rows"] if row["product_group"] == "LC"
    )
    assert lc["classification"] == "SALES_EMBEDDED_COGS_CANDIDATE_MAPPING_GAP"
    assert all(item["status"] == "PASS" for item in result["checks"])
    assert {row["validation"] for row in result["intra_group_sku"]} == {
        "INSUFFICIENT_SOURCE"
    }
    assert all(
        row["embedded_cogs_component"] is None
        for row in result["intra_group_sku"]
    )
