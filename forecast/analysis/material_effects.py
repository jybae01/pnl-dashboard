from __future__ import annotations

from dataclasses import dataclass, field

from .schema import AnalysisScenario, ProductRecord


@dataclass
class MaterialEffects:
    """Raw-material effects in operating-profit sign convention."""

    total: float = 0.0
    nonwoven_price_ex_fx: float = 0.0
    nonwoven_jpy: float = 0.0
    materials_ex_nonwoven: float = 0.0
    # Backward-compatible fields. MCM is not calculated as an identifiable effect.
    mcm_paid_supply: float = 0.0
    other_unit_mix: float = 0.0
    unit_excluding_jpy: float = 0.0
    by_product_group: dict[str, float] = field(default_factory=dict)
    by_product_group_details: dict[str, dict[str, float]] = field(default_factory=dict)
    mcm_by_product_group: dict[str, float] = field(default_factory=dict)
    issues: list[str] = field(default_factory=list)
    details: list[dict[str, float | str]] = field(default_factory=list)
    nonwoven_details: list[dict[str, float | str]] = field(default_factory=list)

    @property
    def detail_reconciliation_difference(self) -> float:
        return self.total - (
            self.nonwoven_price_ex_fx + self.nonwoven_jpy + self.materials_ex_nonwoven
        )


def _group_rows(scenario: AnalysisScenario, month: str, group: str) -> list[ProductRecord]:
    return [
        row for row in scenario.products
        if row.year_month == month
        and row.product_group == group
        and row.material_applicable_flag
    ]


