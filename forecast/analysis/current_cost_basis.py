from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .configuration import AnalysisConfig
from .manufacturing_effects import ManufacturingEffects
from .material_effects import MaterialEffects
from .schema import AnalysisScenario, CurrentCostComponentRecord


COMPONENT_ORDER = (
    "raw_material_production_issue",
    "raw_material_tariff_refund",
    "paid_supply",
    "labor",
    "manufacturing_expense",
)


@dataclass
class CurrentCostBasisAnalysis:
    current_manufacturing_cost_effect: float = 0.0
    raw_material_effect: float = 0.0
    manufacturing_activity_effect: float = 0.0
    manufacturing_unit_effect: float = 0.0
    manufacturing_fixed_effect: float = 0.0
    manufacturing_effect: float = 0.0
    existing_current_cost_driver_subtotal: float = 0.0
    basis_gap: float = 0.0
    raw_material_basis_gap: float = 0.0
    manufacturing_basis_gap: float = 0.0
    source_component_tie_difference: float = 0.0
    driver_component_tie_difference: float = 0.0
    unexplained_amount: float = 0.0
    status: str = "UNAVAILABLE"
    architecture_decision: str = "UNDETERMINED"
    architecture_rationale: str = ""
    component_details: list[dict[str, Any]] = field(default_factory=list)
    aggregate_details: list[dict[str, Any]] = field(default_factory=list)
    manufacturing_driver_details: list[dict[str, Any]] = field(default_factory=list)
    gap_classification: list[dict[str, Any]] = field(default_factory=list)
    residual: float | None = None
    residual_basis_gap_link: float | None = None
    residual_remainder: float | None = None
    plug_created: bool = False


def _component_map(
    scenario: AnalysisScenario,
) -> dict[str, list[CurrentCostComponentRecord]]:
    output: dict[str, list[CurrentCostComponentRecord]] = {}
    for row in scenario.current_cost_components:
        output.setdefault(row.component_code, []).append(row)
    return output


def _sum_amount(rows: list[CurrentCostComponentRecord]) -> float:
    return sum(row.amount for row in rows)


def _references(rows: list[CurrentCostComponentRecord]) -> str:
    return ", ".join(row.source_reference for row in rows)


def _formulas(rows: list[CurrentCostComponentRecord]) -> str:
    return " | ".join(
        f"{row.source_reference}: {row.source_formula or 'INPUT/BLANK=0'}"
        for row in rows
    )


