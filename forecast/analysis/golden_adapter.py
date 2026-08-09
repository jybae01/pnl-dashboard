from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .configuration import AnalysisConfig
from .manufacturing_effects import calculate_manufacturing_effects
from .material_effects import calculate_material_effects
from .schema import (
    ActivityRecord,
    AnalysisScenario,
    ExpenseRecord,
    PnlRecord,
    ProductRecord,
    ScenarioMeta,
)


@dataclass(frozen=True)
class AdaptedGoldenScenario:
    scenario: AnalysisScenario
    manufacturing_source_rows: dict[str, int]
    manufacturing_ratio_rows: dict[str, int]
    sga_source_rows: list[dict[str, Any]]


class GoldenAnalysisAdapter:
    """Read named V1 analysis inputs from a Golden Model workbook.

    Cell locations live exclusively in ``config/model_mapping.json``.  The
    comparison engine receives normalized records and never asks Streamlit to
    read workbook cells or calculate an effect.
    """

    MONTH_COLUMNS = {month: chr(ord("E") + month - 1) for month in range(1, 13)}

    def __init__(self, mapping: dict[str, Any], config: AnalysisConfig):
        self.mapping = mapping
        self.adapter = mapping["analysis_adapter"]
        self.comparison = mapping["comparison"]
        self.config = config

    @staticmethod
    def _number(value: Any) -> float:
        try:
            return float(value or 0.0)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _max_row(workbook: Any) -> int:
        rows = []
        for address in workbook.cells:
            digits = "".join(character for character in address if character.isdigit())
            if digits:
                rows.append(int(digits))
        return max(rows, default=0)

    @staticmethod
    def _label(workbook: Any, row: int, columns: str = "DCBA") -> str:
        reader = getattr(workbook, "raw_value", workbook.value)
        for column in columns:
            value = reader(f"{column}{row}")
            if value not in (None, "", 0):
                return str(value).strip()
        return ""

    def _find_marker(self, workbook: Any, marker: str) -> int:
        reader = getattr(workbook, "raw_value", workbook.value)
        for row in range(1, self._max_row(workbook) + 1):
            values = " ".join(
                str(reader(f"{column}{row}") or "").strip()
                for column in "ABCD"
            )
            if marker in values:
                return row
        raise ValueError(f"Golden Model marker not found: {marker}")

    def discover_manufacturing_accounts(self, workbook: Any) -> list[dict[str, Any]]:
        settings = self.adapter["account_discovery"]
        start = self._find_marker(workbook, settings["manufacturing_start_marker"])
        stop = self._find_marker(workbook, settings["manufacturing_stop_marker"])
        excluded = set(settings.get("manufacturing_excluded_labels", ()))
        reader = getattr(workbook, "raw_value", workbook.value)
        labor_section = False
        rows: list[dict[str, Any]] = []
        for row in range(start + 1, stop):
            column_c = str(reader(f"C{row}") or "").strip()
            column_d = str(reader(f"D{row}") or "").strip()
            if column_c == "노무비" and not column_d:
                labor_section = True
                continue
            if column_c == "제조경비" and not column_d:
                labor_section = False
                continue
            if not column_d or column_d in excluded:
                continue
            classification = column_c if column_c in {"변동비", "고정비"} else None
            if labor_section and classification is None:
                classification = "고정비"
            if classification:
                account = column_d
                ratio_key = (
                    "labor" if labor_section
                    else "outsourcing" if self.config.is_outsourcing(account)
                    else "other_variable"
                )
                rows.append({
                    "row": row,
                    "account": account,
                    "source_classification": classification,
                    "ratio_key": ratio_key,
                })
        return rows

    def discover_manufacturing_rows(self, workbook: Any) -> list[int]:
        """Backward-compatible row-only view used by mapping regression tests."""
        return [item["row"] for item in self.discover_manufacturing_accounts(workbook)]

    def discover_sga_rows(self, workbook: Any) -> list[dict[str, Any]]:
        settings = self.adapter["account_discovery"]
        start = self._find_marker(workbook, settings["sga_start_marker"])
        stop = self._find_marker(workbook, settings["sga_stop_marker"])
        reader = getattr(workbook, "raw_value", workbook.value)
        section: str | None = None
        rows: list[dict[str, Any]] = []
        for row in range(start + 1, stop):
            column_b = str(reader(f"B{row}") or "").strip()
            column_c = str(reader(f"C{row}") or "").strip()
            if column_b in {"판매비", "일반관리비"}:
                section = column_b
                continue
            if column_b in {"변동비", "고정비"} and column_c and section:
                rows.append({
                    "row": row,
                    "account": column_c,
                    "section": section,
                    "source_classification": column_b,
                })
        return rows

    def _mapped_value(self, workbook: Any, column: str, spec: Any) -> float:
        if isinstance(spec, int):
            return self._number(workbook.value(f"{column}{spec}"))
        if isinstance(spec, list):
            return sum(self._mapped_value(workbook, column, row) for row in spec)
        if isinstance(spec, dict):
            return (
                sum(self._mapped_value(workbook, column, row) for row in spec.get("add", ()))
                - sum(self._mapped_value(workbook, column, row) for row in spec.get("subtract", ()))
            )
        return 0.0

    def _material_cost(self, workbook: Any, column: str, spec: dict[str, Any]) -> float:
        total = sum(
            self._number(workbook.value(f"{column}{row}"))
            for row in spec.get("direct_material_rows", ())
        )
        for term in spec.get("front_material_terms", ()):
            source_quantity = self._number(
                workbook.value(f"{column}{term['source_production_row']}")
            )
            if not source_quantity:
                continue
            source_amount = sum(
                self._number(workbook.value(f"{column}{row}"))
                for row in term.get("source_pool_amount_rows", ())
            )
            if "source_material_amount_row" in term:
                source_amount += self._number(
                    workbook.value(f"{column}{term['source_material_amount_row']}")
                )
            allocation_ratio = (
                self._number(workbook.value(
                    f"{column}{term['source_allocation_ratio_row']}"
                ))
                if term.get("source_allocation_ratio_row") else 1.0
            )
            source_unit = source_amount * allocation_ratio / source_quantity
            adjustment = self._number(
                workbook.value(f"{column}{term['adjustment_row']}")
            )
            total += (
                self._number(workbook.value(f"{column}{term['production_row']}"))
                * self._number(workbook.value(f"{column}{term['input_length_row']}"))
                * source_unit
                * adjustment
            )
        for term in spec.get("back_material_terms", ()):
            allocation_ratio = self._number(
                workbook.value(f"{column}{term['allocation_ratio_row']}")
            )
            pool_amount = sum(
                self._number(workbook.value(f"{column}{row}"))
                for row in term.get("pool_amount_rows", ())
            )
            total += allocation_ratio * pool_amount
        total += sum(
            self._number(workbook.value(f"{column}{row}"))
            for row in spec.get("mcm_material_rows", ())
        )
        return total

    @staticmethod
    def _monthly_tariff(meta: Any, month: int) -> float:
        """Return the direct tariff input for one Golden Model month."""
        monthly = getattr(meta, "tariff_adjustment_monthly", {}) or {}
        if monthly:
            return GoldenAnalysisAdapter._number(monthly.get(str(month), 0.0))
        regional = getattr(meta, "regional_sales_monthly", {}) or {}
        sales = GoldenAnalysisAdapter._number(regional.get(str(month), 0.0))
        applicable = GoldenAnalysisAdapter._number(
            getattr(meta, "tariff_applicable_rate", 0.10)
        )
        rate = GoldenAnalysisAdapter._number(getattr(meta, "tariff_rate", 0.13))
        return sales * applicable * rate

    def _material_products(
        self,
        workbook: Any,
        year: int,
        month: int,
        *,
        sales_fx: float = 1.0,
    ) -> list[ProductRecord]:
        column = self.MONTH_COLUMNS[month]
        material = self.adapter["material"]
        front_process = material["front_process"]
        nonwoven_output = self._number(
            workbook.value(f"{column}{front_process['nonwoven_quantity_row']}")
        )
        nonwoven_cost = self._number(
            workbook.value(f"{column}{front_process['nonwoven_amount_row']}")
        )
        jpy = self._number(workbook.value(f"{column}{material['jpy_fx_row']}"))
        sales_groups = self.comparison.get("sales_groups", {})
        records: list[ProductRecord] = []
        for group, spec in material["groups"].items():
            unit_basis = str(spec["unit_basis"])
            sales = self._number(workbook.value(f"{column}{spec['sales_quantity_row']}"))
            sales_spec = sales_groups.get(group, {})
            sales_amount = self._number(
                workbook.value(f"{column}{sales_spec['amount_row']}")
            ) if sales_spec else 0.0
            product_cogs = self._number(
                workbook.value(f"{column}{sales_spec['cogs_row']}")
            ) if sales_spec else 0.0
            production = sum(
                self._number(workbook.value(f"{column}{row}"))
                for row in spec.get("production_quantity_rows", ())
            )
            mcm_quantity = sum(
                self._number(workbook.value(f"{column}{row}"))
                for row in spec.get("mcm_rows", ())
            )
            core_production = max(production - mcm_quantity, 0.0)
            nonwoven_input = sum(
                self._number(workbook.value(f"{column}{term['sales_quantity_row']}"))
                * self._number(workbook.value(f"{column}{term['input_length_row']}"))
                for term in spec.get("nonwoven_input_terms", ())
            )
            raw_material_cost = self._material_cost(workbook, column, spec)
            is_length = unit_basis.upper() == "LENGTH"
            records.append(ProductRecord(
                year_month=f"{year:04d}-{month:02d}",
                product_code=f"{group}_CORE",
                product_group=group,
                unit_basis=unit_basis,
                sales_qty=0.0 if is_length else sales,
                sales_length=sales if is_length else 0.0,
                production_qty=0.0 if is_length else core_production,
                production_length=core_production if is_length else 0.0,
                sap_production_qty=None if is_length else core_production,
                sap_production_length=core_production if is_length else None,
                sales_amount=sales_amount,
                product_cogs=product_cogs,
                raw_material_cost=raw_material_cost,
                nonwoven_cost=nonwoven_cost if group == "FS" else 0.0,
                nonwoven_output_length=nonwoven_output if group == "FS" else 0.0,
                nonwoven_sales_input_length=nonwoven_input,
                sales_fx=float(sales_fx) if sales_fx else 1.0,
                jpy_fx_krw_per_jpy=jpy,
            ))
            if mcm_quantity:
                records.append(ProductRecord(
                    year_month=f"{year:04d}-{month:02d}",
                    product_code=f"{group}_MCM",
                    product_group=group,
                    unit_basis="PCS",
                    production_qty=mcm_quantity,
                    sap_production_qty=mcm_quantity,
                    nonwoven_output_length=0.0,
                    jpy_fx_krw_per_jpy=jpy,
                    mcm_flag=True,
                    mcm_qty=mcm_quantity,
                    mcm_product_group=group,
                    outsourcing_eligible_flag=False,
                ))
        # The material mapping covers SW/BW/LC/FS. Keep any remaining
        # configured sales group (currently 신사업) in the common schema as a
        # sales-only record so it participates in sales effects without
        # inventing production or material costs.
        material_groups = set(material["groups"])
        for group, spec in sales_groups.items():
            product_group = str(spec.get("label") or group)
            if group in material_groups or product_group in material_groups:
                continue
            sales = self._number(workbook.value(f"{column}{spec['quantity_row']}"))
            records.append(ProductRecord(
                year_month=f"{year:04d}-{month:02d}",
                product_code=f"{product_group}_SALES",
                product_group=product_group,
                unit_basis="PCS",
                sales_qty=sales,
                sales_amount=self._number(workbook.value(f"{column}{spec['amount_row']}")),
                product_cogs=self._number(workbook.value(f"{column}{spec['cogs_row']}")),
                sales_fx=float(sales_fx) if sales_fx else 1.0,
                jpy_fx_krw_per_jpy=jpy,
                material_applicable_flag=False,
            ))
        return records

    def build(
        self,
        workbook: Any,
        meta: Any,
        months: tuple[int, ...],
        *,
        sales_fx: float = 1.0,
    ) -> AdaptedGoldenScenario:
        manufacturing_accounts = self.discover_manufacturing_accounts(workbook)
        sga_rows = self.discover_sga_rows(workbook)
        manufacturing_sources = {
            item["account"]: item["row"] for item in manufacturing_accounts
        }
        products: list[ProductRecord] = []
        manufacturing_expenses: list[ExpenseRecord] = []
        sga_expenses: list[ExpenseRecord] = []
        activities: list[ActivityRecord] = []
        pnl: list[PnlRecord] = []
        manufacturing = self.adapter["manufacturing"]
        ratio_rows = manufacturing["front_ratio_rows"]
        manufacturing_ratio_sources = {
            item["account"]: int(ratio_rows[item["ratio_key"]])
            for item in manufacturing_accounts
        }
        cost_rows = self.comparison["cost_rows"]
        pnl_rows = self.comparison["pnl_rows"]
        for month in months:
            column = self.MONTH_COLUMNS[month]
            year_month = f"{int(meta.year):04d}-{month:02d}"
            month_products = self._material_products(
                workbook, int(meta.year), month, sales_fx=sales_fx
            )
            products.extend(month_products)
            for source in manufacturing_accounts:
                row = int(source["row"])
                account = str(source["account"])
                front_ratio = self._number(
                    workbook.value(f"{column}{ratio_rows[source['ratio_key']]}")
                )
                manufacturing_expenses.append(ExpenseRecord(
                    year_month=year_month,
                    account=account,
                    amount=self._number(workbook.value(f"{column}{row}")),
                    category="manufacturing",
                    front_ratio=front_ratio,
                    back_ratio=1.0 - front_ratio,
                ))
            manufacturing_input = sum(
                self._mapped_value(workbook, column, cost_rows[code])
                for code in ("raw_material", "labor", "outsourcing", "other_processing")
            )
            activities.append(ActivityRecord(
                year_month=year_month,
                front_activity=sum(
                    self._number(workbook.value(f"{column}{row}"))
                    for row in manufacturing["front_activity_rows"]
                ),
                back_activity=sum(
                    self._number(workbook.value(f"{column}{row}"))
                    for row in manufacturing["back_activity_rows"]
                ),
                transport_activity=sum(row.sales_basis for row in month_products),
                manufacturing_input_cost=manufacturing_input,
                tariff_input=self._monthly_tariff(meta, month),
                tariff_in_transport=bool(getattr(meta, "tariff_in_workbook", False)),
            ))
            for source in sga_rows:
                account = str(source["account"])
                section = str(source.get("section") or "")
                # Selling transport drives the sales-price transport split;
                # same-named general-admin transport remains fixed SGA. Encode
                # the section only in the normalized account, retaining the
                # raw source row for the existing UI detail table.
                account_for_analysis = (
                    f"{section}_{account}"
                    if self.config.is_transport(account)
                    else account
                )
                sga_expenses.append(ExpenseRecord(
                    year_month=year_month,
                    account=account_for_analysis,
                    amount=self._number(workbook.value(f"{column}{source['row']}")),
                    category="sga",
                ))
            external_tariff = (
                0.0
                if getattr(meta, "tariff_in_workbook", False)
                else self._monthly_tariff(meta, month)
            )
            pnl.append(PnlRecord(
                year_month=year_month,
                revenue=self._number(workbook.value(f"{column}{pnl_rows['revenue']}")),
                cogs=self._number(workbook.value(f"{column}{pnl_rows['cogs']}")),
                operating_profit=self._number(
                    workbook.value(f"{column}{pnl_rows['operating_profit']}")
                ) - external_tariff,
            ))
        scenario = AnalysisScenario(
            meta=ScenarioMeta(
                scenario_id=str(meta.id),
                scenario_type=str(meta.model_type),
                version=str(meta.version),
            ),
            products=products,
            manufacturing_expenses=manufacturing_expenses,
            sga_expenses=sga_expenses,
            activities=activities,
            pnl=pnl,
        )
        return AdaptedGoldenScenario(
            scenario,
            manufacturing_sources,
            manufacturing_ratio_sources,
            sga_rows,
        )

    @staticmethod
    def material_analysis(
        baseline: AdaptedGoldenScenario,
        comparison: AdaptedGoldenScenario,
    ) -> dict[str, Any]:
        result = calculate_material_effects(baseline.scenario, comparison.scenario)
        groups: list[dict[str, Any]] = []
        for group in sorted(result.by_product_group_details):
            detail = result.by_product_group_details.get(group)
            if not detail:
                continue
            base_output = detail["baseline_output"]
            comparison_output = detail["comparison_output"]
            errors = bool(detail["calculation_errors"])
            groups.append({
                "product_group": group,
                "baseline_unit_cost": (
                    detail["baseline_cost"] / base_output if base_output else None
                ),
                "comparison_unit_cost": (
                    detail["comparison_cost"] / comparison_output
                    if comparison_output else None
                ),
                "unit_cost_delta": (
                    detail["comparison_cost"] / comparison_output
                    - detail["baseline_cost"] / base_output
                    if base_output and comparison_output else None
                ),
                "nonwoven_price_ex_fx": detail["nonwoven_price_ex_fx"],
                "nonwoven_jpy": detail["nonwoven_jpy"],
                "materials_ex_nonwoven": detail["materials_ex_nonwoven"],
                "total": detail["total"],
                "calculation_status": "CHECK: 생산출고 분모 0" if errors else "완료",
            })
        return {
            "product_groups": groups,
            "total": result.total,
            "nonwoven_price_ex_fx": result.nonwoven_price_ex_fx,
            "nonwoven_jpy": result.nonwoven_jpy,
            "materials_ex_nonwoven": result.materials_ex_nonwoven,
            "calculation_status": "CHECK" if result.issues else "완료",
            "issues": list(result.issues),
            "jpy_fx_unit": "KRW/JPY",
        }

    def manufacturing_accounts(
        self,
        baseline: AdaptedGoldenScenario,
        comparison: AdaptedGoldenScenario,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        calculated = calculate_manufacturing_effects(
            baseline.scenario, comparison.scenario, self.config
        )
        aggregated: dict[str, dict[str, Any]] = {}
        for detail in calculated.details:
            account = str(detail["account"])
            row = aggregated.setdefault(account, {
                "row": comparison.manufacturing_source_rows.get(
                    account, baseline.manufacturing_source_rows.get(account)
                ),
                "account": account,
                "classification": detail["classification"],
                "baseline_amount": 0.0,
                "comparison_amount": 0.0,
                "delta": 0.0,
                "activity_effect": 0.0,
                "unit_effect": 0.0,
                "fixed_effect": 0.0,
                "occurrence_effect": 0.0,
                "front_ratios": set(),
                "statuses": set(),
            })
            for key in (
                "baseline_amount", "comparison_amount", "delta",
                "activity_effect", "unit_effect", "fixed_effect", "occurrence_effect",
            ):
                row[key] += self._number(detail.get(key))
            row["statuses"].add(str(detail.get("calculation_status") or "완료"))
            row["front_ratios"].add(self._number(detail.get("front_ratio_base")))

        comparison_cogs = sum(row.cogs for row in comparison.scenario.pnl)
        manufacturing_input = sum(
            row.manufacturing_input_cost for row in comparison.scenario.activities
        )
        realization_rate = comparison_cogs / manufacturing_input if manufacturing_input else None
        output: list[dict[str, Any]] = []
        for account in sorted(
            aggregated,
            key=lambda name: aggregated[name]["row"] or 10**9,
        ):
            row = aggregated[account]
            statuses = row.pop("statuses")
            front_ratios = sorted(row.pop("front_ratios"))
            row["baseline_front_ratios"] = front_ratios
            row["allocation_ratio_row"] = comparison.manufacturing_ratio_rows.get(
                account, baseline.manufacturing_ratio_rows.get(account)
            )
            row["inventory_realization_rate"] = realization_rate
            row["final_profit_effect"] = (
                row["occurrence_effect"] * realization_rate
                if realization_rate is not None else None
            )
            row["calculation_status"] = (
                " / ".join(sorted(statuses))
                if realization_rate is not None
                else "CHECK: 당기투입 제조원가 분모 0"
            )
            output.append(row)
        analysis = {
            "activity_effect": sum(row["activity_effect"] for row in output),
            "unit_effect": sum(row["unit_effect"] for row in output),
            "fixed_effect": sum(row["fixed_effect"] for row in output),
            "occurrence_effect": sum(row["occurrence_effect"] for row in output),
            "inventory_realization_rate": realization_rate,
            "final_effect": sum(
                self._number(row["final_profit_effect"]) for row in output
            ),
            "issues": list(calculated.issues),
            "allocation_policy": "기준 모형 345~347행 전공정 가공비 투입비율을 기준·비교 양쪽에 동일 적용",
        }
        return output, analysis
