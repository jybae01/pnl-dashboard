from __future__ import annotations

from forecast.analysis.configuration import AnalysisConfig
from forecast.analysis.current_cost_basis import calculate_current_cost_basis_analysis
from forecast.analysis.manufacturing_effects import ManufacturingEffects
from forecast.analysis.material_effects import MaterialEffects
from forecast.analysis.schema import (
    AnalysisScenario,
    CurrentCostComponentRecord,
    ScenarioMeta,
)


CONFIG = AnalysisConfig(
    product_groups=("FS", "SW", "BW", "LC"),
    variable_manufacturing_accounts=frozenset(),
    variable_sga_accounts=frozenset(),
    transport_accounts=frozenset(),
    outsourcing_accounts=frozenset({"outsourcing"}),
    labor_accounts=frozenset(),
    absolute_tolerance=1.0,
    relative_tolerance=1e-9,
)


def _scenario(side: str, amounts: dict[str, float]) -> AnalysisScenario:
    return AnalysisScenario(
        meta=ScenarioMeta(side, side, "V1"),
        current_cost_components=[
            CurrentCostComponentRecord(
                "2026-01",
                code,
                code,
                "manufacturing" if code in {"labor", "manufacturing_expense"} else "raw_material",
                "test",
                amount,
                f"Data!E{index}",
                source_validation_status="PASS",
            )
            for index, (code, amount) in enumerate(amounts.items(), 300)
        ],
    )


def test_current_cost_basis_classifies_raw_scope_gap_without_plug() -> None:
    base = _scenario("base", {
        "raw_material_production_issue": 100,
        "raw_material_tariff_refund": 0,
        "paid_supply": 0,
        "labor": 50,
        "manufacturing_expense": 50,
    })
    comparison = _scenario("comparison", {
        "raw_material_production_issue": 90,
        "raw_material_tariff_refund": -5,
        "paid_supply": 20,
        "labor": 40,
        "manufacturing_expense": 60,
    })
    material = MaterialEffects(total=-2)
    manufacturing = ManufacturingEffects(
        front_unit=-10,
        front_fixed=10,
        occurrence_total=0,
        details=[
            {
                "account": "labor account",
                "current_cost_component": "labor",
                "baseline_amount": 50,
                "comparison_amount": 40,
                "activity_effect": 0,
                "unit_effect": 0,
                "fixed_effect": 10,
                "occurrence_effect": 10,
            },
            {
                "account": "other account",
                "current_cost_component": "manufacturing_expense",
                "baseline_amount": 50,
                "comparison_amount": 60,
                "activity_effect": 0,
                "unit_effect": -10,
                "fixed_effect": 0,
                "occurrence_effect": -10,
            },
        ],
    )

    result = calculate_current_cost_basis_analysis(
        base,
        comparison,
        current_manufacturing_cost_effect=-5,
        material=material,
        manufacturing=manufacturing,
        config=CONFIG,
    )

    assert result.existing_current_cost_driver_subtotal == -2
    assert result.basis_gap == -3
    assert result.raw_material_basis_gap == -3
    assert result.manufacturing_basis_gap == 0
    assert result.unexplained_amount == 0
    assert result.status == "CHECK_SCOPE_GAP"
    assert result.architecture_decision == "OPTION_C"
    assert result.plug_created is False
    assert sum(row["amount"] for row in result.gap_classification) == result.basis_gap


def test_manufacturing_components_reconcile_direct_to_activity_unit_fixed() -> None:
    base = _scenario("base", {
        "raw_material_production_issue": 0,
        "raw_material_tariff_refund": 0,
        "paid_supply": 0,
        "labor": 80,
        "manufacturing_expense": 100,
    })
    comparison = _scenario("comparison", {
        "raw_material_production_issue": 0,
        "raw_material_tariff_refund": 0,
        "paid_supply": 0,
        "labor": 70,
        "manufacturing_expense": 90,
    })
    manufacturing = ManufacturingEffects(
        front_activity=3,
        front_unit=7,
        front_fixed=10,
        occurrence_total=20,
        details=[
            {
                "account": "labor account",
                "current_cost_component": "labor",
                "baseline_amount": 80,
                "comparison_amount": 70,
                "activity_effect": 0,
                "unit_effect": 0,
                "fixed_effect": 10,
                "occurrence_effect": 10,
            },
            {
                "account": "outsourcing",
                "current_cost_component": "manufacturing_expense",
                "baseline_amount": 100,
                "comparison_amount": 90,
                "activity_effect": 3,
                "unit_effect": 7,
                "fixed_effect": 0,
                "occurrence_effect": 10,
            },
        ],
    )

    result = calculate_current_cost_basis_analysis(
        base,
        comparison,
        current_manufacturing_cost_effect=20,
        material=MaterialEffects(total=0),
        manufacturing=manufacturing,
        config=CONFIG,
    )

    assert result.manufacturing_basis_gap == 0
    assert result.basis_gap == 0
    assert result.status == "PASS"
    assert result.architecture_decision == "OPTION_A"
    assert {row["component_code"] for row in result.manufacturing_driver_details} == {
        "labor", "outsourcing", "other_manufacturing_expense"
    }
