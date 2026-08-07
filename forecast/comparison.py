from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .storage import ModelMeta
from .workbook import GoldenWorkbook
from .analysis.configuration import AnalysisConfig
from .analysis.golden_adapter import GoldenAnalysisAdapter
from .analysis.manufacturing_effects import calculate_manufacturing_effects
from .analysis.material_effects import calculate_material_effects
from .analysis.sales_effects import calculate_sales_effects
from .analysis.sga_effects import calculate_sga_effects
from .sales_comparison import calculate_sales_effect_rows, sales_effect_totals


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
    sales_groups: list[dict[str, Any]]
    production: list[dict[str, Any]]
    mcm: list[dict[str, Any]]
    cost_summary: list[dict[str, Any]]
    effects: list[dict[str, Any]]
    operating_profit_delta: float
    effects_total: float
    residual: float
    reconciled: bool
    narrative: str = ""
    mcm_transition: dict[str, Any] | None = None
    manufacturing_accounts: list[dict[str, Any]] = field(default_factory=list)
    sga_accounts: list[dict[str, Any]] = field(default_factory=list)
    material_analysis: dict[str, Any] = field(default_factory=dict)
    manufacturing_analysis: dict[str, Any] = field(default_factory=dict)
    sales_analysis: dict[str, Any] = field(default_factory=dict)


