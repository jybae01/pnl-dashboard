from __future__ import annotations

from dataclasses import asdict
import json

import pytest

from forecast.analysis.configuration import AnalysisConfig
from forecast.analysis.manufacturing_effects import calculate_manufacturing_effects
from forecast.analysis.production_evidence import (
    WEIGHTED_FORMULA_POLICY,
    calculate_production_evidence,
)
from forecast.analysis.schema import (
    ActivityRecord,
    AnalysisScenario,
    ExpenseRecord,
    ProductRecord,
    ProductionEvidenceRecord,
    ScenarioMeta,
)


ROWS = {
    "FS": ((532,), (533,), "LENGTH", "전공정", "FS"),
    "SW": ((1026, 1051), (1027, 1052), "PCS", "후공정", "SW400 + SW440"),
    "BW": ((1076, 1101), (1077, 1102), "PCS", "후공정", "BW400 + BW440"),
    "LC": ((1126,), (1127,), "PCS", "후공정", "LC"),
}


def _record(month: str, group: str, quantity: float, amount: float) -> ProductionEvidenceRecord:
    quantity_rows, amount_rows, unit, process, aggregation = ROWS[group]
    column = {"2026-07": "K", "2026-08": "L"}.get(month, "M")
    return ProductionEvidenceRecord(
        year_month=month,
        product_group=group,
        process=process,
        unit_basis=unit,
        quantity=quantity,
        amount=amount,
        quantity_source=" + ".join(f"Data!{column}{row}" for row in quantity_rows),
        amount_source=" + ".join(f"Data!{column}{row}" for row in amount_rows),
        quantity_source_rows=quantity_rows,
        amount_source_rows=amount_rows,
        aggregation_basis=aggregation,
        formula_policy=WEIGHTED_FORMULA_POLICY,
    )


def _scenario(side: str, values: dict[str, list[tuple[str, float, float]]]) -> AnalysisScenario:
    return AnalysisScenario(
        meta=ScenarioMeta(side, side, "1"),
        production_evidence=[
            _record(month, group, quantity, amount)
            for group, monthly in values.items()
            for month, quantity, amount in monthly
        ],
    )


def _values(multiplier: float = 1.0) -> dict[str, list[tuple[str, float, float]]]:
    return {
        "FS": [("2026-07", 10, 1_000 * multiplier), ("2026-08", 30, 6_000 * multiplier)],
        "SW": [("2026-07", 4, 400 * multiplier), ("2026-08", 16, 3_200 * multiplier)],
        "BW": [("2026-07", 5, 750 * multiplier), ("2026-08", 15, 3_750 * multiplier)],
        "LC": [("2026-07", 2, 400 * multiplier), ("2026-08", 8, 2_400 * multiplier)],
    }


def test_source_map_has_exact_inventory_ledger_row_authority():
    mapping = json.loads(
        open("config/analysis_production_evidence_sources.json", encoding="utf-8").read()
    )
    groups = mapping["groups"]
    assert groups["FS"]["quantity_rows"] == [532]
    assert groups["FS"]["amount_rows"] == [533]
    assert groups["SW"]["quantity_rows"] == [1026, 1051]
    assert groups["SW"]["amount_rows"] == [1027, 1052]
    assert groups["BW"]["quantity_rows"] == [1076, 1101]
    assert groups["BW"]["amount_rows"] == [1077, 1102]
    assert groups["LC"]["quantity_rows"] == [1126]
    assert groups["LC"]["amount_rows"] == [1127]
    assert mapping["mapping_version"] == "analysis-production-evidence-v1.0.0"


def test_selected_period_uses_total_amount_over_total_quantity_not_monthly_mean():
    rows = calculate_production_evidence(
        _scenario("base", _values()),
        _scenario("comparison", _values(1.2)),
    )
    by_group = {row["production_basis"]: row for row in rows}

    assert by_group["FS"]["baseline_weighted_unit_cost"] == 7_000 / 40
    assert by_group["FS"]["baseline_weighted_unit_cost"] != (100 + 200) / 2
    assert by_group["SW"]["baseline_quantity"] == 20
    assert by_group["SW"]["baseline_amount"] == 3_600
    assert by_group["SW"]["baseline_weighted_unit_cost"] == 180
    assert by_group["BW"]["baseline_weighted_unit_cost"] == 4_500 / 20
    assert by_group["LC"]["baseline_weighted_unit_cost"] == 2_800 / 10
    assert by_group["SW"]["comparison_weighted_unit_cost"] == pytest.approx(216)
    assert by_group["SW"]["unit_cost_delta"] == pytest.approx(36)
    assert by_group["SW"]["selected_period"] == ["2026-07", "2026-08"]
    assert by_group["SW"]["baseline_quantity_sources"] == [
        "Data!K1026", "Data!K1051", "Data!L1026", "Data!L1051",
    ]
    assert by_group["SW"]["baseline_amount_sources"] == [
        "Data!K1027", "Data!K1052", "Data!L1027", "Data!L1052",
    ]


def test_zero_quantity_returns_null_unit_cost_without_divide_by_zero():
    values = _values()
    values["LC"] = [("2026-07", 0, 0), ("2026-08", 0, 0)]
    comparison = _values()
    comparison["LC"] = [("2026-07", 0, 50), ("2026-08", 0, 50)]

    lc = next(
        row for row in calculate_production_evidence(
            _scenario("base", values), _scenario("comparison", comparison)
        )
        if row["production_basis"] == "LC"
    )

    assert lc["baseline_weighted_unit_cost"] is None
    assert lc["comparison_weighted_unit_cost"] is None
    assert lc["unit_cost_delta"] is None


def test_units_and_back_total_never_mix_length_into_pcs_denominator():
    rows = calculate_production_evidence(
        _scenario("base", _values()), _scenario("comparison", _values(1.2))
    )
    by_group = {row["production_basis"]: row for row in rows}

    assert (by_group["FS"]["unit"], by_group["FS"]["unit_cost_unit"]) == ("m", "원/m")
    for group in ("SW", "BW", "LC", "SW+BW+LC"):
        assert (by_group[group]["unit"], by_group[group]["unit_cost_unit"]) == ("PCS", "원/PCS")
    back = by_group["SW+BW+LC"]
    assert back["baseline_quantity"] == 50
    assert back["baseline_amount"] == 10_900
    assert back["baseline_weighted_unit_cost"] == 10_900 / 50
    assert back["baseline_quantity"] != 90  # excludes the 40 m FS denominator


def test_evidence_records_do_not_change_manufacturing_effect_identity():
    config = AnalysisConfig.load("config/analysis_v1.json")

    def scenario(side: str, evidence: bool) -> AnalysisScenario:
        return AnalysisScenario(
            meta=ScenarioMeta(side, side, "1"),
            products=[
                ProductRecord("2026-07", "FS", "FS", unit_basis="LENGTH", sap_production_length=100),
                ProductRecord("2026-07", "SW", "SW", sap_production_qty=50),
            ],
            manufacturing_expenses=[
                ExpenseRecord("2026-07", "수도광열비", 100 if side == "base" else 120, "manufacturing", front_ratio=0.5, back_ratio=0.5),
            ],
            activities=[ActivityRecord("2026-07")],
            production_evidence=(
                _scenario(side, _values()).production_evidence if evidence else []
            ),
        )

    without = calculate_manufacturing_effects(
        scenario("base", False), scenario("comparison", False), config
    )
    with_evidence = calculate_manufacturing_effects(
        scenario("base", True), scenario("comparison", True), config
    )

    assert asdict(without) == asdict(with_evidence)
