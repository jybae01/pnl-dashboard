from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any


MONTH_COLUMNS = {month: chr(ord("E") + month - 1) for month in range(1, 13)}


def _number(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _effect_map(effects: Sequence[Mapping[str, Any]]) -> dict[str, float]:
    return {
        str(item.get("code") or ""): _number(item.get("profit_effect"))
        for item in effects
    }


def _source_references(
    spec: Mapping[str, Any], months: Sequence[int]
) -> str:
    rows = [
        int(spec[key])
        for key in ("quantity_row", "amount_row")
        if spec.get(key) is not None
    ]
    return " | ".join(
        f"Data!{MONTH_COLUMNS[int(month)]}{row}"
        for month in months
        for row in rows
    ) or "SOURCE_REFERENCE_UNAVAILABLE"


def _monthly_amounts(
    rows: Sequence[Mapping[str, Any]],
    *,
    period_key: str,
    amount_key: str,
) -> dict[str, float]:
    amounts: dict[str, float] = defaultdict(float)
    for row in rows:
        period = str(row.get(period_key) or "")
        if period:
            amounts[period] += _number(row.get(amount_key))
    return dict(amounts)


def analyze_sales_cogs_basis_overlap(
    *,
    sales_analysis: Mapping[str, Any],
    sales_scope_contract: Mapping[str, Mapping[str, Any]],
    inventory_analysis: Mapping[str, Any],
    effects: Sequence[Mapping[str, Any]],
    product_rows: Sequence[Mapping[str, Any]],
    manufactured_groups: Sequence[str],
    material_details: Sequence[Mapping[str, Any]],
    manufacturing_details: Sequence[Mapping[str, Any]],
    sga_details: Sequence[Mapping[str, Any]],
    baseline_pnl_records: Sequence[Any],
    comparison_pnl_records: Sequence[Any],
    sku_source_rows: Mapping[str, Mapping[str, Any]],
    months: Sequence[int],
    period_label: str,
    operating_profit_delta: float,
    effects_total: float,
    residual: float,
    residual_analysis: Mapping[str, Any] | None = None,
    absolute_tolerance: float = 1.0,
    relative_tolerance: float = 1e-9,
) -> dict[str, Any]:
    """Analyze the Sales GP/COGS basis overlap without changing an Effect.

    ``embedded_cogs_expense_delta`` follows expense-source sign
    (Comparison COGS - Base COGS).  ``overlap_profit_candidate`` reverses that
    sign so it is comparable with the OP bridge.  Counterfactuals are analysis
    metadata only and never replace production Quantity, Mix, or Inventory
    Timing values.
    """
    groups = {str(group) for group in manufactured_groups}
    all_trace_rows = [dict(row) for row in sales_analysis.get("trace_rows") or []]
    trace_rows = [
        dict(row)
        for row in all_trace_rows
        if str(row.get("product_group") or "") in groups
    ]
    scope_contract = {
        str(group): dict(contract)
        for group, contract in sales_scope_contract.items()
    }
    pool_rows = [dict(row) for row in sales_analysis.get("pool_trace_rows") or []]
    pool_map = {
        (str(row.get("period") or ""), str(row.get("pool") or "")): row
        for row in pool_rows
    }
    periods = sorted({str(row.get("period") or "") for row in trace_rows})
    tolerance = max(
        float(absolute_tolerance),
        abs(float(operating_profit_delta)) * float(relative_tolerance),
    )

    detail_rows: list[dict[str, Any]] = []
    matched_pool_rows: list[dict[str, Any]] = []
    for period in periods:
        for pool in ("PCS", "LENGTH"):
            selected = [
                row
                for row in trace_rows
                if str(row.get("period") or "") == period
                and str(row.get("pool") or "") == pool
            ]
            if not selected:
                continue
            base_total = sum(_number(row.get("base_quantity")) for row in selected)
            comparison_total = sum(
                _number(row.get("comparison_quantity")) for row in selected
            )
            pool_detail_start = len(detail_rows)
            for row in selected:
                base_quantity = _number(row.get("base_quantity"))
                comparison_quantity = _number(row.get("comparison_quantity"))
                base_revenue = _number(row.get("base_revenue"))
                comparison_revenue = _number(row.get("comparison_revenue"))
                base_cogs = _number(row.get("base_cogs"))
                comparison_cogs = _number(row.get("comparison_cogs"))
                base_revenue_per_unit = (
                    base_revenue / base_quantity if base_quantity else 0.0
                )
                base_cogs_per_unit = (
                    base_cogs / base_quantity if base_quantity else 0.0
                )
                base_gp_per_unit = base_revenue_per_unit - base_cogs_per_unit
                base_mix = base_quantity / base_total if base_total else 0.0
                comparison_mix = (
                    comparison_quantity / comparison_total
                    if comparison_total else 0.0
                )
                quantity_delta = comparison_total - base_total
                revenue_quantity = (
                    quantity_delta * base_mix * base_revenue_per_unit
                )
                gp_quantity = quantity_delta * base_mix * base_gp_per_unit
                embedded_quantity = revenue_quantity - gp_quantity
                revenue_mix = (
                    comparison_total
                    * (comparison_mix - base_mix)
                    * base_revenue_per_unit
                )
                gp_mix = (
                    comparison_total
                    * (comparison_mix - base_mix)
                    * base_gp_per_unit
                )
                embedded_mix = revenue_mix - gp_mix
                embedded_total = embedded_quantity + embedded_mix
                group = str(row.get("product_group") or "")
                group_contract = scope_contract.get(group, {})
                scope_status = str(
                    group_contract.get("status") or "SOURCE_SCOPE_MATCHED"
                )
                detail_rows.append({
                    "period": period,
                    "pool": pool,
                    "unit": str(row.get("unit") or ("m" if pool == "LENGTH" else "PCS")),
                    "product_group": group,
                    "base_quantity": base_quantity,
                    "comparison_quantity": comparison_quantity,
                    "pool_base_quantity": base_total,
                    "pool_comparison_quantity": comparison_total,
                    "base_revenue": base_revenue,
                    "comparison_revenue": comparison_revenue,
                    "base_cogs": base_cogs,
                    "comparison_cogs": comparison_cogs,
                    "base_revenue_per_unit": base_revenue_per_unit,
                    "base_cogs_per_unit": base_cogs_per_unit,
                    "base_gp_per_unit": base_gp_per_unit,
                    "base_mix": base_mix,
                    "comparison_mix": comparison_mix,
                    "revenue_basis_quantity": revenue_quantity,
                    "gp_basis_quantity": gp_quantity,
                    "embedded_cogs_quantity_expense_delta": embedded_quantity,
                    "revenue_basis_mix": revenue_mix,
                    "gp_basis_mix": gp_mix,
                    "embedded_cogs_mix_expense_delta": embedded_mix,
                    "embedded_cogs_expense_delta": embedded_total,
                    "overlap_profit_candidate": -embedded_total,
                    "base_source_reference": row.get("base_source_reference"),
                    "comparison_source_reference": row.get(
                        "comparison_source_reference"
                    ),
                    "scope": "MANUFACTURED_MATCHED",
                    "classification": (
                        "SALES_EMBEDDED_COGS_CANDIDATE_MAPPING_GAP"
                        if scope_status != "SOURCE_SCOPE_MATCHED"
                        else "SALES_EMBEDDED_COGS_CANDIDATE"
                    ),
                    "source_scope_status": scope_status,
                    "source_scope_contract": group_contract,
                    "source_validation_status": row.get("validation_status"),
                })
            created = detail_rows[pool_detail_start:]
            official = pool_map.get((period, pool), {})
            matched_gp_quantity = sum(
                _number(row.get("gp_basis_quantity")) for row in created
            )
            matched_gp_mix = sum(_number(row.get("gp_basis_mix")) for row in created)
            revenue_quantity = sum(
                _number(row.get("revenue_basis_quantity")) for row in created
            )
            revenue_mix = sum(
                _number(row.get("revenue_basis_mix")) for row in created
            )
            embedded_expense = revenue_quantity + revenue_mix - (
                matched_gp_quantity + matched_gp_mix
            )
            official_quantity = _number(official.get("quantity_effect"))
            official_mix = _number(official.get("mix_effect"))
            quantity_scope_difference = official_quantity - matched_gp_quantity
            mix_scope_difference = official_mix - matched_gp_mix
            matched_pool_rows.append({
                "period": period,
                "pool": pool,
                "unit": "m" if pool == "LENGTH" else "PCS",
                "base_total_quantity": base_total,
                "comparison_total_quantity": comparison_total,
                "official_gp_quantity": official_quantity,
                "official_gp_mix": official_mix,
                "matched_gp_quantity": matched_gp_quantity,
                "matched_gp_mix": matched_gp_mix,
                "revenue_basis_quantity": revenue_quantity,
                "revenue_basis_mix": revenue_mix,
                "embedded_cogs_quantity_expense_delta": (
                    revenue_quantity - matched_gp_quantity
                ),
                "embedded_cogs_mix_expense_delta": revenue_mix - matched_gp_mix,
                "embedded_cogs_expense_delta": embedded_expense,
                "overlap_profit_candidate": -embedded_expense,
                "official_vs_matched_gp_scope_difference": (
                    quantity_scope_difference + mix_scope_difference
                ),
                "official_vs_matched_gp_quantity_difference": (
                    quantity_scope_difference
                ),
                "official_vs_matched_gp_mix_difference": mix_scope_difference,
                "quantity_scope_validation": (
                    "PASS"
                    if abs(quantity_scope_difference) <= tolerance
                    else "CHECK_SCOPE"
                ),
                "mix_scope_validation": (
                    "PASS"
                    if abs(mix_scope_difference) <= tolerance
                    else "CHECK_SCOPE"
                ),
                "validation": (
                    "PASS"
                    if abs(
                        official_quantity + official_mix
                        - matched_gp_quantity - matched_gp_mix
                    ) <= tolerance
                    else "CHECK_SCOPE"
                ),
            })

    inventory_months = {
        str(row.get("period") or ""): dict(row)
        for row in inventory_analysis.get("monthly_details") or []
    }
    material_months = _monthly_amounts(
        material_details, period_key="period", amount_key="total_effect"
    )
    manufacturing_months = _monthly_amounts(
        manufacturing_details, period_key="month", amount_key="realized_effect"
    )
    sga_months = _monthly_amounts(
        sga_details, period_key="month", amount_key="profit_effect"
    )
    price_months = _monthly_amounts(
        all_trace_rows, period_key="period", amount_key="price_effect"
    )
    fx_months = _monthly_amounts(
        all_trace_rows, period_key="period", amount_key="sales_fx_effect"
    )
    new_business_rows = [
        dict(row) for row in sales_analysis.get("new_business_trace_rows") or []
    ]
    new_business_revenue_months = _monthly_amounts(
        new_business_rows, period_key="period", amount_key="revenue_effect"
    )
    new_business_gp_rate_months = _monthly_amounts(
        new_business_rows, period_key="period", amount_key="gp_rate_effect"
    )
    freight_rows = [dict(row) for row in sales_analysis.get("freight_trace_rows") or []]
    freight_months = _monthly_amounts(
        freight_rows, period_key="period", amount_key="freight_effect"
    )
    tariff_months = _monthly_amounts(
        freight_rows, period_key="period", amount_key="tariff_effect"
    )
    base_op = {str(row.year_month): _number(row.operating_profit) for row in baseline_pnl_records}
    comparison_op = {
        str(row.year_month): _number(row.operating_profit)
        for row in comparison_pnl_records
    }

    cogs_comparison: list[dict[str, Any]] = []
    option_rows: list[dict[str, Any]] = []
    for period in periods:
        details = [row for row in detail_rows if row["period"] == period]
        pools = [row for row in matched_pool_rows if row["period"] == period]
        product_cogs_effect = sum(
            _number(row.get("base_cogs")) - _number(row.get("comparison_cogs"))
            for row in details
        )
        inventory = inventory_months.get(period, {})
        manufactured_effect = _number(inventory.get("manufactured_cogs_effect"))
        current_cost_effect = _number(
            inventory.get("current_manufacturing_cost_effect")
        )
        inventory_timing = _number(inventory.get("inventory_timing_effect"))
        overlap_profit = sum(
            _number(row.get("overlap_profit_candidate")) for row in pools
        )
        cogs_comparison.append({
            "period": period,
            "sales_product_cogs_direct_effect": product_cogs_effect,
            "manufactured_cogs_effect": manufactured_effect,
            "sales_to_pnl_cogs_scope_difference": (
                manufactured_effect - product_cogs_effect
            ),
            "current_manufacturing_cost_effect": current_cost_effect,
            "inventory_timing_effect": inventory_timing,
            "embedded_sales_cogs_overlap_profit_candidate": overlap_profit,
            "candidate_adjusted_inventory_timing": inventory_timing - overlap_profit,
            "base_sales_product_cogs": sum(
                _number(row.get("base_cogs")) for row in details
            ),
            "comparison_sales_product_cogs": sum(
                _number(row.get("comparison_cogs")) for row in details
            ),
            "base_manufactured_cogs": _number(
                inventory.get("base_manufactured_cogs")
            ),
            "comparison_manufactured_cogs": _number(
                inventory.get("comparison_manufactured_cogs")
            ),
            "source_reference": inventory.get("source_reference"),
            "classification": "PARTIAL_OVERLAP_SOURCE_SCOPE_DIFFERENCE",
        })

        official_quantity = sum(_number(row.get("official_gp_quantity")) for row in pools)
        official_mix = sum(_number(row.get("official_gp_mix")) for row in pools)
        new_business_revenue_effect = new_business_revenue_months.get(period, 0.0)
        new_business_gp_rate_effect = new_business_gp_rate_months.get(period, 0.0)
        production_quantity = official_quantity + new_business_revenue_effect
        revenue_quantity = sum(
            _number(row.get("revenue_basis_quantity")) for row in pools
        )
        revenue_mix = sum(_number(row.get("revenue_basis_mix")) for row in pools)
        current_sales_total = (
            production_quantity + official_mix
            + price_months.get(period, 0.0)
            + new_business_gp_rate_effect
            + freight_months.get(period, 0.0)
            + fx_months.get(period, 0.0)
        )
        other_cogs_effects = (
            material_months.get(period, 0.0)
            + manufacturing_months.get(period, 0.0)
        )
        current_effects = (
            current_sales_total
            + tariff_months.get(period, 0.0)
            + other_cogs_effects
            + inventory_timing
            + sga_months.get(period, 0.0)
        )
        op_delta = comparison_op.get(period, 0.0) - base_op.get(period, 0.0)

        def add_option(
            option: str,
            quantity: float,
            mix: float,
            sales_total: float,
            timing: float,
            option_effects: float,
        ) -> None:
            option_rows.append({
                "period": period,
                "option": option,
                "quantity": quantity,
                "mix": mix,
                "sales_total": sales_total,
                "inventory_timing": timing,
                "other_cogs_effects": other_cogs_effects,
                "effects_total": option_effects,
                "residual": op_delta - option_effects,
                "operating_profit_delta": op_delta,
                "identity_difference": option_effects + (op_delta - option_effects) - op_delta,
                "counterfactual_only": option != "CURRENT",
            })

        add_option(
            "CURRENT", production_quantity, official_mix, current_sales_total,
            inventory_timing, current_effects,
        )
        add_option(
            "OPTION_A", production_quantity, official_mix, current_sales_total,
            inventory_timing - overlap_profit, current_effects - overlap_profit,
        )
        option_b_sales = (
            current_sales_total - official_quantity - official_mix
            + revenue_quantity + revenue_mix
        )
        option_b_effects = (
            current_effects - official_quantity - official_mix
            + revenue_quantity + revenue_mix
        )
        add_option(
            "OPTION_B", revenue_quantity + new_business_revenue_effect,
            revenue_mix, option_b_sales,
            inventory_timing, option_b_effects,
        )
        add_option(
            "OPTION_C", production_quantity, official_mix, current_sales_total,
            inventory_timing, current_effects,
        )

    cumulative_options: list[dict[str, Any]] = []
    for option in ("CURRENT", "OPTION_A", "OPTION_B", "OPTION_C"):
        selected = [row for row in option_rows if row["option"] == option]
        cumulative = {
            key: sum(_number(row.get(key)) for row in selected)
            for key in (
                "quantity", "mix", "sales_total", "inventory_timing",
                "other_cogs_effects", "effects_total", "residual",
                "operating_profit_delta",
            )
        }
        cumulative_options.append({
            "period": period_label,
            "option": option,
            **cumulative,
            "identity_difference": (
                cumulative["effects_total"] + cumulative["residual"]
                - cumulative["operating_profit_delta"]
            ),
            "counterfactual_only": option != "CURRENT",
        })
    option_rows.extend(cumulative_options)

    sku_rows: list[dict[str, Any]] = []
    by_code = {str(row.get("code") or ""): dict(row) for row in product_rows}
    for group, codes in (("SW", ("SW400", "SW440")), ("BW", ("BW400", "BW440"))):
        selected = [by_code[code] for code in codes if code in by_code]
        if not selected:
            continue
        base_total = sum(_number(row.get("baseline_quantity")) for row in selected)
        comparison_total = sum(
            _number(row.get("comparison_quantity")) for row in selected
        )
        revenue_quantity = 0.0
        revenue_mix = 0.0
        for row in selected:
            base_quantity = _number(row.get("baseline_quantity"))
            comparison_quantity = _number(row.get("comparison_quantity"))
            base_unit_revenue = (
                _number(row.get("baseline_amount")) / base_quantity
                if base_quantity else 0.0
            )
            base_mix = base_quantity / base_total if base_total else 0.0
            comparison_mix = (
                comparison_quantity / comparison_total
                if comparison_total else 0.0
            )
            revenue_quantity += (
                (comparison_total - base_total) * base_mix * base_unit_revenue
            )
            revenue_mix += (
                comparison_total
                * (comparison_mix - base_mix)
                * base_unit_revenue
            )
        refs = [
            _source_references(sku_source_rows.get(code, {}), months)
            for code in codes
        ]
        sku_rows.append({
            "product_group": group,
            "sku_scope": " + ".join(codes),
            "base_quantity": base_total,
            "comparison_quantity": comparison_total,
            "revenue_basis_quantity_reference": revenue_quantity,
            "revenue_basis_mix_reference": revenue_mix,
            "embedded_cogs_component": None,
            "classification": "INTRA_GROUP_SKU_BASIS_DIFFERENCE",
            "source_coverage": "REVENUE_ONLY_COGS_BY_SKU_UNAVAILABLE",
            "source_reference": " | ".join(refs),
            "validation": "INSUFFICIENT_SOURCE",
        })

    embedded_expense = sum(
        _number(row.get("embedded_cogs_expense_delta"))
        for row in matched_pool_rows
    )
    overlap_profit = -embedded_expense
    product_cogs_direct = sum(
        _number(row.get("sales_product_cogs_direct_effect"))
        for row in cogs_comparison
    )
    manufactured_direct = sum(
        _number(row.get("manufactured_cogs_effect"))
        for row in cogs_comparison
    )
    source_scope_gap = manufactured_direct - product_cogs_direct
    sources_mapped = all(
        row.get("source_validation_status") in {"PASS", "SOURCE_MAPPED"}
        for row in detail_rows
    )
    inventory_sources_mapped = (
        inventory_analysis.get("source_validation_status") == "PASS"
        and inventory_analysis.get("scope_validation_status") == "PASS"
    )
    exact_cogs_scope_match = all(
        abs(_number(row.get("sales_to_pnl_cogs_scope_difference"))) <= tolerance
        for row in cogs_comparison
    )
    mapping_gaps = sorted({
        str(row.get("source_scope_status") or "")
        for row in detail_rows
        if str(row.get("source_scope_status") or "") != "SOURCE_SCOPE_MATCHED"
    })
    if not sources_mapped or not inventory_sources_mapped:
        verdict = "INSUFFICIENT_SOURCE"
    elif abs(overlap_profit) <= tolerance:
        verdict = "NO_MATERIAL_OVERLAP"
    elif exact_cogs_scope_match and not mapping_gaps:
        verdict = "OVERLAP_CONFIRMED"
    else:
        verdict = "PARTIAL_OVERLAP"

    residual_components = (
        list((residual_analysis or {}).get("components") or [])
        if isinstance(residual_analysis, Mapping)
        else []
    )
    sales_formula_basis_gap = next(
        (
            _number(item.get("amount"))
            for item in residual_components
            if str(
                item.get("component_id") or item.get("component_code") or ""
            ) == "sales_formula_basis_gap"
        ),
        0.0,
    )

    current_cumulative = next(
        row for row in cumulative_options if row["option"] == "CURRENT"
    )
    option_a_cumulative = next(
        row for row in cumulative_options if row["option"] == "OPTION_A"
    )
    option_b_cumulative = next(
        row for row in cumulative_options if row["option"] == "OPTION_B"
    )
    checks = [
        {
            "check": "Production effects_total unchanged",
            "actual": current_cumulative["effects_total"],
            "expected": float(effects_total),
        },
        {
            "check": "Production residual unchanged",
            "actual": current_cumulative["residual"],
            "expected": float(residual),
        },
        {
            "check": "Production OP Delta unchanged",
            "actual": current_cumulative["operating_profit_delta"],
            "expected": float(operating_profit_delta),
        },
        {
            "check": "Option A and B matched-scope effects_total",
            "actual": option_a_cumulative["effects_total"],
            "expected": option_b_cumulative["effects_total"],
        },
        {
            "check": "Pool unit separation",
            "actual": 0.0 if all(
                (row["pool"] == "PCS" and row["unit"] == "PCS")
                or (row["pool"] == "LENGTH" and row["unit"] == "m")
                for row in detail_rows
            ) else 1.0,
            "expected": 0.0,
        },
        {
            "check": "Counterfactual identity",
            "actual": max(
                (abs(_number(row.get("identity_difference"))) for row in option_rows),
                default=0.0,
            ),
            "expected": 0.0,
        },
    ]
    for item in checks:
        item["difference"] = _number(item["actual"]) - _number(item["expected"])
        item["tolerance"] = tolerance
        item["status"] = (
            "PASS" if abs(_number(item["difference"])) <= tolerance else "FAIL"
        )

    effect_amounts = _effect_map(effects)
    production_core_overlap_applied = (
        inventory_analysis.get("core_overlap_policy_status")
        == "APPLIED_CORE_ONLY"
    )
    return {
        "schema_version": "1",
        "status": "PASS" if all(item["status"] == "PASS" for item in checks) else "CHECK",
        "verdict": verdict,
        "confidence": "MEDIUM" if verdict == "PARTIAL_OVERLAP" else "HIGH",
        "period": period_label,
        "sign_convention": {
            "bridge": "+ = OP improvement; - = OP deterioration",
            "embedded_cogs_expense_delta": "Comparison COGS - Base COGS",
            "overlap_profit_candidate": "- embedded_cogs_expense_delta",
        },
        "scope": {
            "included": sorted(groups),
            "excluded": ["New Business Merchandise"],
            "intended_excluded": ["LC Merchandise"],
            "lc_merchandise_separation": (
                "UNRESOLVED_MAPPING_GAP" if mapping_gaps else "SEPARATED"
            ),
            "pools": {"PCS": ["SW", "BW", "LC"], "LENGTH": ["FS"]},
            "mapping_gaps": mapping_gaps,
            "contracts": scope_contract,
            "new_business_base_non_unitized_revenue": any(
                str(row.get("code") or "") == "NEW_BUSINESS"
                and not _number(row.get("baseline_quantity"))
                and bool(_number(row.get("baseline_amount")))
                for row in product_rows
            ),
        },
        "detail_rows": detail_rows,
        "pool_rows": matched_pool_rows,
        "cogs_comparison": cogs_comparison,
        "option_rows": option_rows,
        "intra_group_sku": sku_rows,
        "summary": {
            "official_gp_quantity": effect_amounts.get("sales_quantity", 0.0),
            "official_gp_mix": effect_amounts.get("sales_mix", 0.0),
            "matched_revenue_quantity": sum(
                _number(row.get("revenue_basis_quantity")) for row in matched_pool_rows
            ),
            "matched_revenue_mix": sum(
                _number(row.get("revenue_basis_mix")) for row in matched_pool_rows
            ),
            "embedded_cogs_quantity_expense_delta": sum(
                _number(row.get("embedded_cogs_quantity_expense_delta"))
                for row in matched_pool_rows
            ),
            "embedded_cogs_mix_expense_delta": sum(
                _number(row.get("embedded_cogs_mix_expense_delta"))
                for row in matched_pool_rows
            ),
            "embedded_sales_cogs_expense_delta": embedded_expense,
            "slice5a_sales_formula_basis_gap": sales_formula_basis_gap,
            "basis_gap_after_embedded_candidate": (
                sales_formula_basis_gap - embedded_expense
            ),
            "embedded_candidate_coverage_ratio": (
                abs(embedded_expense) / abs(sales_formula_basis_gap)
                if sales_formula_basis_gap else None
            ),
            "overlap_profit_candidate": overlap_profit,
            "sales_product_cogs_direct_effect": product_cogs_direct,
            "manufactured_cogs_direct_effect": manufactured_direct,
            "sales_to_pnl_cogs_scope_difference": source_scope_gap,
            "current_inventory_timing": effect_amounts.get("inventory_timing", 0.0),
            "candidate_adjusted_inventory_timing": (
                effect_amounts.get("inventory_timing", 0.0) - overlap_profit
            ),
            "current_residual": float(residual),
            "option_a_residual": option_a_cumulative["residual"],
            "option_b_residual": option_b_cumulative["residual"],
            "source_scope_exact_match": exact_cogs_scope_match,
        },
        "checks": checks,
        "counterfactual_only": True,
        "production_formula_mutated": production_core_overlap_applied,
        "recommendation": (
            "CORE_ONLY_OVERLAP_PRODUCTION_POLICY_APPLIED"
            if production_core_overlap_applied
            else "OPTION_A_REVIEW_FIRST"
            if verdict == "OVERLAP_CONFIRMED"
            else "OPTION_C_PENDING_SCOPE_RECONCILIATION"
            if verdict == "PARTIAL_OVERLAP"
            else "OPTION_C_PENDING_SOURCE"
        ),
        "decision_candidate_after_scope_reconciliation": (
            "PRODUCTION_APPLIED" if production_core_overlap_applied else "OPTION_A"
        ),
    }
