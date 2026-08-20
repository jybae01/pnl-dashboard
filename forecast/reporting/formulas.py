from __future__ import annotations

from typing import Iterable, TypeAlias


Number: TypeAlias = int | float
NullableNumber: TypeAlias = Number | None


def sum_required(*values: NullableNumber) -> NullableNumber:
    """Return a subtotal only when every required source is available."""

    if any(value is None for value in values):
        return None
    return sum(value for value in values if value is not None)


def sum_required_iter(values: Iterable[NullableNumber]) -> NullableNumber:
    return sum_required(*tuple(values))


def difference(actual: NullableNumber, plan: NullableNumber) -> NullableNumber:
    if actual is None or plan is None:
        return None
    return actual - plan


def ratio_percent(numerator: NullableNumber, denominator: NullableNumber) -> float | None:
    """Return a percentage-point value (7.4 means 7.4%, never 0.074)."""

    if numerator is None or denominator is None or denominator == 0:
        return None
    return numerator / denominator * 100


def variance_rate(actual: NullableNumber, plan: NullableNumber) -> float | None:
    return ratio_percent(difference(actual, plan), plan)


def revenue_total(
    rev_product: NullableNumber,
    rev_semi: NullableNumber,
    rev_merch: NullableNumber,
    rev_other: NullableNumber,
    rev_rebate: NullableNumber,
) -> NullableNumber:
    return sum_required(rev_product, rev_semi, rev_merch, rev_other, rev_rebate)


def accounting_cogs_total(
    cogs_product: NullableNumber,
    cogs_semi: NullableNumber,
    cogs_merch: NullableNumber,
    cogs_other: NullableNumber,
    cogs_inventory_loss: NullableNumber,
) -> NullableNumber:
    return sum_required(
        cogs_product,
        cogs_semi,
        cogs_merch,
        cogs_other,
        cogs_inventory_loss,
    )


def manufacturing_total(
    mfg_material: NullableNumber,
    mfg_labor: NullableNumber,
    mfg_outsourcing: NullableNumber,
    mfg_other: NullableNumber,
) -> NullableNumber:
    return sum_required(mfg_material, mfg_labor, mfg_outsourcing, mfg_other)


def admin_other_total(
    admin_other_1: NullableNumber,
    admin_other_2: NullableNumber,
    admin_other_3: NullableNumber,
    admin_other_4: NullableNumber,
) -> NullableNumber:
    return sum_required(admin_other_1, admin_other_2, admin_other_3, admin_other_4)


def admin_total(
    admin_labor: NullableNumber,
    admin_depr: NullableNumber,
    admin_rnd: NullableNumber,
    admin_fee: NullableNumber,
    admin_other: NullableNumber,
) -> NullableNumber:
    return sum_required(admin_labor, admin_depr, admin_rnd, admin_fee, admin_other)


def sales_other_total(
    sales_other_1: NullableNumber,
    sales_other_2: NullableNumber,
    sales_other_3: NullableNumber,
) -> NullableNumber:
    return sum_required(sales_other_1, sales_other_2, sales_other_3)


def sales_total(
    sales_freight: NullableNumber,
    sales_commission: NullableNumber,
    sales_brand: NullableNumber,
    sales_labor: NullableNumber,
    sales_sample: NullableNumber,
    sales_bad_debt: NullableNumber,
    sales_sundry: NullableNumber,
    sales_other: NullableNumber,
) -> NullableNumber:
    return sum_required(
        sales_freight,
        sales_commission,
        sales_brand,
        sales_labor,
        sales_sample,
        sales_bad_debt,
        sales_sundry,
        sales_other,
    )


def sga_total(admin: NullableNumber, sales: NullableNumber) -> NullableNumber:
    return sum_required(admin, sales)


def gross_profit(revenue: NullableNumber, cogs: NullableNumber) -> NullableNumber:
    if revenue is None or cogs is None:
        return None
    return revenue - cogs


def operating_profit(gross_profit_value: NullableNumber, sga: NullableNumber) -> NullableNumber:
    if gross_profit_value is None or sga is None:
        return None
    return gross_profit_value - sga


def asp(revenue: NullableNumber, volume: NullableNumber) -> float | None:
    if revenue is None or volume is None or volume == 0:
        return None
    return revenue / volume
