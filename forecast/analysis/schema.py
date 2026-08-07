from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Iterable


@dataclass(frozen=True)
class ScenarioMeta:
    scenario_id: str
    scenario_type: str
    version: str


@dataclass(frozen=True)
class ProductRecord:
    year_month: str
    product_code: str
    product_group: str
    unit_basis: str = "PCS"
    sales_qty: float = 0.0
    sales_length: float = 0.0
    sales_amount: float = 0.0
    product_cogs: float = 0.0
    production_qty: float = 0.0
    production_length: float = 0.0
    sap_production_qty: float | None = None
    sap_production_length: float | None = None
    mes_production_qty: float | None = None
    mes_production_length: float | None = None
    raw_material_cost: float = 0.0
    nonwoven_cost: float = 0.0
    nonwoven_output_length: float | None = None
    nonwoven_sales_input_length: float = 0.0
    sales_fx: float = 1.0
    jpy_fx: float = 0.0
    jpy_fx_krw_per_jpy: float | None = None
    sales_currency: str = "KRW"
    mcm_flag: bool = False
    mcm_qty: float = 0.0
    mcm_issue_amount: float = 0.0
    mcm_product_group: str = ""
    outsourcing_eligible_flag: bool = True

    @property
    def sales_basis(self) -> float:
        return self.sales_length if self.unit_basis.upper() == "LENGTH" else self.sales_qty

    @property
    def production_basis(self) -> float:
        if self.unit_basis.upper() == "LENGTH":
            return self.sap_production_length if self.sap_production_length is not None else self.production_length
        return self.sap_production_qty if self.sap_production_qty is not None else self.production_qty

    @property
    def sap_qty(self) -> float:
        return self.sap_production_qty if self.sap_production_qty is not None else self.production_qty

    @property
    def sap_length(self) -> float:
        return self.sap_production_length if self.sap_production_length is not None else self.production_length

    @property
    def mes_qty(self) -> float | None:
        return self.mes_production_qty

    @property
    def mes_length(self) -> float | None:
        return self.mes_production_length

    @property
    def effective_jpy_fx(self) -> float:
        return self.jpy_fx_krw_per_jpy if self.jpy_fx_krw_per_jpy is not None else self.jpy_fx


@dataclass(frozen=True)
class ExpenseRecord:
    year_month: str
    account: str
    amount: float
    category: str
    front_ratio: float = 0.0
    back_ratio: float = 0.0


@dataclass(frozen=True)
class ActivityRecord:
    year_month: str
    front_activity: float = 0.0
    back_activity: float = 0.0
    transport_activity: float = 0.0
    manufacturing_input_cost: float = 0.0
    inventory_realization_rate: float | None = None
    tariff_input: float = 0.0
    tariff_in_transport: bool = True
    labor_front_ratio: float | None = None
    outsourcing_front_ratio: float | None = None
    other_expense_front_ratio: float | None = None


@dataclass(frozen=True)
class PnlRecord:
    year_month: str
    revenue: float
    cogs: float
    operating_profit: float


@dataclass(frozen=True)
class DirectEffectRecord:
    year_month: str
    code: str
    label: str
    amount: float


@dataclass
class AnalysisScenario:
    meta: ScenarioMeta
    products: list[ProductRecord] = field(default_factory=list)
    manufacturing_expenses: list[ExpenseRecord] = field(default_factory=list)
    sga_expenses: list[ExpenseRecord] = field(default_factory=list)
    activities: list[ActivityRecord] = field(default_factory=list)
    pnl: list[PnlRecord] = field(default_factory=list)
    direct_effects: list[DirectEffectRecord] = field(default_factory=list)

    @property
    def months(self) -> tuple[str, ...]:
        sources: Iterable[Iterable[Any]] = (
            self.products,
            self.manufacturing_expenses,
            self.sga_expenses,
            self.activities,
            self.pnl,
            self.direct_effects,
        )
        return tuple(sorted({row.year_month for source in sources for row in source}))

    def select(self, months: Iterable[str]) -> "AnalysisScenario":
        selected = set(months)
        return AnalysisScenario(
            meta=self.meta,
            products=[row for row in self.products if row.year_month in selected],
            manufacturing_expenses=[row for row in self.manufacturing_expenses if row.year_month in selected],
            sga_expenses=[row for row in self.sga_expenses if row.year_month in selected],
            activities=[row for row in self.activities if row.year_month in selected],
            pnl=[row for row in self.pnl if row.year_month in selected],
            direct_effects=[row for row in self.direct_effects if row.year_month in selected],
        )

    def to_common_tables(self) -> dict[str, list[dict[str, Any]]]:
        common = asdict(self.meta)

        def rows(items: Iterable[Any]) -> list[dict[str, Any]]:
            return [{**common, **asdict(item)} for item in items]

        return {
            "products": rows(self.products),
            "manufacturing_expenses": [
                {
                    **common,
                    "year_month": item.year_month,
                    "manufacturing_expense_account": item.account,
                    "manufacturing_expense_amount": item.amount,
                    "allocation_ratios": {"front": item.front_ratio, "back": item.back_ratio},
                    "front_ratio": item.front_ratio,
                    "back_ratio": item.back_ratio,
                }
                for item in self.manufacturing_expenses
            ],
            "sga_expenses": [
                {
                    **common,
                    "year_month": item.year_month,
                    "sga_account": item.account,
                    "sga_amount": item.amount,
                }
                for item in self.sga_expenses
            ],
            "activities": rows(self.activities),
            "pnl": rows(self.pnl),
            "direct_effects": rows(self.direct_effects),
        }
