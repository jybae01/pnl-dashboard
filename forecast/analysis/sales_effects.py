from __future__ import annotations

from dataclasses import dataclass, field

from .configuration import AnalysisConfig
from .schema import AnalysisScenario, ProductRecord


FREIGHT_LENGTH_METERS_PER_PCS = 45.0


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
    # Deprecated payload aliases retained for V1 compatibility. Freight is a
    # single monthly equivalent-shipment pool; no product-level freight amount
    # allocation is introduced.
    transport_quantity: float = 0.0
    transport_unit: float = 0.0
    tariff: float = 0.0
    new_business_revenue_effect: float = 0.0
    new_business_gp_rate_effect: float = 0.0
    issues: list[str] = field(default_factory=list)
    details: list[dict[str, float | str]] = field(default_factory=list)
    pool_details: list[dict[str, float | str]] = field(default_factory=list)
    freight_details: list[dict[str, float | str | bool]] = field(default_factory=list)
    new_business_details: list[dict[str, float | str]] = field(default_factory=list)
    monthly_effects: list[dict[str, float | str]] = field(default_factory=list)

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


def _freight_quantity(
    products: dict[tuple[str, str], ProductRecord],
    month: str,
    product_group: str,
    unit_basis: str,
) -> tuple[float, str]:
    row = products.get((month, product_group))
    if row is None:
        return 0.0, ""
    if row.unit_basis.upper() != unit_basis:
        raise ValueError(
            f"{month} 고객배송 운반비: {product_group} 판매수량 단위가 "
            f"{unit_basis}가 아닙니다."
        )
    quantity = row.sales_length if unit_basis == "LENGTH" else row.sales_qty
    return float(quantity), str(row.sales_quantity_source or "")


def _freight_unit_cost(
    freight: float,
    denominator: float,
    *,
    month: str,
    side: str,
) -> float:
    if denominator < 0:
        raise ValueError(
            f"{month} 고객배송 운반비: {side} 총 환산 판매수량이 음수입니다."
        )
    if denominator == 0:
        if freight == 0:
            return 0.0
        raise ValueError(
            f"{month} 고객배송 운반비: {side} 운반비가 존재하지만 "
            "총 환산 판매수량이 0입니다."
        )
    return freight / denominator


