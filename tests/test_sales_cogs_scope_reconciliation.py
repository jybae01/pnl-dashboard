from __future__ import annotations

from forecast.analysis.sales_cogs_scope import (
    analyze_sales_cogs_scope_reconciliation,
)


def _group(
    period: str,
    group: str,
    *,
    core: float,
    adjustment: float = 0.0,
    merchandise: float = 0.0,
    quantity: float = 10.0,
    revenue: float = 200.0,
) -> dict:
    pool = "LENGTH" if group == "FS" else "PCS"
    merch_quantity = 2.0 if merchandise else 0.0
    merch_revenue = 30.0 if merchandise else 0.0
    return {
        "period": period,
        "product_group": group,
        "pool": pool,
        "unit": "m" if pool == "LENGTH" else "PCS",
        "classification": "MANUFACTURED_ONLY",
        "manufactured_quantity": quantity,
        "manufactured_revenue": revenue,
        "matched_manufactured_cogs": core,
        "sales_manufactured_cogs": core + adjustment,
        "sales_product_quantity": quantity + merch_quantity,
        "sales_product_revenue": revenue + merch_revenue,
        "sales_product_cogs": core + adjustment + merchandise,
        "sales_adjustment": adjustment,
        "merchandise_quantity": merch_quantity,
        "merchandise_revenue": merch_revenue,
        "merchandise_cogs": merchandise,
        "source_reference": f"Data:{period}:{group}",
        "formula_trace": f"Data:{period}:{group}=SOURCE",
    }


def _source(side: str) -> dict:
    period = "2026-07"
    if side == "BASE":
        groups = [
            _group(period, "SW", core=100, adjustment=20),
            _group(period, "BW", core=0, quantity=5, revenue=80),
            _group(period, "LC", core=40, adjustment=5, merchandise=20),
            _group(period, "FS", core=20, quantity=20, revenue=100),
        ]
        pnl = {
            "finished_goods_cogs": 147,
            "semi_finished_goods_cogs": 22,
            "pnl_manufactured_cogs": 169,
            "core_finished_goods_cogs": 140,
            "core_semi_finished_goods_cogs": 20,
            "core_manufactured_cogs": 160,
            "finished_adjustment": 7,
            "semi_finished_adjustment": 2,
        }
        new = (0, 50, 40)
    else:
        groups = [
            _group(period, "SW", core=70, adjustment=10, quantity=8, revenue=170),
            _group(period, "BW", core=0, quantity=5, revenue=80),
            _group(period, "LC", core=30, adjustment=3, merchandise=10, quantity=9, revenue=180),
            _group(period, "FS", core=20, quantity=18, revenue=90),
        ]
        pnl = {
            "finished_goods_cogs": 105,
            "semi_finished_goods_cogs": 21,
            "pnl_manufactured_cogs": 126,
            "core_finished_goods_cogs": 100,
            "core_semi_finished_goods_cogs": 20,
            "core_manufactured_cogs": 120,
            "finished_adjustment": 5,
            "semi_finished_adjustment": 1,
        }
        new = (3, 30, 20)
    pnl.update({
        "period": period,
        "source_reference": f"Data:{side}:P&L",
        "formula_trace": f"Data:{side}:P&L=SOURCE",
    })
    sku_rows = []
    for group in ("SW", "BW", "LC", "FS"):
        sku_rows.append({
            "period": period,
            "sku": f"{group}_SKU",
            "product_group": group,
            "unit": "m" if group == "FS" else "PCS",
            "quantity": 1,
            "revenue": 2,
            "cogs": 1,
            "quantity_source_available": True,
            "revenue_source_available": True,
            "cogs_source_available": True,
            "source_reference": f"Data:{side}:{group}",
        })
    return {
        "group_rows": groups,
        "pnl_rows": [pnl],
        "new_business_rows": [{
            "period": period,
            "quantity": new[0],
            "quantity_raw": None if side == "BASE" else new[0],
            "mapped_revenue": new[1],
            "actual_revenue": new[1],
            "actual_cogs": new[2],
            "business_classification": "MERCHANDISE",
            "source_reference": f"Data:{side}:NEW",
        }],
        "sku_rows": sku_rows,
    }


def _analysis() -> dict:
    return analyze_sales_cogs_scope_reconciliation(
        baseline_source=_source("BASE"),
        comparison_source=_source("COMPARISON"),
        sales_cogs_basis_analysis={
            "summary": {
                "current_inventory_timing": 25,
                "embedded_sales_cogs_expense_delta": -15,
                "official_gp_quantity": 10,
                "official_gp_mix": 5,
                "matched_revenue_quantity": -2,
                "matched_revenue_mix": 1,
            }
        },
        inventory_analysis={
            "source_validation_status": "PASS",
            "scope_validation_status": "PASS",
        },
        effects_total=100,
        residual=-50,
        operating_profit_delta=50,
    )


def test_scope_difference_is_fully_classified_without_plug():
    analysis = _analysis()

    assert analysis["status"] == "PASS"
    assert analysis["verdict"] == "OVERLAP_CONFIRMED"
    assert analysis["option_readiness"] == "OPTION_A_NOT_READY"
    assert analysis["summary"]["sales_product_cogs_effect"] == 62
    assert analysis["summary"]["pnl_manufactured_cogs_effect"] == 43
    assert analysis["summary"]["scope_difference_sales_minus_pnl"] == 19
    assert analysis["summary"]["unexplained"] == 0
    components = {
        row["component"]: row["amount"]
        for row in analysis["scope_components"]
    }
    assert components["SW_SALES_COGS_ADJUSTMENT"] == 10
    assert components["LC_SALES_COGS_ADJUSTMENT"] == 2
    assert components["LC_MERCHANDISE_COGS_INCLUDED_IN_SALES"] == 10
    assert components["P&L_FINISHED_COGS_ADJUSTMENT"] == -2
    assert components["P&L_SEMI_FINISHED_COGS_ADJUSTMENT"] == -1
    assert {
        row["classification"]
        for row in analysis["scope_components"]
        if row["component"].endswith("ADJUSTMENT")
    } == {"FORMULA_BASIS_DIFFERENCE"}


def test_lc_new_business_sku_and_counterfactual_contracts_are_explicit():
    analysis = _analysis()

    assert analysis["lc_rows"][0]["separability"] == "LC_MANUFACTURED_MERCHANDISE_SEPARABLE"
    assert analysis["new_business_rows"][0]["denominator_status"] == "MISSING"
    assert analysis["new_business_rows"][0]["comparison_denominator_status"] == "AVAILABLE"
    assert analysis["new_business_rows"][0]["classification"] == "MERCHANDISE_NON_UNITIZED_BASE"
    assert {row["coverage"] for row in analysis["sku_coverage"]} == {"FULL"}
    assert all(abs(row["identity_difference"]) <= 1 for row in analysis["option_rows"])
    current = analysis["option_rows"][0]
    assert current["effects_total"] == 100
    assert current["residual"] == -50
    assert analysis["production_formula_mutated"] is False
