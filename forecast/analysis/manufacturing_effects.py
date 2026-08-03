from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .configuration import AnalysisConfig
from .schema import ActivityRecord, AnalysisScenario, ExpenseRecord, ProductRecord


@dataclass
class ManufacturingEffects:
    front_activity: float = 0.0
    front_unit: float = 0.0
    back_activity: float = 0.0
    back_unit: float = 0.0
    front_fixed: float = 0.0
    back_fixed: float = 0.0
    occurrence_total: float = 0.0
    realized_total: float = 0.0
    outsourcing_decrease_effect: float = 0.0
    details: list[dict[str, Any]] = field(default_factory=list)
    production_reconciliation: list[dict[str, Any]] = field(default_factory=list)
    realization_details: list[dict[str, float | str]] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)

    @property
    def fixed_total(self) -> float:
        return self.front_fixed + self.back_fixed


@dataclass(frozen=True)
class _MonthActivity:
    front: float
    back: float
    outsourcing_back: float


def _expense_map(scenario: AnalysisScenario) -> dict[tuple[str, str], ExpenseRecord]:
    result: dict[tuple[str, str], ExpenseRecord] = {}
    for row in scenario.manufacturing_expenses:
        key = (row.year_month, row.account)
        if key in result:
            raise ValueError(f"중복 제조경비 레코드: {row.year_month} / {row.account}")
        result[key] = row
    return result


def _activity_map(scenario: AnalysisScenario) -> dict[str, ActivityRecord]:
    return {row.year_month: row for row in scenario.activities}


def _pnl_cogs(scenario: AnalysisScenario) -> dict[str, float]:
    return {row.year_month: row.cogs for row in scenario.pnl}


def _month_products(scenario: AnalysisScenario, month: str) -> list[ProductRecord]:
    return [row for row in scenario.products if row.year_month == month]


def _sap_activity(scenario: AnalysisScenario, month: str, fallback: ActivityRecord) -> _MonthActivity:
    rows = _month_products(scenario, month)
    has_sap_mapping = any(
        row.sap_production_qty is not None or row.sap_production_length is not None
        for row in rows
    )
    if not has_sap_mapping:
        return _MonthActivity(fallback.front_activity, fallback.back_activity, fallback.back_activity)

    front = sum(row.sap_length for row in rows if row.product_group == "FS")
    back_rows = [row for row in rows if (row.mcm_product_group or row.product_group) in {"SW", "BW"}]
    back = sum(row.sap_qty for row in back_rows)
    outsourcing_back = sum(
        row.sap_qty
        for row in back_rows
        if row.outsourcing_eligible_flag and not row.mcm_flag
    )
    return _MonthActivity(front, back, outsourcing_back)


def _front_ratio(
    row: ExpenseRecord | None,
    activity: ActivityRecord,
    account: str,
    config: AnalysisConfig,
) -> float:
    if row and (row.front_ratio or row.back_ratio):
        return row.front_ratio
    if config.is_labor(account) and activity.labor_front_ratio is not None:
        return activity.labor_front_ratio
    if config.is_outsourcing(account) and activity.outsourcing_front_ratio is not None:
        return activity.outsourcing_front_ratio
    if activity.other_expense_front_ratio is not None:
        return activity.other_expense_front_ratio
    return 0.0


def _production_reconciliation(base: AnalysisScenario, comparison: AnalysisScenario, months: list[str]):
    output: list[dict[str, Any]] = []
    for side, scenario in (("base", base), ("comparison", comparison)):
        for month in months:
            rows = _month_products(scenario, month)
            for group in sorted({row.product_group for row in rows}):
                selected = [row for row in rows if row.product_group == group]
                sap_qty = sum(row.sap_qty for row in selected)
                sap_length = sum(row.sap_length for row in selected)
                mes_qty_values = [row.mes_qty for row in selected if row.mes_qty is not None]
                mes_length_values = [row.mes_length for row in selected if row.mes_length is not None]
                output.append({
                    "scenario": side,
                    "month": month,
                    "product_group": group,
                    "sap_qty": sap_qty,
                    "mes_qty": sum(mes_qty_values) if mes_qty_values else None,
                    "qty_difference": (sum(mes_qty_values) - sap_qty) if mes_qty_values else None,
                    "sap_length": sap_length,
                    "mes_length": sum(mes_length_values) if mes_length_values else None,
                    "length_difference": (sum(mes_length_values) - sap_length) if mes_length_values else None,
                })
    return output


