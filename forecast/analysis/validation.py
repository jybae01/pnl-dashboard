from __future__ import annotations

from .configuration import AnalysisConfig
from .schema import AnalysisScenario


def validate_scenario(scenario: AnalysisScenario, config: AnalysisConfig) -> list[str]:
    issues: list[str] = []
    unknown_groups = sorted({row.product_group for row in scenario.products if row.product_group not in config.product_groups})
    if unknown_groups:
        issues.append(f"미등록 제품군: {', '.join(unknown_groups)}")

    for label, rows in (("활동", scenario.activities), ("손익", scenario.pnl)):
        months = [row.year_month for row in rows]
        duplicates = sorted({month for month in months if months.count(month) > 1})
        if duplicates:
            issues.append(f"{label} 월 중복: {', '.join(duplicates)}")

    for row in scenario.manufacturing_expenses:
        ratio_total = row.front_ratio + row.back_ratio
        if row.amount and abs(ratio_total - 1.0) > 1e-6:
            issues.append(
                f"{row.year_month} {row.account}: 전·후공정 배부율 합계가 {ratio_total:.6f}로 100%가 아님"
            )
        if row.front_ratio < 0 or row.back_ratio < 0:
            issues.append(f"{row.year_month} {row.account}: 음수 배부율")
    for row in scenario.products:
        if row.mcm_issue_amount and not (row.mcm_flag or row.mcm_qty):
            issues.append(f"{row.year_month} {row.product_code}: MCM 출고금액은 있으나 MCM 식별값이 없음")
        if row.effective_jpy_fx < 0:
            issues.append(f"{row.year_month} {row.product_code}: 원/JPY 환율이 음수임")
    return issues
