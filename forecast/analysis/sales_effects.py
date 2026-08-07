from __future__ import annotations

from dataclasses import dataclass, field

from .configuration import AnalysisConfig
from .schema import AnalysisScenario, ProductRecord


@dataclass
class SalesEffects:
    quantity: float = 0.0
    mix: float = 0.0
    price: float = 0.0
    displayed_price: float = 0.0
    sales_fx: float = 0.0
    transport_quantity: float = 0.0
    transport_unit: float = 0.0
    tariff: float = 0.0
    issues: list[str] = field(default_factory=list)

    @property
    def total(self) -> float:
        return self.quantity + self.mix + self.price + self.sales_fx + self.tariff


def _product_map(scenario: AnalysisScenario) -> dict[tuple[str, str], ProductRecord]:
    result: dict[tuple[str, str], ProductRecord] = {}
    for row in scenario.products:
        key = (row.year_month, row.product_code)
        if key in result:
            raise ValueError(f"중복 제품 레코드: {row.year_month} / {row.product_code}")
        result[key] = row
    return result


def _expense_by_month(scenario: AnalysisScenario, config: AnalysisConfig) -> dict[str, float]:
    result: dict[str, float] = {}
    for row in scenario.sga_expenses:
        if config.is_transport(row.account):
            result[row.year_month] = result.get(row.year_month, 0.0) + float(row.amount)
    return result


def _activities(scenario: AnalysisScenario):
    return {row.year_month: row for row in scenario.activities}


def calculate_sales_effects(
    base: AnalysisScenario,
    comparison: AnalysisScenario,
    config: AnalysisConfig,
) -> SalesEffects:
    result = SalesEffects()
    left = _product_map(base)
    right = _product_map(comparison)
    months = sorted(set(base.months) & set(comparison.months))

    for month in months:
        codes = sorted({code for ym, code in left if ym == month} | {code for ym, code in right if ym == month})
        for unit_basis in ("PCS", "LENGTH"):
            rows: list[tuple[ProductRecord | None, ProductRecord | None]] = []
            for code in codes:
                lrow, rrow = left.get((month, code)), right.get((month, code))
                basis = (rrow or lrow).unit_basis.upper() if (rrow or lrow) else "PCS"
                if basis == unit_basis:
                    rows.append((lrow, rrow))
            if not rows:
                continue

            base_total = sum(row.sales_basis for row, _ in rows if row)
            comp_total = sum(row.sales_basis for _, row in rows if row)
            base_weighted_margin = 0.0
            mix_component = 0.0
            for lrow, rrow in rows:
                q0 = lrow.sales_basis if lrow else 0.0
                q1 = rrow.sales_basis if rrow else 0.0
                margin0 = ((lrow.sales_amount - lrow.product_cogs) / q0) if lrow and q0 else 0.0
                m0 = q0 / base_total if base_total else 0.0
                m1 = q1 / comp_total if comp_total else 0.0
                base_weighted_margin += m0 * margin0
                mix_component += (m1 - m0) * margin0

                fx0 = float(lrow.sales_fx) if lrow and lrow.sales_fx else 1.0
                fx1 = float(rrow.sales_fx) if rrow and rrow.sales_fx else fx0
                p0_krw = lrow.sales_amount / q0 if lrow and q0 else 0.0
                p1_krw = rrow.sales_amount / q1 if rrow and q1 else 0.0
                p0_foreign = p0_krw / fx0 if fx0 else 0.0
                p1_foreign = p1_krw / fx1 if fx1 else 0.0
                result.displayed_price += q1 * (p1_foreign - p0_foreign) * (fx0 + fx1) / 2
                result.sales_fx += q1 * (fx1 - fx0) * (p0_foreign + p1_foreign) / 2
                if q1 and not q0:
                    result.issues.append(f"{month} {rrow.product_code}: 기준 판매수량이 없어 신규 제품 가격효과가 비교단가 기준으로 계산됨")

            result.quantity += (comp_total - base_total) * base_weighted_margin
            result.mix += comp_total * mix_component

    base_transport = _expense_by_month(base, config)
    comp_transport = _expense_by_month(comparison, config)
    base_activity = _activities(base)
    comp_activity = _activities(comparison)
    for month in months:
        a0 = base_activity.get(month)
        a1 = comp_activity.get(month)
        q0 = a0.transport_activity if a0 else 0.0
        q1 = a1.transport_activity if a1 else 0.0
        tariff0 = a0.tariff_input if a0 else 0.0
        tariff1 = a1.tariff_input if a1 else 0.0
        c0 = base_transport.get(month, 0.0) - (tariff0 if a0 and a0.tariff_in_transport else 0.0)
        c1 = comp_transport.get(month, 0.0) - (tariff1 if a1 and a1.tariff_in_transport else 0.0)
        u0 = c0 / q0 if q0 else 0.0
        u1 = c1 / q1 if q1 else 0.0
        result.transport_quantity += -(q1 - q0) * u0
        result.transport_unit += -q1 * (u1 - u0)
        result.tariff += tariff0 - tariff1
        if not q0 and c0:
            result.issues.append(f"{month}: 기준 판매운반비 활동량이 0이라 운반비 원단위 계산에서 제외됨")

    result.quantity += result.transport_quantity
    result.price = result.displayed_price + result.transport_unit
    return result
