from __future__ import annotations

from dataclasses import dataclass, asdict
from math import isfinite
from typing import Any, Iterable


@dataclass(frozen=True)
class SalesEffectRow:
    product_group: str
    baseline_quantity: float
    baseline_amount: float
    baseline_unit_price: float
    baseline_gross_margin_rate: float
    comparison_quantity: float
    comparison_amount: float
    comparison_unit_price: float
    comparison_gross_margin_rate: float
    quantity_delta: float
    pure_price_delta_usd: float
    quantity_effect: float
    pure_price_effect: float
    sales_fx_effect: float
    unit_value_effect: float
    total_sales_effect: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def calculate_sales_effect_rows(
    rows: Iterable[dict[str, Any]],
    baseline_fx: float,
    comparison_fx: float,
) -> list[SalesEffectRow]:
    """Calculate sales effects with an exact price/FX split.

    Quantity effect uses the base model's unit price and gross-margin rate.
    The comparison quantity is used for the total unit-value effect. Pure price
    and FX effects use a symmetric decomposition, so their sum always equals
    the KRW unit-price change multiplied by the comparison quantity.
    """
    if baseline_fx <= 0 or comparison_fx <= 0:
        raise ValueError("매출환율은 0보다 커야 합니다.")

    effects: list[SalesEffectRow] = []
    for row in rows:
        product_group = str(row.get("product_group") or "")
        q0 = float(row.get("baseline_quantity") or 0.0)
        q1 = float(row.get("comparison_quantity") or 0.0)
        a0 = float(row.get("baseline_amount") or 0.0)
        a1 = float(row.get("comparison_amount") or 0.0)
        p0 = a0 / q0 if q0 else 0.0
        p1 = a1 / q1 if q1 else 0.0
        gm0 = float(row.get("baseline_gross_margin_rate") or 0.0)
        gm1 = float(row.get("comparison_gross_margin_rate") or 0.0)

        if product_group.strip() == "신사업":
            if "baseline_cogs" not in row or "comparison_cogs" not in row:
                raise ValueError(
                    "신사업 compatibility 계산에는 기준/비교 매출원가가 필요합니다."
                )
            raw_c0 = row.get("baseline_cogs")
            raw_c1 = row.get("comparison_cogs")
            if raw_c0 is None or raw_c1 is None or (
                isinstance(raw_c0, str) and not raw_c0.strip()
            ) or (
                isinstance(raw_c1, str) and not raw_c1.strip()
            ):
                raise ValueError(
                    "신사업 compatibility 계산에는 유효한 기준/비교 매출원가가 필요합니다."
                )
            try:
                c0 = float(raw_c0)
                c1 = float(raw_c1)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    "신사업 compatibility 계산에는 유효한 기준/비교 매출원가가 필요합니다."
                ) from exc
            if not isfinite(c0) or not isfinite(c1):
                raise ValueError(
                    "신사업 compatibility 계산에는 유효한 기준/비교 매출원가가 필요합니다."
                )
            if a0 == 0 and a1 == 0 and c0 == 0 and c1 == 0:
                effects.append(SalesEffectRow(
                    product_group=product_group,
                    baseline_quantity=q0,
                    baseline_amount=0.0,
                    baseline_unit_price=0.0,
                    baseline_gross_margin_rate=0.0,
                    comparison_quantity=q1,
                    comparison_amount=0.0,
                    comparison_unit_price=0.0,
                    comparison_gross_margin_rate=0.0,
                    quantity_delta=q1 - q0,
                    pure_price_delta_usd=0.0,
                    quantity_effect=0.0,
                    pure_price_effect=0.0,
                    sales_fx_effect=0.0,
                    unit_value_effect=0.0,
                    total_sales_effect=0.0,
                ))
                continue
            if a0 <= 0 or a1 <= 0:
                raise ValueError(
                    "신사업 compatibility 계산에는 양수인 기준/비교 매출액이 필요합니다."
                )
            gp0 = a0 - c0
            gp1 = a1 - c1
            gm0 = gp0 / a0
            gm1 = gp1 / a1
            revenue_effect = (a1 - a0) * gm0
            gp_rate_effect = a1 * (gm1 - gm0)
            effects.append(SalesEffectRow(
                product_group=product_group,
                baseline_quantity=q0,
                baseline_amount=a0,
                baseline_unit_price=p0,
                baseline_gross_margin_rate=gm0,
                comparison_quantity=q1,
                comparison_amount=a1,
                comparison_unit_price=p1,
                comparison_gross_margin_rate=gm1,
                quantity_delta=q1 - q0,
                pure_price_delta_usd=0.0,
                quantity_effect=revenue_effect,
                pure_price_effect=gp_rate_effect,
                sales_fx_effect=0.0,
                unit_value_effect=gp_rate_effect,
                total_sales_effect=revenue_effect + gp_rate_effect,
            ))
            continue

        quantity_effect = (q1 - q0) * p0 * gm0
        unit_value_effect = q1 * (p1 - p0)

        foreign_price0 = p0 / baseline_fx
        foreign_price1 = p1 / comparison_fx
        pure_price_effect = q1 * (foreign_price1 - foreign_price0) * (baseline_fx + comparison_fx) / 2.0
        sales_fx_effect = q1 * (comparison_fx - baseline_fx) * (foreign_price0 + foreign_price1) / 2.0

        effects.append(SalesEffectRow(
            product_group=product_group,
            baseline_quantity=q0,
            baseline_amount=a0,
            baseline_unit_price=p0,
            baseline_gross_margin_rate=gm0,
            comparison_quantity=q1,
            comparison_amount=a1,
            comparison_unit_price=p1,
            comparison_gross_margin_rate=gm1,
            quantity_delta=q1 - q0,
            pure_price_delta_usd=foreign_price1 - foreign_price0,
            quantity_effect=quantity_effect,
            pure_price_effect=pure_price_effect,
            sales_fx_effect=sales_fx_effect,
            unit_value_effect=unit_value_effect,
            total_sales_effect=quantity_effect + pure_price_effect + sales_fx_effect,
        ))
    return effects


def sales_effect_totals(rows: Iterable[SalesEffectRow]) -> dict[str, float]:
    items = list(rows)
    return {
        "quantity_effect": sum(row.quantity_effect for row in items),
        "pure_price_effect": sum(row.pure_price_effect for row in items),
        "sales_fx_effect": sum(row.sales_fx_effect for row in items),
        "unit_value_effect": sum(row.unit_value_effect for row in items),
        "total_sales_effect": sum(row.total_sales_effect for row in items),
    }
