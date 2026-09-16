from __future__ import annotations

import re
from dataclasses import dataclass, field

from .configuration import AnalysisConfig
from .schema import AnalysisScenario, ExpenseRecord


@dataclass
class SgaEffects:
    variable: float = 0.0
    fixed: float = 0.0
    details: list[dict[str, float | str | int | None]] = field(default_factory=list)

    @property
    def total(self) -> float:
        return self.variable + self.fixed


def _sga_key(r: ExpenseRecord) -> tuple[str, int | None, str]:
    section = getattr(r, "source_section", "")
    row_num = getattr(r, "source_row", None)
    if not section and r.business_source and " / " in r.business_source:
        section = r.business_source.split(" / ", 1)[0].strip()
    if row_num is None and r.amount_source:
        m = re.search(r"(\d+)$", r.amount_source)
        if m:
            row_num = int(m.group(1))
    return (section, row_num, r.account)


def calculate_sga_effects(
    base: AnalysisScenario,
    comparison: AnalysisScenario,
    config: AnalysisConfig,
) -> SgaEffects:
    result = SgaEffects()
    months = sorted(set(base.months) & set(comparison.months))
    for month in months:
        left: dict[tuple[str, int | None, str], float] = {}
        right: dict[tuple[str, int | None, str], float] = {}
        for row in base.sga_expenses:
            if row.year_month == month:
                k = _sga_key(row)
                left[k] = left.get(k, 0.0) + float(row.amount)
        for row in comparison.sga_expenses:
            if row.year_month == month:
                k = _sga_key(row)
                right[k] = right.get(k, 0.0) + float(row.amount)

        all_keys = sorted(
            set(left) | set(right),
            key=lambda k: (k[1] if k[1] is not None else 10**9, k[0], k[2]),
        )
        for key in all_keys:
            section, row_num, account = key
            baseline_amount = float(left.get(key, 0.0))
            comparison_amount = float(right.get(key, 0.0))
            is_transport = config.is_transport(account) and section != "일반관리비"
            if is_transport:
                result.details.append({
                    "month": month,
                    "account": account,
                    "section": section,
                    "row": row_num,
                    "classification": "transport",
                    "baseline_amount": baseline_amount,
                    "comparison_amount": comparison_amount,
                    "delta": comparison_amount - baseline_amount,
                    "profit_effect": 0.0,
                    "bridge_position": "변동 판관비",
                })
                continue
            effect = baseline_amount - comparison_amount
            short_account = account.split("_", 1)[-1]
            is_var = config.is_variable_sga(account) or config.is_variable_sga(short_account)
            bucket = "variable" if is_var else "fixed"
            setattr(result, bucket, getattr(result, bucket) + effect)
            result.details.append({
                "month": month,
                "account": account,
                "section": section,
                "row": row_num,
                "classification": bucket,
                "baseline_amount": baseline_amount,
                "comparison_amount": comparison_amount,
                "delta": comparison_amount - baseline_amount,
                "profit_effect": effect,
                "bridge_position": "변동 판관비" if is_var else "판관비",
            })
    return result
