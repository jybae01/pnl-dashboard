from __future__ import annotations

from forecast.analysis.configuration import AnalysisConfig
from forecast.analysis.inventory_effects import (
    PERSISTENCE_CONSISTENT,
    PERSISTENCE_EMERGING,
    PERSISTENCE_INSUFFICIENT,
    PERSISTENCE_MIXED,
    PERSISTENCE_REVERSAL,
    calculate_inventory_timing_effects,
    classify_persistence,
)
from forecast.analysis.manufacturing_effects import calculate_manufacturing_effects
from forecast.analysis.schema import (
    ActivityRecord,
    AnalysisScenario,
    ExpenseRecord,
    InventoryCostRecord,
    OpeningInventoryUnitRecord,
    ScenarioMeta,
)


def _config(*, materiality: float | None = None) -> AnalysisConfig:
    return AnalysisConfig(
        product_groups=("SW", "BW", "LC", "FS"),
        variable_manufacturing_accounts=frozenset({"utilities"}),
        variable_sga_accounts=frozenset(),
        transport_accounts=frozenset(),
        outsourcing_accounts=frozenset(),
        labor_accounts=frozenset(),
        absolute_tolerance=1.0,
        relative_tolerance=1e-9,
        inventory_materiality_absolute=materiality,
    )


def _scenario(identifier: str, monthly: list[tuple[str, float, float, float]]) -> AnalysisScenario:
    units = []
    for month, *_ in monthly:
        for group, basis, spec, qty, cost in (
            ("FS", "LENGTH", "FS", 100.0, 10.0),
            ("SW", "PCS", "SW400+SW440", 20.0, 20.0),
            ("BW", "PCS", "BW400+BW440", 30.0, 30.0),
            ("LC", "PCS", "4-inch", 40.0, 40.0),
        ):
            units.append(OpeningInventoryUnitRecord(
                month, group, basis, spec, qty, qty * cost, cost,
                f"Data!{month}:{group}:qty", f"Data!{month}:{group}:amount",
            ))
    return AnalysisScenario(
        meta=ScenarioMeta(identifier, identifier, "V1"),
        inventory_costs=[
            InventoryCostRecord(
                month, current, finished, semi,
                f"Data!{month}:current", f"Data!{month}:finished", f"Data!{month}:semi",
                "PASS", "PASS", ("manufactured scope",),
            )
            for month, current, finished, semi in monthly
        ],
        opening_inventory_units=units,
    )


def test_inventory_timing_formula_and_profit_sign() -> None:
    base = _scenario("base", [("2026-07", 900.0, 700.0, 300.0)])
    comparison = _scenario("comparison", [("2026-07", 800.0, 650.0, 250.0)])
    result = calculate_inventory_timing_effects(
        base, comparison, ("2026-07",), _config(),
        operating_profit_delta=100.0, current_cost_related_effects=100.0,
    )

    assert result.manufactured_cogs_effect == 100.0
    assert result.current_manufacturing_cost_effect == 100.0
    assert result.inventory_timing_effect == 0.0

    worse = _scenario("comparison", [("2026-07", 800.0, 800.0, 350.0)])
    result = calculate_inventory_timing_effects(
        base, worse, ("2026-07",), _config(),
        operating_profit_delta=-100.0, current_cost_related_effects=100.0,
    )
    assert result.manufactured_cogs_effect == -150.0
    assert result.current_manufacturing_cost_effect == 100.0
    assert result.inventory_timing_effect == -250.0


def test_persistence_rules() -> None:
    assert classify_persistence([10, 20, 30], latest_material=True) == PERSISTENCE_CONSISTENT
    assert classify_persistence([-10, 20, 30], latest_material=True) == PERSISTENCE_EMERGING
    assert classify_persistence([10, -20, 30], latest_material=True) == PERSISTENCE_MIXED
    assert classify_persistence([10, 20, -30], latest_material=True) == PERSISTENCE_REVERSAL
    assert classify_persistence([10, 20], latest_material=True) == PERSISTENCE_INSUFFICIENT


def test_units_coverage_and_no_primary_when_materiality_unconfigured() -> None:
    base = _scenario("base", [
        ("2026-05", 100.0, 70.0, 30.0),
        ("2026-06", 100.0, 70.0, 30.0),
        ("2026-07", 100.0, 70.0, 30.0),
    ])
    comparison = _scenario("comparison", [
        ("2026-05", 90.0, 65.0, 25.0),
        ("2026-06", 90.0, 65.0, 25.0),
        ("2026-07", 90.0, 65.0, 25.0),
    ])
    result = calculate_inventory_timing_effects(
        base, comparison, ("2026-07",), _config(),
        operating_profit_delta=10.0, current_cost_related_effects=10.0,
    )

    by_group = {row["product_group"]: row for row in result.opening_inventory_units}
    assert by_group["FS"]["unit_basis"] == "LENGTH"
    assert all(by_group[group]["unit_basis"] == "PCS" for group in ("SW", "BW", "LC"))
    assert by_group["LC"]["specification"] == "4-inch"
    assert result.product_unit_coverage == "LIMITED"
    assert result.materiality_status == "UNCONFIGURED"
    assert result.primary == "NO_PRIMARY"
    assert "LIMITED_COVERAGE" in result.explanation_rule


def test_direction_mismatch_remains_reference_and_no_primary() -> None:
    base = _scenario("base", [("2026-07", 100.0, 100.0, 50.0)])
    comparison = _scenario("comparison", [("2026-07", 90.0, 80.0, 40.0)])
    result = calculate_inventory_timing_effects(
        base, comparison, ("2026-07",), _config(materiality=1.0),
        operating_profit_delta=100.0, current_cost_related_effects=10.0,
    )
    assert result.inventory_timing_effect > 0
    assert not any(row["direction_aligned"] for row in result.opening_inventory_units)
    assert result.primary == "NO_PRIMARY"
    assert result.reference


def test_realization_rate_is_reference_only_and_never_changes_effect() -> None:
    def scenario(identifier: str, rate: float, amount: float) -> AnalysisScenario:
        return AnalysisScenario(
            meta=ScenarioMeta(identifier, identifier, "V1"),
            manufacturing_expenses=[ExpenseRecord("2026-07", "fixed", amount, "manufacturing")],
            activities=[ActivityRecord(
                "2026-07", manufacturing_input_cost=100.0,
                inventory_realization_rate=rate,
            )],
        )

    base = scenario("base", 1.0, 100.0)
    below = calculate_manufacturing_effects(base, scenario("below", 0.5, 80.0), _config())
    above = calculate_manufacturing_effects(base, scenario("above", 1.5, 80.0), _config())

    assert below.occurrence_total == above.occurrence_total == 20.0
    assert below.realized_total == above.realized_total == 20.0
    assert below.details[0]["final_profit_effect"] == 20.0
    assert above.details[0]["final_profit_effect"] == 20.0
