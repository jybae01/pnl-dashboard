from __future__ import annotations

from dataclasses import dataclass, field

from .configuration import AnalysisConfig
from .schema import ActivityRecord, AnalysisScenario, ExpenseRecord


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
    details: list[dict[str, float | str]] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)


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

    for month in months:
        accounts = sorted({account for ym, account in left if ym == month} | {account for ym, account in right if ym == month})
        a0, a1 = act0.get(month, ActivityRecord(month)), act1.get(month, ActivityRecord(month))
        occurrence_month = 0.0
        for account in accounts:
            lrow, rrow = left.get((month, account)), right.get((month, account))
            amount0, amount1 = (lrow.amount if lrow else 0.0), (rrow.amount if rrow else 0.0)
            fr0, br0 = (lrow.front_ratio if lrow else 0.0), (lrow.back_ratio if lrow else 0.0)
            fr1, br1 = (rrow.front_ratio if rrow else fr0), (rrow.back_ratio if rrow else br0)
            front0, front1 = amount0 * fr0, amount1 * fr1
            back0, back1 = amount0 * br0, amount1 * br1
            detail = {"month": month, "account": account}
            if config.is_variable_manufacturing(account):
                fu0 = front0 / a0.front_activity if a0.front_activity else 0.0
                fu1 = front1 / a1.front_activity if a1.front_activity else 0.0
                bu0 = back0 / a0.back_activity if a0.back_activity else 0.0
                bu1 = back1 / a1.back_activity if a1.back_activity else 0.0
                fa = -(a1.front_activity - a0.front_activity) * fu0
                fuv = -a1.front_activity * (fu1 - fu0)
                ba = -(a1.back_activity - a0.back_activity) * bu0
                buv = -a1.back_activity * (bu1 - bu0)
                result.front_activity += fa
                result.front_unit += fuv
                result.back_activity += ba
                result.back_unit += buv
                occurrence = fa + fuv + ba + buv
                detail.update(front_activity=fa, front_unit=fuv, back_activity=ba, back_unit=buv)
                if (front0 and not a0.front_activity) or (back0 and not a0.back_activity):
                    result.issues.append(f"{month} {account}: 기준 조업도 분모가 0임")
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

        explicit_rate = a1.inventory_realization_rate
        if explicit_rate is not None:
            realization_rate = float(explicit_rate)
        elif a1.manufacturing_input_cost:
            realization_rate = cogs1.get(month, 0.0) / a1.manufacturing_input_cost
        else:
            realization_rate = 0.0
            if occurrence_month:
                result.issues.append(f"{month}: 당기투입제조원가가 0이라 제조경비 손익실현 효과를 0으로 처리함")
        result.occurrence_total += occurrence_month
        result.realized_total += occurrence_month * realization_rate

    return result