class GenericComparisonEngine:
    """Compare any two Golden-Model-compatible workbooks.

    Scenario type is metadata only. Delta is always comparison - baseline.
    """

    MONTH_COLUMNS = {month: chr(ord("E") + month - 1) for month in range(1, 13)}

    def __init__(self, mapping_path: str | Path):
        mapping_path = Path(mapping_path)
        payload = json.loads(mapping_path.read_text(encoding="utf-8"))
        self.full_mapping = payload
        self.mapping = payload["comparison"]
        self.manufacturing_account_rows = tuple(payload.get("manufacturing_input_rows", ()))
        self.sga_account_rows = tuple(payload.get("sga_input_rows", ()))
        analysis_config_path = mapping_path.with_name("analysis_v1.json")
        self.analysis_config = (
            AnalysisConfig.load(analysis_config_path) if analysis_config_path.exists() else None
        )
        if self.analysis_config is None:
            raise ValueError("analysis_v1.json is required for Golden Model comparison")
        self.analysis_adapter = GoldenAnalysisAdapter(payload, self.analysis_config)

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
        *,
        baseline_sales_fx: float = 1480.0,
        comparison_sales_fx: float = 1480.0,
    ) -> ComparisonResult:
        common = set(self.common_months(baseline_meta, comparison_meta))
        if not period.months or not set(period.months).issubset(common):
            raise ValueError("두 모형의 공통기간에 포함되지 않는 비교기간입니다.")
        baseline = self._extract(
            GoldenWorkbook(baseline_path), baseline_meta, period.months,
            sales_fx=baseline_sales_fx,
        )
        target = self._extract(
            GoldenWorkbook(comparison_path), comparison_meta, period.months,
            sales_fx=comparison_sales_fx,
        )

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
        sales_groups = []
        for key, spec in self.mapping["sales_groups"].items():
            left, right = baseline["sales_groups"][key], target["sales_groups"][key]
            sales_groups.append({
                "product_group": spec["label"],
                "baseline_quantity": left["quantity"],
                "baseline_amount": left["amount"],
                "baseline_cogs": left["cogs"],
                "baseline_gross_margin_rate": left["gross_margin_rate"],
                "comparison_quantity": right["quantity"],
                "comparison_amount": right["amount"],
                "comparison_cogs": right["cogs"],
                "comparison_gross_margin_rate": right["gross_margin_rate"],
            })
        calculated_sales = calculate_sales_effect_rows(
            sales_groups, baseline_sales_fx, comparison_sales_fx
        )
        sales_analysis = {
            "baseline_fx_krw_per_usd": float(baseline_sales_fx),
            "comparison_fx_krw_per_usd": float(comparison_sales_fx),
            "rows": [row.to_dict() for row in calculated_sales],
            "totals": sales_effect_totals(calculated_sales),
        }
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
        narrative = self._narrative(op_delta, effects, residual)
        if baseline.get("adapted") is not None and target.get("adapted") is not None:
            base_scenario = baseline["adapted"].scenario
            comparison_scenario = target["adapted"].scenario
            calculated_analysis_sales = calculate_sales_effects(
                base_scenario, comparison_scenario, self.analysis_config
            )
            calculated_analysis_material = calculate_material_effects(
                base_scenario, comparison_scenario
            )
            calculated_analysis_manufacturing = calculate_manufacturing_effects(
                base_scenario, comparison_scenario, self.analysis_config
            )
            calculated_analysis_sga = calculate_sga_effects(
                base_scenario, comparison_scenario, self.analysis_config
            )
            # Keep the legacy group rows for the sales tab, but make their
            # aggregate totals come from the same normalized records used by
            # the bridge. This brings mix, transport and the direct tariff
            # input into one deterministic reconciliation.
            sales_analysis["totals"] = {
                **sales_analysis["totals"],
                "quantity_effect": calculated_analysis_sales.quantity,
                "mix_effect": calculated_analysis_sales.mix,
                "pure_price_effect": calculated_analysis_sales.price,
                "sales_fx_effect": calculated_analysis_sales.sales_fx,
                "transport_quantity_effect": calculated_analysis_sales.transport_quantity,
                "transport_unit_effect": calculated_analysis_sales.transport_unit,
                "tariff_effect": calculated_analysis_sales.tariff,
                "total_sales_effect": (
                    calculated_analysis_sales.quantity
                    + calculated_analysis_sales.mix
                    + calculated_analysis_sales.price
                    + calculated_analysis_sales.sales_fx
                ),
            }
            effects = [
                {
                    "code": "sales_quantity",
                    "factor": "판매수량 효과",
                    "baseline": None,
                    "comparison": None,
                    "delta": None,
                    "profit_effect": calculated_analysis_sales.quantity,
                },
                {
                    "code": "sales_mix",
                    "factor": "제품 Mix 효과",
                    "baseline": None,
                    "comparison": None,
                    "delta": None,
                    "profit_effect": calculated_analysis_sales.mix,
                },
                {
                    "code": "sales_price",
                    "factor": "판매단가 효과(관세 제외 운반비 단가 포함)",
                    "baseline": None,
                    "comparison": None,
                    "delta": None,
                    "profit_effect": calculated_analysis_sales.price,
                },
                {
                    "code": "sales_fx",
                    "factor": "매출환율 효과",
                    "baseline": None,
                    "comparison": None,
                    "delta": None,
                    "profit_effect": calculated_analysis_sales.sales_fx,
                },
                {
                    "code": "tariff",
                    "factor": "관세 효과",
                    "baseline": None,
                    "comparison": None,
                    "delta": None,
                    "profit_effect": calculated_analysis_sales.tariff,
                },
                {
                    "code": "material_total",
                    "factor": "원부재료 총효과",
                    "baseline": None,
                    "comparison": None,
                    "delta": None,
                    "profit_effect": calculated_analysis_material.total,
                },
                {
                    "code": "manufacturing_realized",
                    "factor": "제조경비 재고실현 효과",
                    "baseline": None,
                    "comparison": None,
                    "delta": None,
                    "profit_effect": calculated_analysis_manufacturing.realized_total,
                },
                {
                    "code": "sga_variable",
                    "factor": "변동 판관비 효과",
                    "baseline": None,
                    "comparison": None,
                    "delta": None,
                    "profit_effect": calculated_analysis_sga.variable,
                },
                {
                    "code": "sga_fixed",
                    "factor": "고정 판관비 효과",
                    "baseline": None,
                    "comparison": None,
                    "delta": None,
                    "profit_effect": calculated_analysis_sga.fixed,
                },
            ]
            material_analysis = self.analysis_adapter.material_analysis(
                baseline["adapted"], target["adapted"]
            )
            manufacturing_accounts, manufacturing_analysis = (
                self.analysis_adapter.manufacturing_accounts(
                    baseline["adapted"], target["adapted"]
                )
            )
        else:
            material_analysis = {}
            manufacturing_accounts = self._manufacturing_account_rows(
                baseline.get("manufacturing_accounts", []),
                target.get("manufacturing_accounts", []),
                target.get("pnl", {}),
                target.get("cost_summary", {}),
            )
            manufacturing_analysis = {}
        # Recompute the bridge after the adapter branch. Legacy payloads keep
        # their mapping-driven effects; real Golden Models use normalized V1
        # effects assembled above.
        effects_total = sum(float(item["profit_effect"] or 0.0) for item in effects)
        residual = op_delta - effects_total
        tolerance = max(1.0, abs(op_delta) * 1e-9)
        narrative = self._narrative(op_delta, effects, residual)
        sga_accounts = self._sga_account_rows(
            baseline.get("sga_accounts", []),
            target.get("sga_accounts", []),
            baseline.get("cost_summary", {}),
            target.get("cost_summary", {}),
        )
        return ComparisonResult(
            baseline=asdict(baseline_meta), comparison=asdict(comparison_meta), period=asdict(period),
            pnl=pnl, products=products, sales_groups=sales_groups, production=production, mcm=mcm,
            cost_summary=cost_summary,
            effects=effects, operating_profit_delta=op_delta, effects_total=effects_total,
            residual=residual, reconciled=abs(residual) <= tolerance,
            narrative=narrative,
            mcm_transition=None,
            manufacturing_accounts=manufacturing_accounts,
            sga_accounts=sga_accounts,
            material_analysis=material_analysis,
            manufacturing_analysis=manufacturing_analysis,
            sales_analysis=sales_analysis,
        )

    @staticmethod
    def _account_map(rows: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
        return {int(row["row"]): row for row in rows}

    def _manufacturing_account_rows(
        self,
        baseline_rows: list[dict[str, Any]],
        comparison_rows: list[dict[str, Any]],
        comparison_pnl: dict[str, float],
        comparison_costs: dict[str, float],
    ) -> list[dict[str, Any]]:
        baseline = self._account_map(baseline_rows)
        comparison = self._account_map(comparison_rows)
        manufacturing_input = sum(float(comparison_costs.get(code) or 0.0) for code in (
            "raw_material", "labor", "outsourcing", "other_processing"
        ))
        realization_rate = (
            float(comparison_pnl.get("cogs") or 0.0) / manufacturing_input
            if manufacturing_input else None
        )
        output: list[dict[str, Any]] = []
        for row_number in sorted(set(baseline) | set(comparison)):
            left = baseline.get(row_number, {})
            right = comparison.get(row_number, {})
            account = str(right.get("account") or left.get("account") or f"행 {row_number}")
            base_amount = float(left.get("amount") or 0.0)
            comparison_amount = float(right.get("amount") or 0.0)
            delta = comparison_amount - base_amount
            is_variable = bool(
                self.analysis_config and self.analysis_config.is_variable_manufacturing(account)
            )
            occurrence_effect = base_amount - comparison_amount
            output.append({
                "row": row_number,
                "account": account,
                "classification": "variable" if is_variable else "fixed",
                "baseline_amount": base_amount,
                "comparison_amount": comparison_amount,
                "delta": delta,
                "activity_effect": None if is_variable else 0.0,
                "unit_effect": None if is_variable else 0.0,
                "fixed_effect": 0.0 if is_variable else occurrence_effect,
                "occurrence_effect": occurrence_effect,
                "inventory_realization_rate": realization_rate,
                "final_profit_effect": (
                    occurrence_effect * realization_rate if realization_rate is not None else None
                ),
                "calculation_status": (
                    "발생효과·실현효과 계산 완료 / 조업도·원단위 분해는 전후공정 배부율 매핑 필요"
                    if is_variable else
                    "고정비 기준-비교 및 비교 모형 재고실현율 적용 완료"
                ),
            })
        return output

    def _sga_account_rows(
        self,
        baseline_rows: list[dict[str, Any]],
        comparison_rows: list[dict[str, Any]],
        baseline_costs: dict[str, float],
        comparison_costs: dict[str, float],
    ) -> list[dict[str, Any]]:
        baseline = self._account_map(baseline_rows)
        comparison = self._account_map(comparison_rows)
        output: list[dict[str, Any]] = []
        for row_number in sorted(set(baseline) | set(comparison)):
            left = baseline.get(row_number, {})
            right = comparison.get(row_number, {})
            account = str(right.get("account") or left.get("account") or f"행 {row_number}")
            section = right.get("section") or left.get("section")
            base_amount = float(left.get("amount") or 0.0)
            comparison_amount = float(right.get("amount") or 0.0)
            delta = comparison_amount - base_amount
            short_account = account.split("_", 1)[-1]
            is_transport = bool(
                self.analysis_config
                and section == "판매비"
                and (
                    self.analysis_config.is_transport(account)
                    or self.analysis_config.is_transport(short_account)
                )
            )
            is_tariff = "관세" in account
            is_variable = bool(
                self.analysis_config
                and (
                    self.analysis_config.is_variable_sga(account)
                    or self.analysis_config.is_variable_sga(short_account)
                )
            )
            if is_transport:
                classification = "transport"
                profit_effect = 0.0
                bridge_position = "판매효과"
            elif is_tariff:
                classification = "tariff"
                profit_effect = 0.0
                bridge_position = "외부효과/관세"
            else:
                classification = "variable" if is_variable else "fixed"
                profit_effect = base_amount - comparison_amount
                bridge_position = "변동 판관비" if is_variable else "고정 판관비"
            output.append({
                "row": row_number,
                "account": account,
                "section": section,
                "classification": classification,
                "baseline_amount": base_amount,
                "comparison_amount": comparison_amount,
                "delta": delta,
                "profit_effect": profit_effect,
                "bridge_position": bridge_position,
            })
        # Web-entered tariff is outside the Golden Model account range, but is
        # still a deterministic comparison input and must be visible exactly once.
        base_tariff = float(baseline_costs.get("tariff") or 0.0)
        comparison_tariff = float(comparison_costs.get("tariff") or 0.0)
        output.append({
            "row": None,
            "account": "관세(직접입력)",
            "section": "별도분석",
            "classification": "tariff",
            "baseline_amount": base_tariff,
            "comparison_amount": comparison_tariff,
            "delta": comparison_tariff - base_tariff,
            "profit_effect": base_tariff - comparison_tariff,
            "bridge_position": "관세효과",
        })
        return output

    @staticmethod
    def _narrative(
        op_delta: float,
        effects: list[dict[str, Any]],
        residual: float,
    ) -> str:
        direction = "증가" if op_delta >= 0 else "감소"
        ordered = sorted(effects, key=lambda row: abs(float(row["profit_effect"])), reverse=True)
        factors = ", ".join(
            f"{row['factor']} {abs(float(row['profit_effect'])) / 1_000_000:,.0f}백만원"
            for row in ordered[:3] if row["profit_effect"]
        )
        sentences = [
            f"비교 모형의 영업이익은 기준 모형 대비 "
            f"{abs(op_delta) / 1_000_000:,.0f}백만원 {direction}했습니다."
        ]
        if factors:
            sentences.append(f"금액 기준 주요 변동요인은 {factors}입니다.")
        if abs(residual) > 1:
            sentences.append(
                f"세부 효과로 귀속되지 않은 잔여차이는 "
                f"{abs(residual) / 1_000_000:,.0f}백만원입니다."
            )
        return " ".join(sentences)

    @staticmethod
    def _rows(labels: dict[str, str], baseline: dict[str, float], comparison: dict[str, float]) -> list[dict[str, Any]]:
        return [{"code": key, "item": label, "baseline": baseline[key], "comparison": comparison[key],
                 "delta": comparison[key] - baseline[key]} for key, label in labels.items()]

    def _extract(
        self,
        workbook: GoldenWorkbook,
        meta: ModelMeta,
        months: tuple[int, ...],
        *,
        sales_fx: float = 1.0,
    ) -> dict[str, Any]:
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
        sales_groups: dict[str, dict[str, float]] = {}
        for key, spec in self.mapping["sales_groups"].items():
            quantity = total(spec["quantity_row"])
            amount = total(spec["amount_row"])
            cogs = total(spec["cogs_row"])
            sales_groups[key] = {
                "quantity": quantity,
                "amount": amount,
                "cogs": cogs,
                "gross_margin_rate": (amount - cogs) / amount if amount else 0.0,
            }
        production = {key: total(row) for key, row in self.mapping["production_rows"].items()}
        mcm = {key: total(row) for key, row in self.mapping["mcm_rows"].items()}

        def mapped_total(spec: int | list[int] | dict[str, list[int]]) -> float:
            if isinstance(spec, int):
                return total(spec)
            if isinstance(spec, list):
                return sum(total(row) for row in spec)
            added = sum(total(row) for row in spec.get("add", []))
            subtracted = sum(total(row) for row in spec.get("subtract", []))
            return added - subtracted

        adapted = None
        analysis_adapter_error = None
        if hasattr(workbook, "cells"):
            try:
                adapted = self.analysis_adapter.build(
                    workbook, meta, months, sales_fx=sales_fx
                )
            except (KeyError, ValueError) as exc:
                # A legacy or partially uploaded workbook can still be
                # compared by the mapping-driven path. Keep the warning in
                # the extraction payload instead of failing the comparison.
                analysis_adapter_error = str(exc)

        def account_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
            output: list[dict[str, Any]] = []
            for row in rows:
                row_number = int(row["row"])
                output.append({
                    "row": row_number,
                    "account": row["account"],
                    "section": row["section"],
                    "amount": total(row_number),
                })
            return output

        cost_rows = self.mapping["cost_rows"]
        raw_material = mapped_total(cost_rows["raw_material"])
        labor = mapped_total(cost_rows["labor"])
        outsourcing = mapped_total(cost_rows["outsourcing"])
        other_processing = mapped_total(cost_rows["other_processing"])
        tariff = web_tariff
        selling = mapped_total(cost_rows["selling_expense"]) + external_tariff
        general_admin = mapped_total(cost_rows["general_admin"])
        selling_before_tariff = selling - tariff
        cost_summary = {
            "raw_material": raw_material,
            "labor": labor,
            "outsourcing": outsourcing,
            "other_processing": other_processing,
            "processing_total": labor + outsourcing + other_processing,
            "manufacturing_expense": mapped_total(cost_rows["manufacturing_expense"]),
            "selling_expense": selling,
            "general_admin": general_admin,
            "sga_total": selling + general_admin,
            "disposal": mapped_total(cost_rows["disposal"]),
            "obsolescence": mapped_total(cost_rows["obsolescence"]),
            "tariff": tariff,
            "customs_refund": mapped_total(cost_rows["customs_refund"]),
        }
        effect_bases = {
            key: mapped_total(spec)
            for key, spec in self.mapping["effect_rows"].items()
        }
        effect_bases.update({
            "selling_ex_tariff": selling_before_tariff,
            "tariff": tariff,
            "general_admin": general_admin,
        })
        return {"pnl": pnl, "products": products, "sales_groups": sales_groups,
                "production": production, "mcm": mcm,
                "cost_summary": cost_summary, "effect_bases": effect_bases,
                "manufacturing_accounts": [],
                "sga_accounts": account_rows(adapted.sga_source_rows) if adapted else [],
                "adapted": adapted,
                "analysis_adapter_error": analysis_adapter_error}
