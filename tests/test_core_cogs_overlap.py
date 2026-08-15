from __future__ import annotations

import pytest

from forecast.analysis.configuration import AnalysisConfig
from forecast.analysis.core_cogs_overlap import (
    CoreManufacturedCogsOverlap,
    calculate_core_manufactured_cogs_overlap,
)
from forecast.analysis.inventory_effects import calculate_inventory_timing_effects
from forecast.analysis.schema import (
    AnalysisScenario,
    InventoryCostRecord,
    ScenarioMeta,
)


def _source(side: str) -> dict:
    quantities = {
        "BASE": {"SW": 100, "BW": 50, "LC": 50, "FS": 100},
        "COMPARISON": {"SW": 90, "BW": 60, "LC": 50, "FS": 80},
    }[side]
    core = {"SW": 1_000, "BW": 1_000, "LC": 500, "FS": 500}
    rows = []
    for group in ("SW", "BW", "LC", "FS"):
        pool = "LENGTH" if group == "FS" else "PCS"
        rows.append({
            "period": "2026-07",
            "product_group": group,
            "pool": pool,
            "unit": "m" if pool == "LENGTH" else "PCS",
            "manufactured_quantity": quantities[group],
            "matched_manufactured_cogs": core[group],
            "quantity_source_available": True,
            "core_cogs_source_available": True,
            "quantity_source_reference": f"{side}:{group}:QTY",
            "core_cogs_source_reference": f"{side}:{group}:CORE",
        })
    return {"group_rows": rows}


def test_core_overlap_uses_separate_pcs_and_length_pools_and_core_only_sources():
    result = calculate_core_manufactured_cogs_overlap(
        _source("BASE"), _source("COMPARISON"), ("2026-07",)
    )

    assert result.policy_status == "APPLIED_CORE_ONLY"
    assert result.total_overlap_effect == pytest.approx(
        result.quantity_overlap_effect + result.mix_overlap_effect
    )
    assert {row["pool"] for row in result.details} == {"PCS", "LENGTH"}
    assert all(
        (row["pool"], row["unit"]) in {("PCS", "PCS"), ("LENGTH", "m")}
        for row in result.details
    )
    assert all(row["adjustment_excluded"] for row in result.details)
    assert all(row["merchandise_excluded"] for row in result.details)
    assert "LC_MERCHANDISE" in result.excluded_sources
    assert "CURRENT_COST_ROW_323_PAID_SUPPLY" in result.excluded_sources


def test_core_overlap_quantity_and_mix_signs_follow_op_convention():
    base = _source("BASE")
    comparison = _source("COMPARISON")
    result = calculate_core_manufactured_cogs_overlap(
        base, comparison, ("2026-07",)
    )

    expense_quantity = sum(
        row["embedded_quantity_cogs_expense"] for row in result.details
    )
    expense_mix = sum(row["embedded_mix_cogs_expense"] for row in result.details)
    assert result.quantity_overlap_effect == pytest.approx(-expense_quantity)
    assert result.mix_overlap_effect == pytest.approx(-expense_mix)


@pytest.mark.parametrize("failure", ["ZERO_DENOMINATOR", "MISSING_SOURCE", "POOL_MISMATCH"])
def test_core_overlap_invalid_source_fails_closed(failure: str):
    base = _source("BASE")
    comparison = _source("COMPARISON")
    target = next(row for row in base["group_rows"] if row["product_group"] == "BW")
    if failure == "ZERO_DENOMINATOR":
        target["manufactured_quantity"] = 0
    elif failure == "MISSING_SOURCE":
        target["core_cogs_source_available"] = False
    else:
        target["pool"] = "LENGTH"

    with pytest.raises(ValueError):
        calculate_core_manufactured_cogs_overlap(
            base, comparison, ("2026-07",)
        )


def _scenario(identifier: str, manufactured: float, current: float) -> AnalysisScenario:
    return AnalysisScenario(
        meta=ScenarioMeta(identifier, "ACTUAL", "V1"),
        inventory_costs=[InventoryCostRecord(
            year_month="2026-07",
            current_manufacturing_cost=current,
            finished_goods_cogs=manufactured,
            semi_finished_goods_cogs=0,
            source_validation_status="PASS",
            scope_validation_status="PASS",
        )],
    )


def test_inventory_timing_preserves_gross_and_applies_core_overlap_once():
    overlap = CoreManufacturedCogsOverlap(
        quantity_overlap_effect=120,
        mix_overlap_effect=-20,
        total_overlap_effect=100,
        source_validation_status="PASS",
        pool_validation_status="PASS",
        policy_status="APPLIED_CORE_ONLY",
        monthly_details=[{
            "period": "2026-07",
            "quantity_overlap_effect": 120,
            "mix_overlap_effect": -20,
            "total_overlap_effect": 100,
        }],
    )
    result = calculate_inventory_timing_effects(
        _scenario("base", manufactured=500, current=300),
        _scenario("comparison", manufactured=200, current=200),
        ("2026-07",),
        AnalysisConfig.load("config/analysis_v1.json"),
        operating_profit_delta=0,
        current_cost_related_effects=100,
        core_cogs_overlap=overlap,
    )

    assert result.manufactured_cogs_effect == 300
    assert result.current_manufacturing_cost_effect == 100
    assert result.gross_inventory_timing_effect == 200
    assert result.inventory_timing_effect == 100
    assert result.monthly_details[0]["gross_inventory_timing_effect"] == 200
    assert result.monthly_details[0]["inventory_timing_effect"] == 100
