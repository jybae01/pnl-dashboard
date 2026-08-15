from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from .configuration import AnalysisConfig
from .core_cogs_overlap import CoreManufacturedCogsOverlap
from .schema import AnalysisScenario, InventoryCostRecord, OpeningInventoryUnitRecord


PERSISTENCE_CONSISTENT = "CONSISTENT"
PERSISTENCE_EMERGING = "EMERGING"
PERSISTENCE_MIXED = "MIXED"
PERSISTENCE_REVERSAL = "REVERSAL"
PERSISTENCE_INSUFFICIENT = "INSUFFICIENT_HISTORY"


def _number(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


@dataclass
class InventoryTimingEffects:
    base_manufactured_cogs: float = 0.0
    comparison_manufactured_cogs: float = 0.0
    manufactured_cogs_effect: float = 0.0
    base_current_manufacturing_cost: float = 0.0
    comparison_current_manufacturing_cost: float = 0.0
    current_manufacturing_cost_effect: float = 0.0
    gross_inventory_timing_effect: float = 0.0
    core_cogs_quantity_overlap_effect: float = 0.0
    core_cogs_mix_overlap_effect: float = 0.0
    core_manufactured_cogs_overlap_effect: float = 0.0
    inventory_timing_effect: float = 0.0
    core_overlap_policy_status: str = "NOT_APPLIED"
    core_overlap_source_validation_status: str = "UNVALIDATED"
    core_overlap_pool_validation_status: str = "UNVALIDATED"
    current_cost_related_effects: float = 0.0
    current_cost_explanation_gap: float = 0.0
    additive_bridge_status: str = "UNVALIDATED"
    source_validation_status: str = "UNVALIDATED"
    scope_validation_status: str = "UNVALIDATED"
    source_coverage: str = "NONE"
    product_unit_coverage: str = "LIMITED"
    materiality_status: str = "UNCONFIGURED"
    persistence: str = PERSISTENCE_INSUFFICIENT
    primary: str = "NO_PRIMARY"
    supporting: list[str] = field(default_factory=list)
    reference: list[str] = field(default_factory=list)
    confidence: str = "LOW"
    explanation_rule: str = ""
    fallback_narrative: str = (
        "재고·원가 반영시차 영향은 확인되나 현재 Source만으로 단일 원인을 특정하기 어려움"
    )
    monthly_details: list[dict[str, Any]] = field(default_factory=list)
    opening_inventory_units: list[dict[str, Any]] = field(default_factory=list)
    source_details: list[dict[str, Any]] = field(default_factory=list)
    core_overlap_details: list[dict[str, Any]] = field(default_factory=list)
    core_overlap_excluded_sources: list[str] = field(default_factory=list)
    scope_notes: list[str] = field(default_factory=list)


def _direction(value: float, tolerance: float = 1.0) -> str:
    if value > tolerance:
        return "IMPROVEMENT"
    if value < -tolerance:
        return "DETERIORATION"
    return "NEUTRAL"


def classify_persistence(
    monthly_effects: Iterable[float],
    *,
    latest_material: bool | None,
) -> str:
    values = tuple(float(value) for value in monthly_effects)
    if len(values) < 3:
        return PERSISTENCE_INSUFFICIENT
    directions = tuple(_direction(value) for value in values[-3:])
    first, second, latest = directions
    if first == second != "NEUTRAL" and latest not in {first, "NEUTRAL"}:
        return PERSISTENCE_REVERSAL
    if first == second == latest and latest != "NEUTRAL":
        return PERSISTENCE_CONSISTENT
    if second == latest != "NEUTRAL" and latest_material is True:
        return PERSISTENCE_EMERGING
    return PERSISTENCE_MIXED


def _materiality(
    effect: float,
    operating_profit_delta: float,
    config: AnalysisConfig,
) -> tuple[str, bool | None]:
    absolute = config.inventory_materiality_absolute
    relative = config.inventory_materiality_op_delta_ratio
    if absolute is None and relative is None:
        return "UNCONFIGURED", None
    absolute_pass = absolute is not None and abs(effect) >= absolute
    relative_pass = (
        relative is not None
        and abs(operating_profit_delta) > config.absolute_tolerance
        and abs(effect) / abs(operating_profit_delta) >= relative
    )
    material = absolute_pass or relative_pass
    return ("MATERIAL" if material else "NOT_MATERIAL"), material


def _unique_costs(rows: Iterable[InventoryCostRecord]) -> dict[str, InventoryCostRecord]:
    output: dict[str, InventoryCostRecord] = {}
    for row in rows:
        if row.year_month in output:
            raise ValueError(f"duplicate inventory cost record: {row.year_month}")
        output[row.year_month] = row
    return output


def _unit_map(
    rows: Iterable[OpeningInventoryUnitRecord],
) -> dict[tuple[str, str], OpeningInventoryUnitRecord]:
    output: dict[tuple[str, str], OpeningInventoryUnitRecord] = {}
    for row in rows:
        key = (row.year_month, row.product_group)
        if key in output:
            raise ValueError(f"duplicate opening inventory unit record: {key}")
        output[key] = row
    return output


def calculate_inventory_timing_effects(
    base: AnalysisScenario,
    comparison: AnalysisScenario,
    selected_months: Iterable[str],
    config: AnalysisConfig,
    *,
    operating_profit_delta: float,
    current_cost_related_effects: float,
    core_cogs_overlap: CoreManufacturedCogsOverlap | None = None,
) -> InventoryTimingEffects:
    selected = tuple(sorted(set(selected_months)))
    if not selected:
        raise ValueError("inventory timing requires at least one selected month")
    left = _unique_costs(base.inventory_costs)
    right = _unique_costs(comparison.inventory_costs)
    common = tuple(sorted(set(left) & set(right)))
    if not set(selected).issubset(common):
        raise ValueError("inventory timing source is missing for a selected month")

    result = InventoryTimingEffects()
    selected_left = [left[month] for month in selected]
    selected_right = [right[month] for month in selected]
    result.base_manufactured_cogs = sum(row.manufactured_cogs for row in selected_left)
    result.comparison_manufactured_cogs = sum(row.manufactured_cogs for row in selected_right)
    result.manufactured_cogs_effect = (
        result.base_manufactured_cogs - result.comparison_manufactured_cogs
    )
    result.base_current_manufacturing_cost = sum(
        row.current_manufacturing_cost for row in selected_left
    )
    result.comparison_current_manufacturing_cost = sum(
        row.current_manufacturing_cost for row in selected_right
    )
    result.current_manufacturing_cost_effect = (
        result.base_current_manufacturing_cost
        - result.comparison_current_manufacturing_cost
    )
    result.gross_inventory_timing_effect = (
        result.manufactured_cogs_effect - result.current_manufacturing_cost_effect
    )
    if core_cogs_overlap is not None:
        if (
            core_cogs_overlap.source_validation_status != "PASS"
            or core_cogs_overlap.pool_validation_status != "PASS"
            or core_cogs_overlap.policy_status != "APPLIED_CORE_ONLY"
        ):
            raise ValueError("core manufactured COGS overlap validation failed")
        result.core_cogs_quantity_overlap_effect = (
            core_cogs_overlap.quantity_overlap_effect
        )
        result.core_cogs_mix_overlap_effect = core_cogs_overlap.mix_overlap_effect
        result.core_manufactured_cogs_overlap_effect = (
            core_cogs_overlap.total_overlap_effect
        )
        result.core_overlap_policy_status = core_cogs_overlap.policy_status
        result.core_overlap_source_validation_status = (
            core_cogs_overlap.source_validation_status
        )
        result.core_overlap_pool_validation_status = (
            core_cogs_overlap.pool_validation_status
        )
        result.core_overlap_details = list(core_cogs_overlap.details)
        result.core_overlap_excluded_sources = list(
            core_cogs_overlap.excluded_sources
        )
    result.inventory_timing_effect = (
        result.gross_inventory_timing_effect
        - result.core_manufactured_cogs_overlap_effect
    )
    result.current_cost_related_effects = float(current_cost_related_effects)
    result.current_cost_explanation_gap = (
        result.current_manufacturing_cost_effect - result.current_cost_related_effects
    )
    tolerance = max(
        config.absolute_tolerance,
        abs(result.current_manufacturing_cost_effect) * config.relative_tolerance,
    )
    result.additive_bridge_status = (
        "PASS"
        if abs(result.current_cost_explanation_gap) <= tolerance
        else "CHECK_CURRENT_COST_SCOPE_GAP"
    )

    source_statuses = {
        row.source_validation_status for row in (*selected_left, *selected_right)
    }
    scope_statuses = {
        row.scope_validation_status for row in (*selected_left, *selected_right)
    }
    result.source_validation_status = (
        "PASS" if source_statuses == {"PASS"} else "FAIL"
    )
    result.scope_validation_status = (
        "PASS" if scope_statuses == {"PASS"} else "FAIL"
    )
    result.source_coverage = (
        "FULL" if result.source_validation_status == "PASS" else "NONE"
    )
    result.scope_notes = sorted({
        note for row in (*selected_left, *selected_right) for note in row.scope_notes
    })
    for side, rows in (("BASE", selected_left), ("COMPARISON", selected_right)):
        for row in rows:
            result.source_details.extend([
                {
                    "side": side,
                    "period": row.year_month,
                    "business_source": "당기투입제조원가",
                    "canonical_field": "current_manufacturing_cost",
                    "unit": "KRW",
                    "source_reference": row.current_manufacturing_cost_source,
                    "value": row.current_manufacturing_cost,
                    "validation_status": row.source_validation_status,
                },
                {
                    "side": side,
                    "period": row.year_month,
                    "business_source": "제품 매출원가",
                    "canonical_field": "finished_goods_cogs",
                    "unit": "KRW",
                    "source_reference": row.finished_goods_cogs_source,
                    "value": row.finished_goods_cogs,
                    "validation_status": row.source_validation_status,
                },
                {
                    "side": side,
                    "period": row.year_month,
                    "business_source": "반제품 매출원가",
                    "canonical_field": "semi_finished_goods_cogs",
                    "unit": "KRW",
                    "source_reference": row.semi_finished_goods_cogs_source,
                    "value": row.semi_finished_goods_cogs,
                    "validation_status": row.source_validation_status,
                },
            ])

    latest_selected = selected[-1]
    history_months = tuple(month for month in common if month <= latest_selected)[-3:]
    overlap_by_month = {
        str(row.get("period")): row
        for row in (core_cogs_overlap.monthly_details if core_cogs_overlap else [])
    }
    for month in history_months:
        manufactured_effect = left[month].manufactured_cogs - right[month].manufactured_cogs
        current_effect = (
            left[month].current_manufacturing_cost
            - right[month].current_manufacturing_cost
        )
        gross_timing = manufactured_effect - current_effect
        overlap = _number(overlap_by_month.get(month, {}).get("total_overlap_effect"))
        quantity_overlap = _number(
            overlap_by_month.get(month, {}).get("quantity_overlap_effect")
        )
        mix_overlap = _number(
            overlap_by_month.get(month, {}).get("mix_overlap_effect")
        )
        timing = gross_timing - overlap
        result.monthly_details.append({
            "period": month,
            "base_manufactured_cogs": left[month].manufactured_cogs,
            "comparison_manufactured_cogs": right[month].manufactured_cogs,
            "manufactured_cogs_effect": manufactured_effect,
            "base_current_manufacturing_cost": left[month].current_manufacturing_cost,
            "comparison_current_manufacturing_cost": right[month].current_manufacturing_cost,
            "current_manufacturing_cost_effect": current_effect,
            "gross_inventory_timing_effect": gross_timing,
            "core_cogs_quantity_overlap_effect": quantity_overlap,
            "core_cogs_mix_overlap_effect": mix_overlap,
            "core_manufactured_cogs_overlap_effect": overlap,
            "inventory_timing_effect": timing,
            "direction": _direction(timing),
            "source_reference": (
                "Base: "
                f"{left[month].finished_goods_cogs_source}, "
                f"{left[month].semi_finished_goods_cogs_source}, "
                f"{left[month].current_manufacturing_cost_source} / Comparison: "
                f"{right[month].finished_goods_cogs_source}, "
                f"{right[month].semi_finished_goods_cogs_source}, "
                f"{right[month].current_manufacturing_cost_source}"
            ),
        })

    result.materiality_status, latest_material = _materiality(
        result.inventory_timing_effect, operating_profit_delta, config
    )
    result.persistence = classify_persistence(
        (row["inventory_timing_effect"] for row in result.monthly_details),
        latest_material=latest_material,
    )

    left_units = _unit_map(base.opening_inventory_units)
    right_units = _unit_map(comparison.opening_inventory_units)
    official_direction = _direction(
        result.monthly_details[-1]["inventory_timing_effect"]
        if result.monthly_details else result.inventory_timing_effect
    )
    aligned_groups: list[str] = []
    for product_group in ("FS", "SW", "BW", "LC"):
        lrow = left_units.get((latest_selected, product_group))
        rrow = right_units.get((latest_selected, product_group))
        if lrow is None or rrow is None:
            result.reference.append(f"{product_group}: SOURCE_MISSING")
            continue
        delta = (
            None
            if lrow.unit_cost is None or rrow.unit_cost is None
            else rrow.unit_cost - lrow.unit_cost
        )
        evidence_direction = (
            "UNKNOWN" if delta is None else _direction(-delta)
        )
        aligned = (
            official_direction not in {"NEUTRAL", "UNKNOWN"}
            and evidence_direction == official_direction
        )
        if aligned:
            aligned_groups.append(product_group)
            result.supporting.append(f"{product_group} 기초재고 단가 방향 일치")
        else:
            result.reference.append(f"{product_group} 기초재고 단가")
        result.opening_inventory_units.append({
            "product_group": product_group,
            "period": latest_selected,
            "unit_basis": lrow.unit_basis,
            "specification": lrow.specification,
            "base_quantity": lrow.quantity,
            "comparison_quantity": rrow.quantity,
            "base_unit_cost": lrow.unit_cost,
            "comparison_unit_cost": rrow.unit_cost,
            "unit_cost_delta": delta,
            "evidence_direction": evidence_direction,
            "official_direction": official_direction,
            "direction_aligned": aligned,
            "coverage": "LIMITED",
            "base_source_reference": (
                f"{lrow.amount_source} / {lrow.quantity_source}"
            ),
            "comparison_source_reference": (
                f"{rrow.amount_source} / {rrow.quantity_source}"
            ),
        })

    if result.persistence != PERSISTENCE_INSUFFICIENT:
        result.supporting.append(f"Rolling 3M {result.persistence}")
    else:
        result.reference.append("Rolling 3M INSUFFICIENT_HISTORY")

    primary_allowed = all((
        result.source_validation_status == "PASS",
        result.scope_validation_status == "PASS",
        result.product_unit_coverage != "LIMITED",
        result.materiality_status == "MATERIAL",
        result.persistence in {PERSISTENCE_CONSISTENT, PERSISTENCE_EMERGING},
        len(aligned_groups) == 4,
    ))
    if primary_allowed:
        result.primary = "OPENING_INVENTORY_UNIT_COST"
        result.confidence = "HIGH"
        result.explanation_rule = "RULE_PRIMARY_FULL_COVERAGE_DIRECTION_PERSISTENCE_MATERIAL"
    else:
        result.primary = "NO_PRIMARY"
        result.confidence = (
            "MEDIUM"
            if result.source_validation_status == result.scope_validation_status == "PASS"
            and result.materiality_status != "UNCONFIGURED"
            and result.persistence != PERSISTENCE_INSUFFICIENT
            else "LOW"
        )
        reasons = []
        if result.source_validation_status != "PASS":
            reasons.append("SOURCE_VALIDATION_FAIL")
        if result.scope_validation_status != "PASS":
            reasons.append("SCOPE_VALIDATION_FAIL")
        if result.product_unit_coverage == "LIMITED":
            reasons.append("LIMITED_COVERAGE")
        if result.materiality_status != "MATERIAL":
            reasons.append(f"MATERIALITY_{result.materiality_status}")
        if result.persistence == PERSISTENCE_INSUFFICIENT:
            reasons.append(PERSISTENCE_INSUFFICIENT)
        if len(aligned_groups) < 4:
            reasons.append("DIRECTION_EVIDENCE_INCOMPLETE")
        result.explanation_rule = "RULE_NO_PRIMARY:" + ",".join(reasons)
    return result