def calculate_sales_effects(
    base: AnalysisScenario,
    comparison: AnalysisScenario,
    config: AnalysisConfig,
) -> SalesEffects:
    result = SalesEffects()
    left = _product_map(base)
    right = _product_map(comparison)
    months = sorted(set(base.months) & set(comparison.months))
    monthly_effects: dict[str, dict[str, float | str]] = {
        month: {
            "period": month,
            "quantity_effect": 0.0,
            "mix_effect": 0.0,
            "displayed_price_effect": 0.0,
            "freight_effect": 0.0,
            "sales_price_effect": 0.0,
            "sales_fx_effect": 0.0,
            "tariff_effect": 0.0,
            "new_business_revenue_effect": 0.0,
            "new_business_gp_rate_effect": 0.0,
            "total_sales_effect": 0.0,
        }
        for month in months
    }

    for month in months:
        codes = sorted({code for ym, code in left if ym == month} | {code for ym, code in right if ym == month})
        new_business_codes = [
            code
            for code in codes
            if str((right.get((month, code)) or left.get((month, code))).product_group).strip()
            == "신사업"
        ]
        for code in new_business_codes:
            lrow = left.get((month, code))
            rrow = right.get((month, code))
            base_revenue = float(lrow.sales_amount) if lrow else 0.0
            comparison_revenue = float(rrow.sales_amount) if rrow else 0.0
            if base_revenue <= 0:
                raise ValueError(
                    f"{month} 신사업: 기준 매출액이 0 이하이므로 GP율 효과를 계산할 수 없습니다."
                )
            if comparison_revenue <= 0:
                raise ValueError(
                    f"{month} 신사업: 비교 매출액이 0 이하이므로 GP율 효과를 계산할 수 없습니다."
                )
            base_cogs = float(lrow.product_cogs) if lrow else 0.0
            comparison_cogs = float(rrow.product_cogs) if rrow else 0.0
            base_gp = base_revenue - base_cogs
            comparison_gp = comparison_revenue - comparison_cogs
            base_gp_rate = base_gp / base_revenue
            comparison_gp_rate = comparison_gp / comparison_revenue
            revenue_effect = (comparison_revenue - base_revenue) * base_gp_rate
            gp_rate_effect = comparison_revenue * (comparison_gp_rate - base_gp_rate)
            identity_difference = (
                revenue_effect + gp_rate_effect - (comparison_gp - base_gp)
            )
            tolerance = max(1.0, abs(comparison_gp - base_gp) * 1e-9)
            if abs(identity_difference) > tolerance:
                raise ValueError(
                    f"{month} 신사업: 매출증가/GP율 변화 효과 항등식이 일치하지 않습니다."
                )

            result.new_business_revenue_effect += revenue_effect
            result.new_business_gp_rate_effect += gp_rate_effect
            result.quantity += revenue_effect
            result.displayed_price += gp_rate_effect
            monthly_effects[month]["quantity_effect"] += revenue_effect
            monthly_effects[month]["displayed_price_effect"] += gp_rate_effect
            monthly_effects[month]["new_business_revenue_effect"] += revenue_effect
            monthly_effects[month]["new_business_gp_rate_effect"] += gp_rate_effect
            result.new_business_details.append({
                "period": month,
                "product_group": "신사업",
                "business_source": "신사업 매출액·매출원가",
                "canonical_fields": "sales_amount / product_cogs",
                "base_quantity": float(lrow.sales_basis) if lrow else 0.0,
                "comparison_quantity": float(rrow.sales_basis) if rrow else 0.0,
                "base_revenue": base_revenue,
                "comparison_revenue": comparison_revenue,
                "base_cogs": base_cogs,
                "comparison_cogs": comparison_cogs,
                "base_gp": base_gp,
                "comparison_gp": comparison_gp,
                "base_gp_rate": base_gp_rate,
                "comparison_gp_rate": comparison_gp_rate,
                "revenue_effect": revenue_effect,
                "gp_rate_effect": gp_rate_effect,
                "effect_total": revenue_effect + gp_rate_effect,
                "gp_difference": comparison_gp - base_gp,
                "sales_fx_effect": 0.0,
                "mix_effect": 0.0,
                "analysis_method": "REVENUE_AND_GP_RATE",
                "base_source_reference": " | ".join(filter(None, (
                    getattr(lrow, "sales_amount_source", "") if lrow else "",
                    getattr(lrow, "product_cogs_source", "") if lrow else "",
                ))),
                "comparison_source_reference": " | ".join(filter(None, (
                    getattr(rrow, "sales_amount_source", "") if rrow else "",
                    getattr(rrow, "product_cogs_source", "") if rrow else "",
                ))),
                "validation_status": "PASS",
            })

        for unit_basis in ("PCS", "LENGTH"):
            rows: list[tuple[ProductRecord | None, ProductRecord | None]] = []
            for code in codes:
                lrow, rrow = left.get((month, code)), right.get((month, code))
                if code in new_business_codes:
                    continue
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
                monthly_effects[month]["displayed_price_effect"] += price_effect
                monthly_effects[month]["sales_fx_effect"] += fx_effect
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

            quantity_effect = (comp_total - base_total) * base_weighted_margin
            mix_effect = comp_total * mix_component
            result.quantity += quantity_effect
            result.mix += mix_effect
            monthly_effects[month]["quantity_effect"] += quantity_effect
            monthly_effects[month]["mix_effect"] += mix_effect
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
        base_sw, base_sw_source = _freight_quantity(left, month, "SW", "PCS")
        comparison_sw, comparison_sw_source = _freight_quantity(
            right, month, "SW", "PCS"
        )
        base_bw, base_bw_source = _freight_quantity(left, month, "BW", "PCS")
        comparison_bw, comparison_bw_source = _freight_quantity(
            right, month, "BW", "PCS"
        )
        base_lc, base_lc_source = _freight_quantity(left, month, "LC", "PCS")
        comparison_lc, comparison_lc_source = _freight_quantity(
            right, month, "LC", "PCS"
        )
        base_fs_length, base_fs_source = _freight_quantity(
            left, month, "FS", "LENGTH"
        )
        comparison_fs_length, comparison_fs_source = _freight_quantity(
            right, month, "FS", "LENGTH"
        )
        base_fs_converted = base_fs_length / FREIGHT_LENGTH_METERS_PER_PCS
        comparison_fs_converted = (
            comparison_fs_length / FREIGHT_LENGTH_METERS_PER_PCS
        )
        base_denominator = base_sw + base_bw + base_lc + base_fs_converted
        comparison_denominator = (
            comparison_sw + comparison_bw + comparison_lc + comparison_fs_converted
        )
        base_unit_freight = _freight_unit_cost(
            c0, base_denominator, month=month, side="기준"
        )
        comparison_unit_freight = _freight_unit_cost(
            c1, comparison_denominator, month=month, side="비교"
        )
        freight_effect = (
            (base_unit_freight - comparison_unit_freight)
            * comparison_denominator
        )

        def quantity_sources(*items: tuple[str, str]) -> str:
            return " | ".join(
                f"{group}: {source}" for group, source in items if source
            )

        result.base_transport_ex_tariff += c0
        result.comparison_transport_ex_tariff += c1
        result.transport_effect += freight_effect
        result.tariff += tariff0 - tariff1
        monthly_effects[month]["freight_effect"] = freight_effect
        monthly_effects[month]["tariff_effect"] = tariff0 - tariff1
        result.freight_details.append({
            "period": month,
            "business_source": "판매비 고객배송 운반비 / 관세 입력",
            "canonical_fields": (
                "transport_effect / tariff / sales_qty / sales_length"
            ),
            "base_freight_including_tariff": base_transport.get(month, 0.0),
            "comparison_freight_including_tariff": comp_transport.get(month, 0.0),
            "base_tariff": tariff0,
            "comparison_tariff": tariff1,
            "base_tariff_in_transport": bool(a0 and a0.tariff_in_transport),
            "comparison_tariff_in_transport": bool(a1 and a1.tariff_in_transport),
            "base_freight_ex_tariff": c0,
            "comparison_freight_ex_tariff": c1,
            "base_sw_pcs": base_sw,
            "comparison_sw_pcs": comparison_sw,
            "base_bw_pcs": base_bw,
            "comparison_bw_pcs": comparison_bw,
            "base_lc_pcs": base_lc,
            "comparison_lc_pcs": comparison_lc,
            "base_fs_length": base_fs_length,
            "comparison_fs_length": comparison_fs_length,
            "freight_conversion_basis": "45m/PCS",
            "freight_length_meters_per_pcs": FREIGHT_LENGTH_METERS_PER_PCS,
            "base_fs_converted_pcs": base_fs_converted,
            "comparison_fs_converted_pcs": comparison_fs_converted,
            "base_equivalent_shipment_quantity": base_denominator,
            "comparison_equivalent_shipment_quantity": comparison_denominator,
            "base_freight_unit_cost": base_unit_freight,
            "comparison_freight_unit_cost": comparison_unit_freight,
            # Compatibility aggregates retained for stored-result readers.
            "base_pcs_quantity": base_sw + base_bw + base_lc,
            "comparison_pcs_quantity": comparison_sw + comparison_bw + comparison_lc,
            "base_length_quantity": base_fs_length,
            "comparison_length_quantity": comparison_fs_length,
            "base_quantity_source_reference": quantity_sources(
                ("SW", base_sw_source),
                ("BW", base_bw_source),
                ("LC", base_lc_source),
                ("FS", base_fs_source),
            ),
            "comparison_quantity_source_reference": quantity_sources(
                ("SW", comparison_sw_source),
                ("BW", comparison_bw_source),
                ("LC", comparison_lc_source),
                ("FS", comparison_fs_source),
            ),
            "freight_denominator_policy": "EQUIVALENT_SHIPMENT_PCS_45M",
            "freight_effect_formula": (
                "(base_freight_unit_cost - comparison_freight_unit_cost) "
                "* comparison_equivalent_shipment_quantity"
            ),
            "freight_effect": freight_effect,
            "tariff_effect": tariff0 - tariff1,
            "base_tariff_regional_sales": a0.tariff_regional_sales if a0 else None,
            "comparison_tariff_regional_sales": a1.tariff_regional_sales if a1 else None,
            "base_tariff_applicable_rate": a0.tariff_applicable_rate if a0 else None,
            "comparison_tariff_applicable_rate": a1.tariff_applicable_rate if a1 else None,
            "base_tariff_rate": a0.tariff_rate if a0 else None,
            "comparison_tariff_rate": a1.tariff_rate if a1 else None,
            "base_tariff_effective_rate": a0.tariff_effective_rate if a0 else None,
            "comparison_tariff_effective_rate": a1.tariff_effective_rate if a1 else None,
            "base_tariff_calculation_source": a0.tariff_calculation_source if a0 else "",
            "comparison_tariff_calculation_source": a1.tariff_calculation_source if a1 else "",
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
    for month in months:
        row = monthly_effects[month]
        row["sales_price_effect"] = (
            float(row["displayed_price_effect"]) + float(row["freight_effect"])
        )
        row["total_sales_effect"] = sum(
            float(row[key])
            for key in (
                "quantity_effect", "mix_effect", "sales_price_effect", "sales_fx_effect"
            )
        )
        result.monthly_effects.append(row)
    return result
