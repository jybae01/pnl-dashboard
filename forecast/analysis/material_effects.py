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
    mcm_by_product_group: dict[str, float] = field(default_factory=dict)
    issues: list[str] = field(default_factory=list)

    @property
    def detail_reconciliation_difference(self) -> float:
        return self.total - (
            self.nonwoven_price_ex_fx + self.nonwoven_jpy + self.materials_ex_nonwoven
        )


def _group_rows(scenario: AnalysisScenario, month: str, group: str) -> list[ProductRecord]:
    return [row for row in scenario.products if row.year_month == month and row.product_group == group]


def calculate_material_effects(base: AnalysisScenario, comparison: AnalysisScenario) -> MaterialEffects:
    result = MaterialEffects()
    months = sorted(set(base.months) & set(comparison.months))
    for month in months:
        groups = sorted(
            {row.product_group for row in base.products if row.year_month == month}
            | {row.product_group for row in comparison.products if row.year_month == month}
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
            base_unit = base_cost / base_output if base_output else 0.0
            comp_unit = comp_cost / comp_output if comp_output else 0.0
            effect = (base_unit - comp_unit) * comparison_sales
            result.total += effect
            result.by_product_group[group] = result.by_product_group.get(group, 0.0) + effect
            if (base_cost and not base_output) or (comp_cost and not comp_output):
                result.issues.append(f"{month} {group}: 원부재료 생산출고 분모가 0임")

        left = [row for row in base.products if row.year_month == month]
        right = [row for row in comparison.products if row.year_month == month]
        base_nonwoven_cost = sum(row.nonwoven_cost for row in left)
        comparison_nonwoven_cost = sum(row.nonwoven_cost for row in right)
        base_nonwoven_output = sum(row.sap_length for row in left)
        comparison_nonwoven_output = sum(row.sap_length for row in right)
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
            else:
                result.issues.append(f"{month}: 부직포 엔화 효과 산출용 생산길이 또는 기준 KRW/JPY가 0임")

    result.unit_excluding_jpy = result.total - result.nonwoven_jpy
    result.materials_ex_nonwoven = result.total - result.nonwoven_price_ex_fx - result.nonwoven_jpy
    result.other_unit_mix = result.materials_ex_nonwoven
    return result
