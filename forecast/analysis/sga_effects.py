from __future__ import annotations

from dataclasses import dataclass, field

from .configuration import AnalysisConfig
from .schema import AnalysisScenario


@dataclass
class SgaEffects:
    variable: float = 0.0
    fixed: float = 0.0
    details: list[dict[str, float | str]] = field(default_factory=list)

    @property
    def total(self) -> float:
        return self.variable + self.fixed


def calculate_sga_effects(
    base: AnalysisScenario,
    comparison: AnalysisScenario,
    config: AnalysisConfig,
) -> SgaEffects:
    result = SgaEffects()
    months = sorted(set(base.months) & set(comparison.months))
    for month in months:
        left = {row.account: row.amount for row in base.sga_expenses if row.year_month == month}
        right = {row.account: row.amount for row in comparison.sga_expenses if row.year_month == month}
        for account in sorted(set(left) | set(right)):
            baseline_amount = float(left.get(account, 0.0))
            comparison_amount = float(right.get(account, 0.0))
            if config.is_transport(account):
                result.details.append({
                    "month": month,
                    "account": account,
                    "classification": "transport",
                    "baseline_amount": baseline_amount,
                    "comparison_amount": comparison_amount,
                    "delta": comparison_amount - baseline_amount,
                    "profit_effect": 0.0,
                    "bridge_position": "판매효과",
                })
                continue
            effect = baseline_amount - comparison_amount
            bucket = "variable" if config.is_variable_sga(account) else "fixed"
            setattr(result, bucket, getattr(result, bucket) + effect)
            result.details.append({
                "month": month,
                "account": account,
                "classification": bucket,
                "baseline_amount": baseline_amount,
                "comparison_amount": comparison_amount,
                "delta": comparison_amount - baseline_amount,
                "profit_effect": effect,
                "bridge_position": "판관비",
            })
    return result
