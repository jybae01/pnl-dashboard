from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ReconciliationResult:
    operating_profit_delta: float
    effects_total: float
    residual: float
    reconciled: bool
    tolerance: float


def reconcile(
    operating_profit_delta: float,
    effects: list[dict[str, float | str]],
    *,
    absolute_tolerance: float = 1.0,
    relative_tolerance: float = 1e-9,
) -> ReconciliationResult:
    effects_total = sum(float(item["profit_effect"]) for item in effects)
    residual = operating_profit_delta - effects_total
    tolerance = max(float(absolute_tolerance), abs(operating_profit_delta) * float(relative_tolerance))
    return ReconciliationResult(
        operating_profit_delta=operating_profit_delta,
        effects_total=effects_total,
        residual=residual,
        reconciled=abs(residual) <= tolerance,
        tolerance=tolerance,
    )
