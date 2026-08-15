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
    transport_effect: float = 0.0
    base_transport_ex_tariff: float = 0.0
    comparison_transport_ex_tariff: float = 0.0
    # Deprecated payload aliases retained for V1 compatibility.  Transport
    # is no longer decomposed without a product/unit allocation source.
    transport_quantity: float = 0.0
    transport_unit: float = 0.0
    tariff: float = 0.0
    issues: list[str] = field(default_factory=list)
    details: list[dict[str, float | str]] = field(default_factory=list)
    pool_details: list[dict[str, float | str]] = field(default_factory=list)
    freight_details: list[dict[str, float | str | bool]] = field(default_factory=list)

    @property
    def total(self) -> float:
        return self.quantity + self.mix + self.price + self.sales_fx + self.tariff


def _product_map(scenario: AnalysisScenario) -> dict[tuple[str, str], ProductRecord]:
    result: dict[tuple[str, str], ProductRecord] = {}
    for row in scenario.products:
        if not any((row.sales_basis, row.sales_amount, row.product_cogs)):
            continue
        key = (row.year_month, row.product_group)
        current = result.get(key)
        if current is None:
            result[key] = row
            continue
        if current.unit_basis.upper() != row.unit_basis.upper():
            raise ValueError(
                f"제품군 내 판매단위 불일치: {row.year_month} / {row.product_group}"
            )
        if current.sales_fx and row.sales_fx and current.sales_fx != row.sales_fx:
            raise ValueError(
                f"제품군 내 매출환율 불일치: {row.year_month} / {row.product_group}"
            )
        # V1 sales effects are product-group based. SKU composition inside a
        # group is aggregated before quantity/Mix/price decomposition.
        def joined(field: str) -> str:
            return " + ".join(
                value for value in (
                    str(getattr(current, field, "") or ""),
                    str(getattr(row, field, "") or ""),
                ) if value
            )

        result[key] = ProductRecord(
            year_month=row.year_month,
            product_code=row.product_group,
            product_group=row.product_group,
            unit_basis=row.unit_basis,
            sales_qty=current.sales_qty + row.sales_qty,
            sales_length=current.sales_length + row.sales_length,
            sales_amount=current.sales_amount + row.sales_amount,
            product_cogs=current.product_cogs + row.product_cogs,
            sales_fx=current.sales_fx or row.sales_fx,
            sales_currency=current.sales_currency or row.sales_currency,
            material_applicable_flag=False,
            sales_quantity_source=joined("sales_quantity_source"),
            sales_amount_source=joined("sales_amount_source"),
            product_cogs_source=joined("product_cogs_source"),
            sales_fx_source=joined("sales_fx_source"),
            source_validation_status=(
                "SOURCE_MAPPED"
                if current.source_validation_status in {"PASS", "SOURCE_MAPPED"}
                and row.source_validation_status in {"PASS", "SOURCE_MAPPED"}
                else "UNVALIDATED"
            ),
        )
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
            detail_rows: list[dict[str, float | str]] = []
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
                price_effect = q1 * (p1_foreign - p0_foreign) * (fx0 + fx1) / 2
                fx_effect = q1 * (fx1 - fx0) * (p0_foreign + p1_foreign) / 2
                product_group = (rrow or lrow).product_group if (rrow or lrow) else ""
                detail_rows.append({
                    "period": month,
                    "pool": unit_basis,
                    "unit": "m" if unit_basis == "LENGTH" else "PCS",
                    "product_group": product_group,
                    "base_quantity": q0,
                    "comparison_quantity": q1,
                    "base_revenue": float(lrow.sales_amount) if lrow else 0.0,
                    "comparison_revenue": float(rrow.sales_amount) if rrow else 0.0,
                    "base_cogs": float(lrow.product_cogs) if lrow else 0.0,
                    "comparison_cogs": float(rrow.product_cogs) if rrow else 0.0,
                    "base_gp_per_unit": margin0,
                    "base_mix": m0,
                    "comparison_mix": m1,
                    "weighted_base_gp": m0 * margin0,
                    "mix_difference": m1 - m0,
                    "mix_component": (m1 - m0) * margin0,
                    "base_fx": fx0,
                    "comparison_fx": fx1,
                    "base_price_krw": p0_krw,
                    "comparison_price_krw": p1_krw,
                    "base_price_foreign": p0_foreign,
                    "comparison_price_foreign": p1_foreign,
                    "price_effect": price_effect,
                    "sales_fx_effect": fx_effect,
                    "business_source": "제품군 판매수량·매출액·매출원가",
                    "canonical_fields": "sales_basis / sales_amount / product_cogs / sales_fx",
                    "base_source_reference": " | ".join(filter(None, (
                        getattr(lrow, "sales_quantity_source", "") if lrow else "",
                        getattr(lrow, "sales_amount_source", "") if lrow else "",
                        getattr(lrow, "product_cogs_source", "") if lrow else "",
                        getattr(lrow, "sales_fx_source", "") if lrow else "",
                    ))),
                    "comparison_source_reference": " | ".join(filter(None, (
                        getattr(rrow, "sales_quantity_source", "") if rrow else "",
                        getattr(rrow, "sales_amount_source", "") if rrow else "",
                        getattr(rrow, "product_cogs_source", "") if rrow else "",
                        getattr(rrow, "sales_fx_source", "") if rrow else "",
                    ))),
                    "validation_status": (
                        "SOURCE_MAPPED"
                        if (not lrow or lrow.source_validation_status in {"PASS", "SOURCE_MAPPED"})
                        and (not rrow or rrow.source_validation_status in {"PASS", "SOURCE_MAPPED"})
                        else "UNVALIDATED"
                    ),
                })
                if q1 and not q0:
                    result.issues.append(f"{month} {rrow.product_code}: 기준 판매수량이 없어 신규 제품 가격효과가 비교단가 기준으로 계산됨")

            result.quantity += (comp_total - base_total) * base_weighted_margin
            result.mix += comp_total * mix_component
            result.details.extend(detail_rows)
            result.pool_details.append({
                "period": month,
                "pool": unit_basis,
                "unit": "m" if unit_basis == "LENGTH" else "PCS",
                "base_total_quantity": base_total,
                "comparison_total_quantity": comp_total,
                "base_weighted_gp_per_unit": base_weighted_margin,
                "mix_component": mix_component,
                "quantity_effect": (comp_total - base_total) * base_weighted_margin,
                "mix_effect": comp_total * mix_component,
            })

    base_transport = _expense_by_month(base, config)
    comp_transport = _expense_by_month(comparison, config)
    base_activity = _activities(base)
    comp_activity = _activities(comparison)
    for month in months:
        a0 = base_activity.get(month)
        a1 = comp_activity.get(month)
        base_transport_row = next(
            (row for row in base.sga_expenses if row.year_month == month and config.is_transport(row.account)),
            None,
        )
        comparison_transport_row = next(
            (row for row in comparison.sga_expenses if row.year_month == month and config.is_transport(row.account)),
            None,
        )
        tariff0 = a0.tariff_input if a0 else 0.0
        tariff1 = a1.tariff_input if a1 else 0.0
        c0 = base_transport.get(month, 0.0) - (tariff0 if a0 and a0.tariff_in_transport else 0.0)
        c1 = comp_transport.get(month, 0.0) - (tariff1 if a1 and a1.tariff_in_transport else 0.0)
        base_pcs_rows = [
            row for (year_month, _code), row in left.items()
            if year_month == month and row.unit_basis.upper() == "PCS"
        ]
        comparison_pcs_rows = [
            row for (year_month, _code), row in right.items()
            if year_month == month and row.unit_basis.upper() == "PCS"
        ]
        base_length_rows = [
            row for (year_month, _code), row in left.items()
            if year_month == month and row.unit_basis.upper() == "LENGTH"
        ]
        comparison_length_rows = [
            row for (year_month, _code), row in right.items()
            if year_month == month and row.unit_basis.upper() == "LENGTH"
        ]

        def quantity_sources(rows: list[ProductRecord]) -> str:
            return " | ".join(sorted({
                row.sales_quantity_source for row in rows if row.sales_quantity_source
            }))

        result.base_transport_ex_tariff += c0
        result.comparison_transport_ex_tariff += c1
        result.transport_effect += c0 - c1
        result.tariff += tariff0 - tariff1
        result.freight_details.append({
            "period": month,
            "business_source": "판매비 고객배송 운반비 / 관세 입력",
            "canonical_fields": "transport_effect / tariff",
            "base_freight_including_tariff": base_transport.get(month, 0.0),
            "comparison_freight_including_tariff": comp_transport.get(month, 0.0),
            "base_tariff": tariff0,
            "comparison_tariff": tariff1,
            "base_tariff_in_transport": bool(a0 and a0.tariff_in_transport),
            "comparison_tariff_in_transport": bool(a1 and a1.tariff_in_transport),
            "base_freight_ex_tariff": c0,
            "comparison_freight_ex_tariff": c1,
            # The transport account is monthly and has no authoritative
            # product/pool allocation.  Expose both raw quantity pools for
            # audit, but never combine PCS and LENGTH or invent a Freight/unit
            # denominator.  V1 therefore assigns the whole direct amount
            # difference to the non-quantity component below.
            "base_pcs_quantity": sum(row.sales_basis for row in base_pcs_rows),
            "comparison_pcs_quantity": sum(row.sales_basis for row in comparison_pcs_rows),
            "base_length_quantity": sum(row.sales_basis for row in base_length_rows),
            "comparison_length_quantity": sum(row.sales_basis for row in comparison_length_rows),
            "base_quantity_source_reference": " | ".join(filter(None, (
                quantity_sources(base_pcs_rows), quantity_sources(base_length_rows),
            ))),
            "comparison_quantity_source_reference": " | ".join(filter(None, (
                quantity_sources(comparison_pcs_rows),
                quantity_sources(comparison_length_rows),
            ))),
            "freight_denominator_policy": "DIRECT_AMOUNT_NO_DENOMINATOR",
            "freight_effect": c0 - c1,
            "tariff_effect": tariff0 - tariff1,
            "base_source_reference": " | ".join(filter(None, (
                base_transport_row.amount_source if base_transport_row else "",
                a0.tariff_input_source if a0 else "",
            ))),
            "comparison_source_reference": " | ".join(filter(None, (
                comparison_transport_row.amount_source if comparison_transport_row else "",
                a1.tariff_input_source if a1 else "",
            ))),
            "validation_status": (
                "SOURCE_MAPPED"
                if all(
                    row is None or row.source_validation_status in {"PASS", "SOURCE_MAPPED"}
                    for row in (base_transport_row, comparison_transport_row, a0, a1)
                )
                else "UNVALIDATED"
            ),
        })

    result.transport_quantity = 0.0
    result.transport_unit = result.transport_effect
    result.price = result.displayed_price + result.transport_effect
    return result
