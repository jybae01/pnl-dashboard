from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .configuration import AnalysisConfig
from .manufacturing_effects import calculate_manufacturing_effects
from .material_effects import calculate_material_effects
from .schema import (
    ActivityRecord,
    AnalysisScenario,
    CoreManufacturedCogsRecord,
    CurrentCostComponentRecord,
    ExpenseRecord,
    InventoryCostRecord,
    OpeningInventoryUnitRecord,
    PnlRecord,
    ProductRecord,
    ProductionEvidenceRecord,
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

    def __init__(
        self,
        mapping: dict[str, Any],
        config: AnalysisConfig,
        production_evidence_mapping: Mapping[str, Any] | None = None,
    ):
        self.mapping = mapping
        self.adapter = mapping["analysis_adapter"]
        self.comparison = mapping["comparison"]
        self.config = config
        self.production_evidence_mapping = (
            dict(production_evidence_mapping)
            if production_evidence_mapping is not None else None
        )

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
                    "current_cost_component": (
                        "labor" if labor_section else "manufacturing_expense"
                    ),
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
    def _source_reference(column: str, rows: list[int]) -> str:
        return "+".join(f"Data!{column}{int(row)}" for row in rows)

    @staticmethod
    def _material_source_rows(spec: dict[str, Any]) -> list[int]:
        """Return every mapped Golden row that contributes to material cost.

        The returned addresses are evidence metadata only.  The engine still
        consumes canonical values and never depends on a Golden row number.
        """
        rows: list[int] = [int(row) for row in spec.get("direct_material_rows", ())]
        for term in spec.get("front_material_terms", ()):
            for key in (
                "source_production_row", "source_material_amount_row",
                "source_allocation_ratio_row", "adjustment_row",
                "production_row", "input_length_row",
            ):
                if term.get(key):
                    rows.append(int(term[key]))
            rows.extend(int(row) for row in term.get("source_pool_amount_rows", ()))
        for term in spec.get("back_material_terms", ()):
            if term.get("allocation_ratio_row"):
                rows.append(int(term["allocation_ratio_row"]))
            rows.extend(int(row) for row in term.get("pool_amount_rows", ()))
        rows.extend(int(row) for row in spec.get("mcm_material_rows", ()))
        return sorted(set(rows))

    def _inventory_source_validation(
        self,
        workbook: Any,
        months: tuple[int, ...],
    ) -> tuple[str, list[str]]:
        mapping = self.adapter.get("inventory_timing", {})
        issues: list[str] = []
        for code in (
            "current_manufacturing_cost",
            "finished_goods_cogs",
            "semi_finished_goods_cogs",
        ):
            source = mapping.get(code, {})
            row = int(source.get("row") or 0)
            expected = str(source.get("expected_label") or "").strip()
            actual = self._label(workbook, row)
            if not row or not expected or expected not in actual:
                issues.append(f"{code}: expected {expected!r}, found {actual!r} at row {row}")
            for month in months:
                column = self.MONTH_COLUMNS[month]
                value = workbook.value(f"{column}{row}") if row else None
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    issues.append(f"{code}: non-numeric source at Data!{column}{row}")
        for product_group, source in mapping.get("opening_inventory_units", {}).items():
            for kind in ("quantity_rows", "amount_rows"):
                for row in source.get(kind, ()):
                    for month in months:
                        column = self.MONTH_COLUMNS[month]
                        value = workbook.value(f"{column}{int(row)}")
                        if isinstance(value, bool) or not isinstance(value, (int, float)):
                            issues.append(
                                f"{product_group}.{kind}: non-numeric source at Data!{column}{int(row)}"
                            )
        for code, source in mapping.get(
            "current_manufacturing_cost_components", {}
        ).items():
            row = int(source.get("row") or 0)
            expected = str(source.get("expected_label") or "").strip()
            actual = self._label(workbook, row)
            if not row or not expected or expected not in actual:
                issues.append(
                    f"current_cost_component.{code}: expected {expected!r}, "
                    f"found {actual!r} at row {row}"
                )
            for month in months:
                column = self.MONTH_COLUMNS[month]
                value = workbook.value(f"{column}{row}") if row else None
                if value is not None and (
                    isinstance(value, bool) or not isinstance(value, (int, float))
                ):
                    issues.append(
                        f"current_cost_component.{code}: non-numeric source "
                        f"at Data!{column}{row}"
                    )
        for code, relationship in mapping.get(
            "current_manufacturing_cost_formula_relationships", {}
        ).items():
            row = int(relationship.get("row") or 0)
            component_rows = tuple(
                int(item) for item in relationship.get("component_rows", ())
            )
            for month in months:
                column = self.MONTH_COLUMNS[month]
                address = f"{column}{row}"
                expected_precedents = {
                    f"{column}{component_row}" for component_row in component_rows
                }
                actual_precedents = set(workbook.formula_precedents(address))
                if not expected_precedents or actual_precedents != expected_precedents:
                    issues.append(
                        f"current_cost_formula.{code}: expected precedents "
                        f"{sorted(expected_precedents)}, found "
                        f"{sorted(actual_precedents)} at Data!{address}"
                    )
        return ("PASS" if not issues else "FAIL"), issues

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
        sales_fx_source: str = "Analysis request.sales_fx",
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
                sales_quantity_source=f"Data!{column}{spec['sales_quantity_row']}",
                sales_amount_source=(
                    f"Data!{column}{sales_spec['amount_row']}" if sales_spec else "UNMAPPED"
                ),
                product_cogs_source=(
                    f"Data!{column}{sales_spec['cogs_row']}" if sales_spec else "UNMAPPED"
                ),
                production_source=self._source_reference(
                    column, [int(row) for row in spec.get("production_quantity_rows", ())]
                ),
                raw_material_cost_source=self._source_reference(
                    column, self._material_source_rows(spec)
                ),
                nonwoven_cost_source=(
                    f"Data!{column}{front_process['nonwoven_amount_row']}"
                    if group == "FS" else ""
                ),
                nonwoven_output_source=(
                    f"Data!{column}{front_process['nonwoven_quantity_row']}"
                    if group == "FS" else ""
                ),
                nonwoven_input_source=" + ".join(
                    f"Data!{column}{int(term['sales_quantity_row'])}*"
                    f"Data!{column}{int(term['input_length_row'])}"
                    for term in spec.get("nonwoven_input_terms", ())
                ),
                sales_fx_source=sales_fx_source,
                jpy_fx_source=f"Data!{column}{material['jpy_fx_row']}",
                source_validation_status="SOURCE_MAPPED",
            ))
            if mcm_quantity:
                records.append(ProductRecord(
                    year_month=f"{year:04d}-{month:02d}",
                    product_code=f"{group}_MCM",
                    product_group=group,
                    unit_basis="PCS",
                    production_qty=mcm_quantity,
                    sap_production_qty=mcm_quantity,
                    sales_fx=float(sales_fx) if sales_fx else 1.0,
                    nonwoven_output_length=0.0,
                    jpy_fx_krw_per_jpy=jpy,
                    mcm_flag=True,
                    mcm_qty=mcm_quantity,
                    mcm_product_group=group,
                    outsourcing_eligible_flag=False,
                    production_source=self._source_reference(
                        column, [int(row) for row in spec.get("mcm_rows", ())]
                    ),
                    sales_fx_source=sales_fx_source,
                    jpy_fx_source=f"Data!{column}{material['jpy_fx_row']}",
                    source_validation_status="SOURCE_MAPPED",
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
                sales_quantity_source=f"Data!{column}{spec['quantity_row']}",
                sales_amount_source=f"Data!{column}{spec['amount_row']}",
                product_cogs_source=f"Data!{column}{spec['cogs_row']}",
                sales_fx_source=sales_fx_source,
                jpy_fx_source=f"Data!{column}{material['jpy_fx_row']}",
                source_validation_status="SOURCE_MAPPED",
            ))
        return records

    def build(
        self,
        workbook: Any,
        meta: Any,
        months: tuple[int, ...],
        *,
        sales_fx: float | Mapping[str, float] = 1.0,
        sales_fx_source_field: str = "sales_fx",
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
        inventory_costs: list[InventoryCostRecord] = []
        core_manufactured_cogs: list[CoreManufacturedCogsRecord] = []
        current_cost_components: list[CurrentCostComponentRecord] = []
        opening_inventory_units: list[OpeningInventoryUnitRecord] = []
        production_evidence: list[ProductionEvidenceRecord] = []
        pnl: list[PnlRecord] = []
        manufacturing = self.adapter["manufacturing"]
        production_evidence_mapping = self.production_evidence_mapping
        ratio_rows = manufacturing["front_ratio_rows"]
        manufacturing_ratio_sources = {
            item["account"]: int(ratio_rows[item["ratio_key"]])
            for item in manufacturing_accounts
        }
        pnl_rows = self.comparison["pnl_rows"]
        inventory_mapping = self.adapter.get("inventory_timing", {})
        core_cogs_mapping = (
            self.mapping.get("sales_cogs_scope_analysis", {}).get("groups", {})
        )
        source_validation_status, source_validation_issues = (
            self._inventory_source_validation(workbook, months)
        )
        scope_mapping = inventory_mapping.get("scope", {})
        scope_validation_status = (
            "PASS"
            if source_validation_status == "PASS"
            and scope_mapping.get("validation_status") == "PASS"
            else "FAIL"
        )
        scope_notes = (
            "Manufactured COGS includes only product and semi-finished product COGS.",
            "Goods COGS, other COGS, and inventory valuation loss are excluded.",
            "Product/semi-finished adjustment rows remain explicit within their P&L COGS sources.",
            *source_validation_issues,
        )
        for month in months:
            column = self.MONTH_COLUMNS[month]
            year_month = f"{int(meta.year):04d}-{month:02d}"
            if isinstance(sales_fx, Mapping):
                month_sales_fx = float(sales_fx.get(year_month, 1.0))
                month_sales_fx_source = (
                    f"Analysis request input: {sales_fx_source_field}[{year_month}]"
                    if year_month in sales_fx
                    else "NOT_APPLICABLE_OUTSIDE_ANALYSIS_PERIOD"
                )
            else:
                month_sales_fx = float(sales_fx)
                month_sales_fx_source = f"Analysis request input: {sales_fx_source_field}"
            tariff_adjustments = getattr(meta, "tariff_adjustment_monthly", {}) or {}
            tariff_uses_direct_adjustment = bool(tariff_adjustments)
            tariff_regional_sales = (
                None
                if tariff_uses_direct_adjustment
                else self._number(
                    (getattr(meta, "regional_sales_monthly", {}) or {}).get(
                        str(month), 0.0
                    )
                )
            )
            tariff_applicable_rate = (
                None
                if tariff_uses_direct_adjustment
                else self._number(getattr(meta, "tariff_applicable_rate", 0.10))
            )
            tariff_rate = (
                None
                if tariff_uses_direct_adjustment
                else self._number(getattr(meta, "tariff_rate", 0.13))
            )
            month_products = self._material_products(
                workbook, int(meta.year), month, sales_fx=month_sales_fx,
                sales_fx_source=month_sales_fx_source,
            )
            products.extend(month_products)
            for product_group, source in (
                production_evidence_mapping.get("groups", {}).items()
                if production_evidence_mapping is not None else ()
            ):
                quantity_rows = tuple(int(row) for row in source["quantity_rows"])
                amount_rows = tuple(int(row) for row in source["amount_rows"])
                production_evidence.append(ProductionEvidenceRecord(
                    year_month=year_month,
                    product_group=str(product_group),
                    process=str(source["process"]),
                    unit_basis=str(source["unit_basis"]),
                    quantity=sum(
                        self._number(workbook.value(f"{column}{row}"))
                        for row in quantity_rows
                    ),
                    amount=sum(
                        self._number(workbook.value(f"{column}{row}"))
                        for row in amount_rows
                    ),
                    quantity_source=self._source_reference(column, list(quantity_rows)),
                    amount_source=self._source_reference(column, list(amount_rows)),
                    quantity_source_rows=quantity_rows,
                    amount_source_rows=amount_rows,
                    aggregation_basis=str(source["aggregation_basis"]),
                    formula_policy=str(production_evidence_mapping["formula_policy"]),
                ))
            for product_group in ("SW", "BW", "LC", "FS"):
                core_source = dict(core_cogs_mapping.get(product_group) or {})
                quantity_row = int(core_source.get("quantity_row") or 0)
                core_rows = [
                    int(row)
                    for row in core_source.get("matched_manufactured_cogs_rows", ())
                ]
                core_manufactured_cogs.append(CoreManufacturedCogsRecord(
                    year_month=year_month,
                    product_group=product_group,
                    pool=(
                        "LENGTH"
                        if core_source.get("unit_basis") == "LENGTH" else "PCS"
                    ),
                    unit=(
                        "m" if core_source.get("unit_basis") == "LENGTH" else "PCS"
                    ),
                    sales_quantity=self._number(
                        workbook.value(f"{column}{quantity_row}")
                        if quantity_row else 0.0
                    ),
                    core_manufactured_cogs=sum(
                        self._number(workbook.value(f"{column}{row}"))
                        for row in core_rows
                    ),
                    quantity_source=(
                        f"Data!{column}{quantity_row}" if quantity_row else "UNMAPPED"
                    ),
                    core_cogs_source=(
                        self._source_reference(column, core_rows)
                        if core_rows else "UNMAPPED"
                    ),
                    source_validation_status=(
                        "SOURCE_MAPPED" if quantity_row and core_rows else "UNMAPPED"
                    ),
                    scope_validation_status=(
                        "CORE_ONLY"
                        if quantity_row and core_rows else "UNMAPPED"
                    ),
                ))
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
                    current_cost_component=str(
                        source.get("current_cost_component") or ""
                    ),
                    business_source=account,
                    amount_source=f"Data!{column}{row}",
                    front_ratio_source=(
                        f"Data!{column}{int(ratio_rows[source['ratio_key']])}"
                    ),
                    source_validation_status="SOURCE_MAPPED",
                ))
            current_source = inventory_mapping.get("current_manufacturing_cost", {})
            finished_source = inventory_mapping.get("finished_goods_cogs", {})
            semi_source = inventory_mapping.get("semi_finished_goods_cogs", {})
            current_row = int(current_source.get("row") or 0)
            finished_row = int(finished_source.get("row") or 0)
            semi_row = int(semi_source.get("row") or 0)
            manufacturing_input = self._number(
                workbook.value(f"{column}{current_row}") if current_row else 0.0
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
                manufacturing_input_cost=manufacturing_input,
                tariff_input=self._monthly_tariff(meta, month),
                tariff_in_transport=bool(getattr(meta, "tariff_in_workbook", False)),
                tariff_regional_sales=tariff_regional_sales,
                tariff_applicable_rate=tariff_applicable_rate,
                tariff_rate=tariff_rate,
                tariff_effective_rate=(
                    tariff_applicable_rate * tariff_rate
                    if tariff_applicable_rate is not None and tariff_rate is not None
                    else None
                ),
                tariff_calculation_source=(
                    "Scenario metadata.tariff_adjustment_monthly"
                    if tariff_uses_direct_adjustment
                    else (
                        "Scenario metadata.regional_sales_monthly × "
                        "tariff_applicable_rate × tariff_rate"
                    )
                ),
                front_activity_source=self._source_reference(
                    column, [int(row) for row in manufacturing["front_activity_rows"]]
                ),
                back_activity_source=self._source_reference(
                    column, [int(row) for row in manufacturing["back_activity_rows"]]
                ),
                manufacturing_input_cost_source=(
                    f"Data!{column}{current_row}" if current_row else "UNMAPPED"
                ),
                tariff_input_source=(
                    "Golden workbook transport account (tariff included)"
                    if getattr(meta, "tariff_in_workbook", False)
                    else (
                        "Scenario metadata.tariff_adjustment_monthly"
                        if tariff_uses_direct_adjustment
                        else (
                            "Scenario metadata.regional_sales_monthly × "
                            "tariff_applicable_rate × tariff_rate"
                        )
                    )
                ),
                source_validation_status="SOURCE_MAPPED",
            ))
            inventory_costs.append(InventoryCostRecord(
                year_month=year_month,
                current_manufacturing_cost=manufacturing_input,
                finished_goods_cogs=self._number(
                    workbook.value(f"{column}{finished_row}") if finished_row else 0.0
                ),
                semi_finished_goods_cogs=self._number(
                    workbook.value(f"{column}{semi_row}") if semi_row else 0.0
                ),
                current_manufacturing_cost_source=(
                    f"Data!{column}{current_row}" if current_row else "UNMAPPED"
                ),
                finished_goods_cogs_source=(
                    f"Data!{column}{finished_row}" if finished_row else "UNMAPPED"
                ),
                semi_finished_goods_cogs_source=(
                    f"Data!{column}{semi_row}" if semi_row else "UNMAPPED"
                ),
                source_validation_status=source_validation_status,
                scope_validation_status=scope_validation_status,
                scope_notes=scope_notes,
            ))
            for component_code, component_source in inventory_mapping.get(
                "current_manufacturing_cost_components", {}
            ).items():
                component_row = int(component_source.get("row") or 0)
                component_address = f"{column}{component_row}"
                current_cost_components.append(CurrentCostComponentRecord(
                    year_month=year_month,
                    component_code=str(component_code),
                    business_source=str(
                        component_source.get("business_source") or component_code
                    ),
                    category=str(component_source.get("category") or ""),
                    existing_effect_basis=str(
                        component_source.get("existing_effect_basis") or ""
                    ),
                    amount=self._number(
                        workbook.value(component_address) if component_row else 0.0
                    ),
                    source_reference=(
                        f"Data!{component_address}" if component_row else "UNMAPPED"
                    ),
                    source_formula=str(
                        workbook.formulas.get(component_address, "")
                    ),
                    source_validation_status=source_validation_status,
                ))
            for product_group in ("FS", "SW", "BW", "LC"):
                unit_source = inventory_mapping.get("opening_inventory_units", {}).get(
                    product_group, {}
                )
                quantity_rows = [int(row) for row in unit_source.get("quantity_rows", ())]
                amount_rows = [int(row) for row in unit_source.get("amount_rows", ())]
                quantity = sum(
                    self._number(workbook.value(f"{column}{row}"))
                    for row in quantity_rows
                )
                amount = sum(
                    self._number(workbook.value(f"{column}{row}"))
                    for row in amount_rows
                )
                opening_inventory_units.append(OpeningInventoryUnitRecord(
                    year_month=year_month,
                    product_group=product_group,
                    unit_basis=str(unit_source.get("unit_basis") or ""),
                    specification=str(unit_source.get("specification") or ""),
                    quantity=quantity,
                    amount=amount,
                    unit_cost=(amount / quantity if quantity else None),
                    quantity_source=self._source_reference(column, quantity_rows),
                    amount_source=self._source_reference(column, amount_rows),
                    coverage="LIMITED",
                ))
            for source in sga_rows:
                account = str(source["account"])
                section = str(source.get("section") or "")
                # Selling transport drives the canonical customer-delivery
                # transport effect; no PCS/LENGTH activity denominator exists
                # in V1.  The raw source row is retained for the detail table.
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
                    business_source=f"{section} / {account}",
                    amount_source=f"Data!{column}{int(source['row'])}",
                    source_validation_status="SOURCE_MAPPED",
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
            inventory_costs=inventory_costs,
            core_manufactured_cogs=core_manufactured_cogs,
            current_cost_components=current_cost_components,
            opening_inventory_units=opening_inventory_units,
            production_evidence=production_evidence,
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
            "trace_rows": list(result.details),
            "nonwoven_trace_rows": list(result.nonwoven_details),
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
                "current_cost_component": detail.get("current_cost_component", ""),
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
            row["inventory_realization_reference_only"] = True
            row["final_profit_effect"] = row["occurrence_effect"]
            row["calculation_status"] = (
                " / ".join(sorted(statuses))
                + " / 재고실현율 참고지표(Effect multiplier 미적용)"
            )
            output.append(row)
        analysis = {
            "activity_effect": sum(row["activity_effect"] for row in output),
            "unit_effect": sum(row["unit_effect"] for row in output),
            "fixed_effect": sum(row["fixed_effect"] for row in output),
            "occurrence_effect": sum(row["occurrence_effect"] for row in output),
            "inventory_realization_rate": realization_rate,
            "inventory_realization_reference_only": True,
            "final_effect": sum(
                self._number(row["final_profit_effect"]) for row in output
            ),
            "issues": list(calculated.issues),
            "allocation_policy": "기준 모형 345~347행 전공정 가공비 투입비율을 기준·비교 양쪽에 동일 적용",
            "trace_rows": list(calculated.details),
            "production_reconciliation": list(calculated.production_reconciliation),
            "realization_details": list(calculated.realization_details),
        }
        return output, analysis