def calculate_material_effects(base: AnalysisScenario, comparison: AnalysisScenario) -> MaterialEffects:
    result = MaterialEffects()
    months = sorted(set(base.months) & set(comparison.months))
    for month in months:
        groups = sorted(
            {row.product_group for row in base.products if row.year_month == month and row.material_applicable_flag}
            | {row.product_group for row in comparison.products if row.year_month == month and row.material_applicable_flag}
            | {row.mcm_product_group for row in base.products if row.year_month == month and row.mcm_product_group}
            | {row.mcm_product_group for row in comparison.products if row.year_month == month and row.mcm_product_group}
        )
        for group in groups:
            left = _group_rows(base, month, group)
            right = _group_rows(comparison, month, group)
            base_output = sum(row.production_basis for row in left)
            comp_output = sum(row.production_basis for row in right)
            base_cost = sum(row.raw_material_cost for row in left)
            comp_cost = sum(row.raw_material_cost for row in right)
            comparison_sales = sum(row.sales_basis for row in right)
            invalid_denominator = (
                (base_cost and not base_output)
                or (comp_cost and not comp_output)
                or (comparison_sales and (not base_output or not comp_output))
            )
            base_unit = base_cost / base_output if base_output else 0.0
            comp_unit = comp_cost / comp_output if comp_output else 0.0
            # A zero production denominator must never be converted into a
            # plausible-looking unit cost. Keep the contribution neutral and
            # surface the exception through issues/calculation_status instead.
            effect = 0.0 if invalid_denominator else (base_unit - comp_unit) * comparison_sales
            result.total += effect
            result.by_product_group[group] = result.by_product_group.get(group, 0.0) + effect
            detail = result.by_product_group_details.setdefault(group, {
                "baseline_cost": 0.0,
                "comparison_cost": 0.0,
                "baseline_output": 0.0,
                "comparison_output": 0.0,
                "comparison_sales": 0.0,
                "total": 0.0,
                "nonwoven_price_ex_fx": 0.0,
                "nonwoven_jpy": 0.0,
                "materials_ex_nonwoven": 0.0,
                "calculation_errors": 0.0,
            })
            detail["baseline_cost"] += base_cost
            detail["comparison_cost"] += comp_cost
            detail["baseline_output"] += base_output
            detail["comparison_output"] += comp_output
            detail["comparison_sales"] += comparison_sales
            detail["total"] += effect
            if invalid_denominator:
                detail["calculation_errors"] += 1.0
                result.issues.append(f"{month} {group}: 원부재료 생산출고 분모가 0임")
            result.details.append({
                "period": month,
                "product_group": group,
                "unit": "m" if (right or left) and (right or left)[0].unit_basis.upper() == "LENGTH" else "PCS",
                "base_cost": base_cost,
                "comparison_cost": comp_cost,
                "base_output": base_output,
                "comparison_output": comp_output,
                "comparison_sales": comparison_sales,
                "base_unit_cost": base_unit,
                "comparison_unit_cost": comp_unit,
                "total_effect": effect,
                "business_source": "제품군 원부재료 생산출고 금액·생산량·판매 적용량",
                "canonical_fields": "raw_material_cost / production_basis / sales_basis",
                "base_source_reference": " | ".join(sorted({
                    value for row in left for value in (
                        row.raw_material_cost_source, row.production_source,
                        row.sales_quantity_source,
                    ) if value
                })),
                "comparison_source_reference": " | ".join(sorted({
                    value for row in right for value in (
                        row.raw_material_cost_source, row.production_source,
                        row.sales_quantity_source,
                    ) if value
                })),
                "validation_status": "CHECK_DENOMINATOR" if invalid_denominator else "PASS",
                "source_validation_status": (
                    "SOURCE_MAPPED"
                    if all(
                        row.source_validation_status in {"PASS", "SOURCE_MAPPED"}
                        for row in (*left, *right)
                    )
                    else "UNVALIDATED"
                ),
            })

        left = [row for row in base.products if row.year_month == month]
        right = [row for row in comparison.products if row.year_month == month]
        base_nonwoven_cost = sum(row.nonwoven_cost for row in left)
        comparison_nonwoven_cost = sum(row.nonwoven_cost for row in right)
        base_nonwoven_output = sum(
            row.nonwoven_output_length
            if row.nonwoven_output_length is not None else row.sap_length
            for row in left
        )
        comparison_nonwoven_output = sum(
            row.nonwoven_output_length
            if row.nonwoven_output_length is not None else row.sap_length
            for row in right
        )
        comparison_input_length = sum(row.nonwoven_sales_input_length for row in right)
        base_jpy = next((row.effective_jpy_fx for row in left if row.effective_jpy_fx), 0.0)
        comp_jpy = next((row.effective_jpy_fx for row in right if row.effective_jpy_fx), 0.0)
        if base_nonwoven_cost or comparison_nonwoven_cost or comparison_input_length:
            base_nonwoven_unit = base_nonwoven_cost / base_nonwoven_output if base_nonwoven_output else 0.0
            comparison_nonwoven_unit = (
                comparison_nonwoven_cost / comparison_nonwoven_output
                if comparison_nonwoven_output else 0.0
            )
            nonwoven_total = (
                (base_nonwoven_unit - comparison_nonwoven_unit) * comparison_input_length
            )
            if base_nonwoven_output and base_jpy:
                # FX is KRW/JPY. Do not convert to KRW/100JPY.
                base_jpy_unit = (base_nonwoven_cost / base_nonwoven_output) / base_jpy
                jpy_effect = comparison_input_length * base_jpy_unit * (base_jpy - comp_jpy)
                result.nonwoven_jpy += jpy_effect
                result.nonwoven_price_ex_fx += nonwoven_total - jpy_effect
                for group in groups:
                    group_input = sum(
                        row.nonwoven_sales_input_length
                        for row in right if row.product_group == group
                    )
                    if not group_input:
                        continue
                    group_jpy = group_input * base_jpy_unit * (base_jpy - comp_jpy)
                    group_total = (
                        (base_nonwoven_unit - comparison_nonwoven_unit) * group_input
                    )
                    detail = result.by_product_group_details.setdefault(group, {
                        "baseline_cost": 0.0,
                        "comparison_cost": 0.0,
                        "baseline_output": 0.0,
                        "comparison_output": 0.0,
                        "comparison_sales": 0.0,
                        "total": 0.0,
                        "nonwoven_price_ex_fx": 0.0,
                        "nonwoven_jpy": 0.0,
                        "materials_ex_nonwoven": 0.0,
                        "calculation_errors": 0.0,
                    })
                    detail["nonwoven_jpy"] += group_jpy
                    detail["nonwoven_price_ex_fx"] += group_total - group_jpy
                result.nonwoven_details.append({
                    "period": month,
                    "base_cost": base_nonwoven_cost,
                    "comparison_cost": comparison_nonwoven_cost,
                    "base_output": base_nonwoven_output,
                    "comparison_output": comparison_nonwoven_output,
                    "comparison_input_length": comparison_input_length,
                    "base_jpy_fx": base_jpy,
                    "comparison_jpy_fx": comp_jpy,
                    "base_unit_cost": base_nonwoven_unit,
                    "comparison_unit_cost": comparison_nonwoven_unit,
                    "base_jpy_unit": base_jpy_unit,
                    "nonwoven_total": nonwoven_total,
                    "nonwoven_jpy": jpy_effect,
                    "nonwoven_price_ex_fx": nonwoven_total - jpy_effect,
                    "business_source": "전공정 부직포 생산출고 / KRW/JPY / 판매투입길이",
                    "canonical_fields": "nonwoven_cost / nonwoven_output_length / nonwoven_sales_input_length / jpy_fx_krw_per_jpy",
                    "base_source_reference": " | ".join(sorted({
                        value for row in left for value in (
                            row.nonwoven_cost_source, row.nonwoven_output_source, row.jpy_fx_source
                        ) if value
                    })),
                    "comparison_source_reference": " | ".join(sorted({
                        value for row in right for value in (
                            row.nonwoven_cost_source, row.nonwoven_output_source,
                            row.nonwoven_input_source, row.jpy_fx_source
                        ) if value
                    })),
                    "validation_status": "PASS",
                    "source_validation_status": (
                        "SOURCE_MAPPED"
                        if all(
                            row.source_validation_status in {"PASS", "SOURCE_MAPPED"}
                            for row in (*left, *right)
                        )
                        else "UNVALIDATED"
                    ),
                })
            else:
                result.issues.append(f"{month}: 부직포 엔화 효과 산출용 생산길이 또는 기준 KRW/JPY가 0임")

    result.unit_excluding_jpy = result.total - result.nonwoven_jpy
    result.materials_ex_nonwoven = result.total - result.nonwoven_price_ex_fx - result.nonwoven_jpy
    result.other_unit_mix = result.materials_ex_nonwoven
    for detail in result.by_product_group_details.values():
        detail["materials_ex_nonwoven"] = (
            detail["total"]
            - detail["nonwoven_price_ex_fx"]
            - detail["nonwoven_jpy"]
        )
    return result
