from __future__ import annotations

from typing import Any

from .schema import (
    ActivityRecord,
    AnalysisScenario,
    DirectEffectRecord,
    ExpenseRecord,
    PnlRecord,
    ProductRecord,
    ScenarioMeta,
)


class ForecastOutputNormalizer:
    """Convert a mapping-driven Forecast export payload into the common schema.

    Workbook cell addresses are deliberately excluded. A workbook adapter must map
    cells to the named payload fields before calling this class.
    """

    @staticmethod
    def normalize(payload: dict[str, Any]) -> AnalysisScenario:
        meta = ScenarioMeta(**payload["meta"])

        def manufacturing(row: dict[str, Any]) -> ExpenseRecord:
            ratios = row.get("allocation_ratios", {})
            return ExpenseRecord(
                year_month=row["year_month"],
                account=row.get("manufacturing_expense_account", row.get("account", "")),
                amount=float(row.get("manufacturing_expense_amount", row.get("amount", 0.0))),
                category="manufacturing",
                front_ratio=float(row.get("front_ratio", ratios.get("front", 0.0))),
                back_ratio=float(row.get("back_ratio", ratios.get("back", 0.0))),
            )

        def sga(row: dict[str, Any]) -> ExpenseRecord:
            return ExpenseRecord(
                year_month=row["year_month"],
                account=row.get("sga_account", row.get("account", "")),
                amount=float(row.get("sga_amount", row.get("amount", 0.0))),
                category="sga",
            )

        return AnalysisScenario(
            meta=meta,
            products=[ProductRecord(**row) for row in payload.get("products", [])],
            manufacturing_expenses=[manufacturing(row) for row in payload.get("manufacturing_expenses", [])],
            sga_expenses=[sga(row) for row in payload.get("sga_expenses", [])],
            activities=[ActivityRecord(**row) for row in payload.get("activities", [])],
            pnl=[PnlRecord(**row) for row in payload.get("pnl", [])],
            direct_effects=[DirectEffectRecord(**row) for row in payload.get("direct_effects", [])],
        )
