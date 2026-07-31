from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .storage import ModelMeta
from .workbook import GoldenWorkbook


@dataclass(frozen=True)
class PeriodOption:
    key: str
    label: str
    months: tuple[int, ...]
    period_type: str


@dataclass
class ComparisonResult:
    baseline: dict[str, Any]
    comparison: dict[str, Any]
    period: dict[str, Any]
    pnl: list[dict[str, Any]]
    products: list[dict[str, Any]]
    production: list[dict[str, Any]]
    mcm: list[dict[str, Any]]
    cost_summary: list[dict[str, Any]]
    effects: list[dict[str, Any]]
    operating_profit_delta: float
    effects_total: float
    residual: float
    reconciled: bool


class GenericComparisonEngine:
    """Compare any two Golden-Model-compatible workbooks.

    Scenario type is metadata only. Delta is always comparison - baseline.
    """

    MONTH_COLUMNS = {month: chr(ord("E") + month - 1) for month in range(1, 13)}

    def __init__(self, mapping_path: str | Path):
        self.mapping = json.loads(Path(mapping_path).read_text(encoding="utf-8"))["comparison"]

    @staticmethod
    def common_months(baseline: ModelMeta, comparison: ModelMeta) -> tuple[int, ...]:
        if baseline.year != comparison.year:
            return ()
        left = set(range(baseline.start_month, baseline.end_month + 1))
        right = set(range(comparison.start_month, comparison.end_month + 1))
        return tuple(sorted(left & right))

    def available_periods(self, baseline: ModelMeta, comparison: ModelMeta) -> list[PeriodOption]:
        common = self.common_months(baseline, comparison)
        common_set = set(common)
        options = [PeriodOption(f"M{month:02d}", f"{month}월", (month,), "월") for month in common]
        for quarter in range(1, 5):
            months = tuple(range((quarter - 1) * 3 + 1, quarter * 3 + 1))
            if set(months).issubset(common_set):
                options.append(PeriodOption(f"Q{quarter}", f"{quarter}분기", months, "분기"))
        for end in common:
            months = tuple(range(1, end + 1))
            if set(months).issubset(common_set):
                options.append(PeriodOption(f"YTD{end:02d}", f"1~{end}월 누계", months, "누계"))
        for start in common:
            months = tuple(range(start, 13))
            if set(months).issubset(common_set):
                options.append(PeriodOption(f"REM{start:02d}", f"{start}~12월 잔여연간", months, "잔여연간"))
        return options

    def compare(
        self,
        baseline_meta: ModelMeta,
        baseline_path: str | Path,
        comparison_meta: ModelMeta,
        comparison_path: str | Path,
        period: PeriodOption,
    ) -> ComparisonResult:
        allowed = {item.key: item for item in self.available_periods(baseline_meta, comparison_meta)}
        if period.key not in allowed:
            raise ValueError("두 모형의 공통기간에 포함되지 않는 비교기간입니다.")
        baseline = self._extract(GoldenWorkbook(baseline_path), baseline_meta, period.months)
        target = self._extract(GoldenWorkbook(comparison_path), comparison_meta, period.months)

        pnl = self._rows(self.mapping["pnl_labels"], baseline["pnl"], target["pnl"])
        products = []
        for key, spec in self.mapping["products"].items():
            left, right = baseline["products"][key], target["products"][key]
            products.append({
                "code": key, "item": spec["label"],
                "baseline_quantity": left["quantity"], "comparison_quantity": right["quantity"],
                "quantity_delta": right["quantity"] - left["quantity"],
                "baseline_amount": left["amount"], "comparison_amount": right["amount"],
                "amount_delta": right["amount"] - left["amount"],
                "baseline_price": left["price"], "comparison_price": right["price"],
                "price_delta": right["price"] - left["price"],
            })
        production = self._rows(self.mapping["production_labels"], baseline["production"], target["production"])
        mcm = self._rows(self.mapping["mcm_labels"], baseline["mcm"], target["mcm"])
        cost_summary = self._rows(self.mapping["cost_labels"], baseline["cost_summary"], target["cost_summary"])

        effects = []
        for key, label in self.mapping["effect_labels"].items():
            delta = target["effect_bases"][key] - baseline["effect_bases"][key]
            effect = delta if key == "revenue" else -delta
            effects.append({"code": key, "factor": label, "baseline": baseline["effect_bases"][key],
                            "comparison": target["effect_bases"][key], "delta": delta, "profit_effect": effect})
        op_delta = target["pnl"]["operating_profit"] - baseline["pnl"]["operating_profit"]
        effects_total = sum(item["profit_effect"] for item in effects)
        residual = op_delta - effects_total
        tolerance = max(1.0, abs(op_delta) * 1e-9)
        return ComparisonResult(
            baseline=asdict(baseline_meta), comparison=asdict(comparison_meta), period=asdict(period),
            pnl=pnl, products=products, production=production, mcm=mcm, cost_summary=cost_summary,
            effects=effects, operating_profit_delta=op_delta, effects_total=effects_total,
            residual=residual, reconciled=abs(residual) <= tolerance,
        )

    @staticmethod
    def _rows(labels: dict[str, str], baseline: dict[str, float], comparison: dict[str, float]) -> list[dict[str, Any]]:
        return [{"code": key, "item": label, "baseline": baseline[key], "comparison": comparison[key],
                 "delta": comparison[key] - baseline[key]} for key, label in labels.items()]

    def _extract(self, workbook: GoldenWorkbook, meta: ModelMeta, months: tuple[int, ...]) -> dict[str, Any]:
        def total(row: int) -> float:
            return sum(float(workbook.value(f"{self.MONTH_COLUMNS[month]}{row}") or 0) for month in months)

        web_tariff = meta.tariff_for_months(months)
        external_tariff = 0.0 if meta.tariff_in_workbook else web_tariff
        pnl = {key: total(row) for key, row in self.mapping["pnl_rows"].items()}
        pnl["selling_expense"] += external_tariff
        pnl["operating_profit"] -= external_tariff
        products: dict[str, dict[str, float]] = {}
        for key, spec in self.mapping["products"].items():
            quantity, amount = total(spec["quantity_row"]), total(spec["amount_row"])
            products[key] = {"quantity": quantity, "amount": amount, "price": amount / quantity if quantity else 0.0}
        production = {key: total(row) for key, row in self.mapping["production_rows"].items()}
        mcm = {key: total(row) for key, row in self.mapping["mcm_rows"].items()}

        raw_material = total(1229) + total(1237)
        labor = total(1230) + total(1238)
        outsourcing = total(1231) + total(1239)
        other_processing = total(1232) + total(1240)
        tariff = web_tariff
        selling = total(1257) + external_tariff
        selling_before_tariff = selling - tariff
        cost_summary = {
            "raw_material": raw_material,
            "labor": labor,
            "outsourcing": outsourcing,
            "other_processing": other_processing,
            "processing_total": labor + outsourcing + other_processing,
            "manufacturing_expense": total(296),
            "selling_expense": selling,
            "general_admin": total(1258),
            "sga_total": selling + total(1258),
            "disposal": total(1248),
            "obsolescence": total(1250),
            "tariff": tariff,
            "customs_refund": total(1246),
        }
        effect_bases = {
            "revenue": total(1201),
            "product_raw_material": total(1229),
            "product_labor": total(1230),
            "product_outsourcing": total(1231),
            "product_other": total(1232),
            "semi_raw_material": total(1237),
            "semi_labor": total(1238),
            "semi_outsourcing": total(1239),
            "semi_other": total(1240),
            "goods_cogs": total(1241),
            "other_cogs": total(1244),
            "paid_supply_cancel": total(1245),
            "customs_refund": total(1246),
            "disposal": total(1248),
            "other_standard_cogs": total(1249),
            "obsolescence": total(1250),
            "selling_ex_tariff": selling_before_tariff,
            "tariff": tariff,
            "general_admin": total(1258),
        }
        return {"pnl": pnl, "products": products, "production": production, "mcm": mcm,
                "cost_summary": cost_summary, "effect_bases": effect_bases}