def calculate_manufacturing_effects(
    base: AnalysisScenario,
    comparison: AnalysisScenario,
    config: AnalysisConfig,
) -> ManufacturingEffects:
    result = ManufacturingEffects()
    left, right = _expense_map(base), _expense_map(comparison)
    act0, act1 = _activity_map(base), _activity_map(comparison)
    cogs1 = _pnl_cogs(comparison)
    months = sorted(set(base.months) & set(comparison.months))
    result.production_reconciliation = _production_reconciliation(base, comparison, months)

    for month in months:
        accounts = sorted(
            {account for ym, account in left if ym == month}
            | {account for ym, account in right if ym == month}
        )
        raw_a0 = act0.get(month, ActivityRecord(month))
        raw_a1 = act1.get(month, ActivityRecord(month))
        a0 = _sap_activity(base, month, raw_a0)
        a1 = _sap_activity(comparison, month, raw_a1)
        occurrence_month = 0.0
        for account in accounts:
            lrow, rrow = left.get((month, account)), right.get((month, account))
            amount0 = lrow.amount if lrow else 0.0
            amount1 = rrow.amount if rrow else 0.0
            fr0 = _front_ratio(lrow, raw_a0, account, config)
            fr1 = _front_ratio(rrow, raw_a1, account, config) if rrow else fr0
            br0, br1 = 1.0 - fr0, 1.0 - fr1
            front0, front1 = amount0 * fr0, amount1 * fr1
            back0, back1 = amount0 * br0, amount1 * br1
            detail: dict[str, Any] = {
                "month": month,
                "account": account,
                "classification": "variable" if config.is_variable_manufacturing(account) else "fixed",
                "front_ratio_base": fr0,
                "front_ratio_comparison": fr1,
            }
            if config.is_variable_manufacturing(account):
                back_activity0 = a0.outsourcing_back if config.is_outsourcing(account) else a0.back
                back_activity1 = a1.outsourcing_back if config.is_outsourcing(account) else a1.back
                fu0 = front0 / a0.front if a0.front else 0.0
                fu1 = front1 / a1.front if a1.front else 0.0
                bu0 = back0 / back_activity0 if back_activity0 else 0.0
                bu1 = back1 / back_activity1 if back_activity1 else 0.0
                fa = -(a1.front - a0.front) * fu0
                fuv = -a1.front * (fu1 - fu0)
                ba = -(back_activity1 - back_activity0) * bu0
                buv = -back_activity1 * (bu1 - bu0)
                result.front_activity += fa
                result.front_unit += fuv
                result.back_activity += ba
                result.back_unit += buv
                occurrence = fa + fuv + ba + buv
                detail.update(
                    front_activity=fa,
                    front_unit=fuv,
                    back_activity=ba,
                    back_unit=buv,
                    base_front_activity=a0.front,
                    comparison_front_activity=a1.front,
                    base_back_activity=back_activity0,
                    comparison_back_activity=back_activity1,
                )
                if config.is_outsourcing(account) and amount1 < amount0:
                    result.outsourcing_decrease_effect += amount0 - amount1
                if (front0 and not a0.front) or (back0 and not back_activity0):
                    result.issues.append(f"{month} {account}: 기준 SAP 생산입고 조업도 분모가 0임")
            else:
                ff = front0 - front1
                bf = back0 - back1
                result.front_fixed += ff
                result.back_fixed += bf
                occurrence = ff + bf
                detail.update(front_fixed=ff, back_fixed=bf)
            occurrence_month += occurrence
            detail["occurrence_effect"] = occurrence
            result.details.append(detail)

        explicit_rate = raw_a1.inventory_realization_rate
        if explicit_rate is not None:
            realization_rate = float(explicit_rate)
            source = "explicit"
        elif raw_a1.manufacturing_input_cost:
            realization_rate = cogs1.get(month, 0.0) / raw_a1.manufacturing_input_cost
            source = "cogs/current_period_manufacturing_input"
        else:
            realization_rate = 0.0
            source = "zero_denominator"
            if occurrence_month:
                result.issues.append(f"{month}: 당기투입제조원가가 0이라 제조경비 손익실현 효과를 0으로 처리함")
        realized = occurrence_month * realization_rate
        result.occurrence_total += occurrence_month
        result.realized_total += realized
        result.realization_details.append({
            "month": month,
            "rate": realization_rate,
            "source": source,
            "occurrence_effect": occurrence_month,
            "realized_effect": realized,
        })

    return result