def calculate_current_cost_basis_analysis(
    base: AnalysisScenario,
    comparison: AnalysisScenario,
    *,
    current_manufacturing_cost_effect: float,
    material: MaterialEffects,
    manufacturing: ManufacturingEffects,
    config: AnalysisConfig,
) -> CurrentCostBasisAnalysis:
    """Explain the row-325 direct-cost basis gap without creating an Effect.

    Existing business formulas remain authoritative.  The function only ties
    direct current-cost sources to their nearest canonical driver component and
    classifies the resulting scope/basis differences.
    """

    result = CurrentCostBasisAnalysis(
        current_manufacturing_cost_effect=current_manufacturing_cost_effect,
        raw_material_effect=material.total,
        manufacturing_activity_effect=(
            manufacturing.front_activity + manufacturing.back_activity
        ),
        manufacturing_unit_effect=(
            manufacturing.front_unit + manufacturing.back_unit
        ),
        manufacturing_fixed_effect=manufacturing.fixed_total,
        manufacturing_effect=manufacturing.occurrence_total,
    )
    result.existing_current_cost_driver_subtotal = (
        result.raw_material_effect + result.manufacturing_effect
    )
    result.basis_gap = (
        result.current_manufacturing_cost_effect
        - result.existing_current_cost_driver_subtotal
    )

    left = _component_map(base)
    right = _component_map(comparison)
    if not left or not right:
        result.status = "UNAVAILABLE"
        result.architecture_rationale = "CURRENT_COST_COMPONENT_SOURCE_MISSING"
        return result

    labor_effect = sum(
        float(item.get("occurrence_effect") or 0.0)
        for item in manufacturing.details
        if item.get("current_cost_component") == "labor"
    )
    manufacturing_expense_effect = sum(
        float(item.get("occurrence_effect") or 0.0)
        for item in manufacturing.details
        if item.get("current_cost_component") == "manufacturing_expense"
    )
    manufacturing_groups = (
        (
            "labor",
            lambda item: item.get("current_cost_component") == "labor",
            "노무비",
        ),
        (
            "outsourcing",
            lambda item: (
                item.get("current_cost_component") == "manufacturing_expense"
                and config.is_outsourcing(str(item.get("account") or ""))
            ),
            "외주가공비",
        ),
        (
            "other_manufacturing_expense",
            lambda item: (
                item.get("current_cost_component") == "manufacturing_expense"
                and not config.is_outsourcing(str(item.get("account") or ""))
            ),
            "기타 제조경비",
        ),
    )
    for code, predicate, business_source in manufacturing_groups:
        selected = [item for item in manufacturing.details if predicate(item)]
        base_amount = sum(float(item.get("baseline_amount") or 0.0) for item in selected)
        comparison_amount = sum(
            float(item.get("comparison_amount") or 0.0) for item in selected
        )
        direct_difference = base_amount - comparison_amount
        activity_effect = sum(
            float(item.get("activity_effect") or 0.0) for item in selected
        )
        unit_effect = sum(float(item.get("unit_effect") or 0.0) for item in selected)
        fixed_effect = sum(float(item.get("fixed_effect") or 0.0) for item in selected)
        existing_effect = sum(
            float(item.get("occurrence_effect") or 0.0) for item in selected
        )
        result.manufacturing_driver_details.append({
            "component_code": code,
            "business_source": business_source,
            "base": base_amount,
            "comparison": comparison_amount,
            "direct_difference": direct_difference,
            "activity_effect": activity_effect,
            "unit_effect": unit_effect,
            "fixed_effect": fixed_effect,
            "existing_effect": existing_effect,
            "gap": direct_difference - existing_effect,
            "source_coverage": "FULL",
            "reason": (
                "Canonical Activity + Unit Cost + Fixed occurrence decomposition "
                "equals the direct Base-minus-Comparison account amount."
            ),
        })
    existing_effects = {
        # The canonical material formula is an aggregate unit-cost driver that
        # uses production/output denominators and comparison sales basis.  It
        # is grouped with production-issue material for reconciliation, not
        # asserted as a one-to-one row-321 amount decomposition.
        "raw_material_production_issue": material.total,
        "raw_material_tariff_refund": 0.0,
        "paid_supply": 0.0,
        "labor": labor_effect,
        "manufacturing_expense": manufacturing_expense_effect,
    }
    reasons = {
        "raw_material_production_issue": (
            "Direct production-issue amount is compared with the aggregate canonical "
            "raw-material driver, which uses production/output unit cost and "
            "Comparison sales/applicable basis; the bases are intentionally different."
        ),
        "raw_material_tariff_refund": (
            "Golden current-cost adjustment is not mapped into the canonical raw-material "
            "driver and therefore remains an explicit source-scope difference."
        ),
        "paid_supply": (
            "Golden paid-supply current-cost adjustment has no direct dependency mapping "
            "to the canonical raw-material or manufacturing driver sources."
        ),
        "labor": (
            "Labor activity/unit/fixed decomposition is algebraically equal to the direct "
            "Base-minus-Comparison labor amount; realization rate is reference-only."
        ),
        "manufacturing_expense": (
            "Manufacturing activity/unit/fixed decomposition is algebraically equal to "
            "the direct Base-minus-Comparison expense amount; realization rate is reference-only."
        ),
    }
    formula_bases = {
        "raw_material_production_issue": (
            "(Base material cost/Base production - Comparison material cost/"
            "Comparison production) × Comparison sales basis"
        ),
        "raw_material_tariff_refund": "Excluded from canonical Raw Material driver",
        "paid_supply": "No direct canonical driver dependency from row-323 source",
        "labor": "Activity + Unit Cost + Fixed = Base amount - Comparison amount",
        "manufacturing_expense": (
            "Activity + Unit Cost + Fixed = Base amount - Comparison amount"
        ),
    }

    for code in COMPONENT_ORDER:
        base_rows = left.get(code, [])
        comparison_rows = right.get(code, [])
        base_amount = _sum_amount(base_rows)
        comparison_amount = _sum_amount(comparison_rows)
        direct_difference = base_amount - comparison_amount
        existing_effect = existing_effects[code]
        gap = direct_difference - existing_effect
        statuses = {
            row.source_validation_status for row in (*base_rows, *comparison_rows)
        }
        validation_status = "PASS" if statuses == {"PASS"} else "CHECK_SOURCE"
        if code in {"labor", "manufacturing_expense"}:
            source_coverage = "FULL"
        elif code in {"raw_material_tariff_refund", "paid_supply"}:
            source_coverage = "FULL_DIRECT_SOURCE_EXCLUDED_FROM_DRIVER"
        else:
            source_coverage = "AGGREGATE_DRIVER_ONLY"
        tolerance = max(
            config.absolute_tolerance,
            abs(direct_difference) * config.relative_tolerance,
        )
        component_status = (
            validation_status
            if validation_status != "PASS"
            else "PASS" if abs(gap) <= tolerance else "CHECK_SCOPE_GAP"
        )
        sample = (base_rows or comparison_rows)[0]
        result.component_details.append({
            "component_code": code,
            "business_source": sample.business_source,
            "category": sample.category,
            "base": base_amount,
            "comparison": comparison_amount,
            "direct_difference": direct_difference,
            "existing_effect": existing_effect,
            "gap": gap,
            "reason": reasons[code],
            "formula_basis": formula_bases[code],
            "source_coverage": source_coverage,
            "validation_status": component_status,
            "base_source_reference": _references(base_rows),
            "comparison_source_reference": _references(comparison_rows),
            "base_source_formula": _formulas(base_rows),
            "comparison_source_formula": _formulas(comparison_rows),
        })

    details = {row["component_code"]: row for row in result.component_details}
    raw_codes = (
        "raw_material_production_issue",
        "raw_material_tariff_refund",
        "paid_supply",
    )
    manufacturing_codes = ("labor", "manufacturing_expense")

    def aggregate(code: str, business_source: str, members: tuple[str, ...]) -> dict[str, Any]:
        return {
            "component_code": code,
            "business_source": business_source,
            "base": sum(details[item]["base"] for item in members),
            "comparison": sum(details[item]["comparison"] for item in members),
            "direct_difference": sum(
                details[item]["direct_difference"] for item in members
            ),
            "existing_effect": sum(details[item]["existing_effect"] for item in members),
            "gap": sum(details[item]["gap"] for item in members),
        }

    raw = aggregate("raw_material_total", "원재료비 계", raw_codes)
    manufacturing_total = aggregate(
        "manufacturing_processing_total", "제조 가공비 합계", manufacturing_codes
    )
    total = aggregate(
        "current_manufacturing_cost",
        "당기투입제조원가",
        (*raw_codes, *manufacturing_codes),
    )
    result.aggregate_details = [raw, manufacturing_total, total]
    result.raw_material_basis_gap = raw["gap"]
    result.manufacturing_basis_gap = manufacturing_total["gap"]
    result.source_component_tie_difference = (
        result.current_manufacturing_cost_effect - total["direct_difference"]
    )
    result.driver_component_tie_difference = (
        result.existing_current_cost_driver_subtotal - total["existing_effect"]
    )

    result.gap_classification = [
        {
            "classification": "formula_scope_difference",
            "business_source": "원부재료비(생산출고) vs Canonical Raw Material driver",
            "amount": details["raw_material_production_issue"]["gap"],
            "source_coverage": "AGGREGATE_DRIVER_ONLY",
            "reason": reasons["raw_material_production_issue"],
        },
        {
            "classification": "excluded_current_cost_adjustment",
            "business_source": "원재료 관세환급액",
            "amount": details["raw_material_tariff_refund"]["gap"],
            "source_coverage": "FULL_DIRECT_SOURCE_EXCLUDED_FROM_DRIVER",
            "reason": reasons["raw_material_tariff_refund"],
        },
        {
            "classification": "source_scope_difference",
            "business_source": "유상사급",
            "amount": details["paid_supply"]["gap"],
            "source_coverage": "FULL_DIRECT_SOURCE_EXCLUDED_FROM_DRIVER",
            "reason": reasons["paid_supply"],
        },
        {
            "classification": "manufacturing_driver_decomposition",
            "business_source": "노무비 + 제조경비",
            "amount": result.manufacturing_basis_gap,
            "source_coverage": "FULL",
            "reason": (
                "Manufacturing direct difference and Activity + Unit Cost + Fixed "
                "decomposition reconcile exactly."
            ),
        },
    ]
    classified = sum(float(row["amount"]) for row in result.gap_classification)
    result.unexplained_amount = result.basis_gap - classified
    classification_tolerance = max(
        config.absolute_tolerance,
        abs(result.current_manufacturing_cost_effect) * config.relative_tolerance,
    )
    if abs(result.unexplained_amount) <= classification_tolerance:
        result.unexplained_amount = 0.0
    result.gap_classification.append({
        "classification": "UNEXPLAINED",
        "business_source": "Unmapped remainder",
        "amount": result.unexplained_amount,
        "source_coverage": (
            "NONE" if result.unexplained_amount else "NOT_APPLICABLE"
        ),
        "reason": "Only the amount not tied by source and driver checks remains unexplained.",
    })

    tolerance = classification_tolerance
    if abs(result.basis_gap) <= tolerance:
        result.architecture_decision = "OPTION_A"
        result.architecture_rationale = "Existing drivers fully decompose current cost."
    elif abs(result.manufacturing_basis_gap) <= tolerance:
        result.architecture_decision = "OPTION_C"
        result.architecture_rationale = (
            "Manufacturing drivers directly reconcile, while raw-material direct sources "
            "and the canonical sales/production driver use structurally different bases."
        )
    else:
        result.architecture_decision = "OPTION_B"
        result.architecture_rationale = (
            "Both raw-material and manufacturing driver concepts differ from direct current cost."
        )
    if (
        abs(result.source_component_tie_difference) > tolerance
        or abs(result.driver_component_tie_difference) > tolerance
        or abs(result.unexplained_amount) > tolerance
    ):
        result.status = "UNEXPLAINED"
    elif abs(result.basis_gap) > tolerance:
        result.status = "CHECK_SCOPE_GAP"
    else:
        result.status = "PASS"
    return result
