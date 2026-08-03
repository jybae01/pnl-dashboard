from __future__ import annotations

from dataclasses import dataclass, field

from .schema import AnalysisScenario, ProductRecord


@dataclass
class MaterialEffects:
    """Raw-material effects in operating-profit sign convention."""

    total: float = 0.0
    nonwoven_jpy: float = 0.0
    mcm_paid_supply: float = 0.0
    other_unit_mix: float = 0.0
    unit_excluding_jpy: float = 0.0
    by_product_group: dict[str, float] = field(default_factory=dict)
    mcm_by_product_group: dict[str, float] = field(default_factory=dict)
    issues: list[str] = field(default_factory=list)

    @property
    def detail_reconciliation_difference(self) -> float:
        return self.total - (self.nonwoven_jpy + self.mcm_paid_supply + self.other_unit_mix)


def _group_rows(scenario: AnalysisScenario, month: str, group: str) -> list[ProductRecord]:
    return [row for row in scenario.products if row.year_month == month and row.product_group == group]


def _mcm_group_rows(scenario: AnalysisScenario, month: str, group: str) -> list[ProductRecord]:
    return [
        row for row in scenario.products
        if row.year_month == month
        and (row.mcm_product_group or row.product_group) == group
        and (row.mcm_flag or row.mcm_issue_amount or row.mcm_qty)
    ]


def _mcm_unit(rows: list[ProductRecord]) -> tuple[float, float]:
    """Return MCM issue amount per related SAP production quantity and amount."""
    amount = sum(float(row.mcm_issue_amount) for row in rows)
    denominator = sum(
        float(row.sap_qty)
        for row in rows
        if row.mcm_flag or row.mcm_issue_amount or row.mcm_qty
    )
    if not denominator:
        denominator = sum(float(row.mcm_qty) for row in rows)
    return (amount / denominator if denominator else 0.0), amount


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

            mcm_unit0, mcm_amount0 = _mcm_unit(_mcm_group_rows(base, month, group))
            mcm_unit1, mcm_amount1 = _mcm_unit(_mcm_group_rows(comparison, month, group))
            if mcm_amount0 or mcm_amount1:
                mcm_effect = (mcm_unit0 - mcm_unit1) * comparison_sales
                result.mcm_paid_supply += mcm_effect
                result.mcm_by_product_group[group] = (
                    result.mcm_by_product_group.get(group, 0.0) + mcm_effect
                )
                if comparison_sales and ((mcm_amount0 and not mcm_unit0) or (mcm_amount1 and not mcm_unit1)):
                    result.issues.append(f"{month} {group}: MCM 생산출고 원단위 분모가 0임")

        left = [row for row in base.products if row.year_month == month]
        right = [row for row in comparison.products if row.year_month == month]
        base_nonwoven_cost = sum(row.nonwoven_cost for row in left)
        base_nonwoven_output = sum(row.sap_length for row in left)
        comparison_input_length = sum(row.nonwoven_sales_input_length for row in right)
        base_jpy = next((row.effective_jpy_fx for row in left if row.effective_jpy_fx), 0.0)
        comp_jpy = next((row.effective_jpy_fx for row in right if row.effective_jpy_fx), 0.0)
        if base_nonwoven_cost or comparison_input_length:
            if base_nonwoven_output and base_jpy:
                # FX is KRW/JPY. Do not convert to KRW/100JPY.
                base_jpy_unit = (base_nonwoven_cost / base_nonwoven_output) / base_jpy
                result.nonwoven_jpy += comparison_input_length * base_jpy_unit * (base_jpy - comp_jpy)
            else:
                result.issues.append(f"{month}: 부직포 엔화 효과 산출용 생산길이 또는 기준 KRW/JPY가 0임")

    result.unit_excluding_jpy = result.total - result.nonwoven_jpy
    result.other_unit_mix = result.total - result.nonwoven_jpy - result.mcm_paid_supply
    return result
