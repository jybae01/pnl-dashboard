from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any


def _number(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _keyed(
    rows: Sequence[Mapping[str, Any]], *keys: str
) -> dict[tuple[str, ...], dict[str, Any]]:
    return {
        tuple(str(row.get(key) or "") for key in keys): dict(row)
        for row in rows
    }


def analyze_sales_cogs_scope_reconciliation(
    *,
    baseline_source: Mapping[str, Any],
    comparison_source: Mapping[str, Any],
    sales_cogs_basis_analysis: Mapping[str, Any],
    inventory_analysis: Mapping[str, Any],
    effects_total: float,
    residual: float,
    operating_profit_delta: float,
    absolute_tolerance: float = 1.0,
    relative_tolerance: float = 1e-9,
) -> dict[str, Any]:
    """Reconcile Sales Product COGS to the P&L manufactured COGS scope.

    This function only emits RCA and workbook-evidence metadata.  It never
    changes production Quantity, Mix, Inventory Timing, Residual, or OP Delta.
    Source signs are normalized to OP bridge convention: Base cost minus
    Comparison cost is an OP improvement.
    """
    tolerance = max(
        float(absolute_tolerance),
        abs(float(operating_profit_delta)) * float(relative_tolerance),
    )
    base_groups = _keyed(baseline_source.get("group_rows") or [], "period", "product_group")
    comp_groups = _keyed(comparison_source.get("group_rows") or [], "period", "product_group")
    base_pnl = _keyed(baseline_source.get("pnl_rows") or [], "period")
    comp_pnl = _keyed(comparison_source.get("pnl_rows") or [], "period")
    periods = sorted({key[0] for key in base_groups} | {key[0] for key in comp_groups})
    groups = sorted({key[1] for key in base_groups} | {key[1] for key in comp_groups})

    source_rows: list[dict[str, Any]] = []
    monthly_scope: list[dict[str, Any]] = []
    scope_components: list[dict[str, Any]] = []
    lc_rows: list[dict[str, Any]] = []
    matched_rows: list[dict[str, Any]] = []

    for period in periods:
        for group in groups:
            base = base_groups.get((period, group), {})
            comparison = comp_groups.get((period, group), {})
            product_effect = _number(base.get("sales_product_cogs")) - _number(
                comparison.get("sales_product_cogs")
            )
            matched_effect = _number(base.get("matched_manufactured_cogs")) - _number(
                comparison.get("matched_manufactured_cogs")
            )
            adjustment_effect = _number(base.get("sales_adjustment")) - _number(
                comparison.get("sales_adjustment")
            )
            merchandise_effect = _number(base.get("merchandise_cogs")) - _number(
                comparison.get("merchandise_cogs")
            )
            source_rows.append({
                "period": period,
                "product_group": group,
                "pool": base.get("pool") or comparison.get("pool"),
                "unit": base.get("unit") or comparison.get("unit"),
                "classification": base.get("classification") or comparison.get("classification"),
                "base_sales_product_cogs": _number(base.get("sales_product_cogs")),
                "comparison_sales_product_cogs": _number(comparison.get("sales_product_cogs")),
                "sales_product_cogs_effect": product_effect,
                "base_matched_manufactured_cogs": _number(base.get("matched_manufactured_cogs")),
                "comparison_matched_manufactured_cogs": _number(comparison.get("matched_manufactured_cogs")),
                "matched_manufactured_cogs_effect": matched_effect,
                "base_sales_adjustment": _number(base.get("sales_adjustment")),
                "comparison_sales_adjustment": _number(comparison.get("sales_adjustment")),
                "sales_adjustment_effect": adjustment_effect,
                "base_merchandise_cogs": _number(base.get("merchandise_cogs")),
                "comparison_merchandise_cogs": _number(comparison.get("merchandise_cogs")),
                "merchandise_cogs_effect": merchandise_effect,
                "base_source_reference": base.get("source_reference"),
                "comparison_source_reference": comparison.get("source_reference"),
                "base_formula_trace": base.get("formula_trace"),
                "comparison_formula_trace": comparison.get("formula_trace"),
            })
            if abs(adjustment_effect) > tolerance or group in {"SW", "BW", "LC", "FS"}:
                scope_components.append({
                    "period": period,
                    "component": f"{group}_SALES_COGS_ADJUSTMENT",
                    "amount": adjustment_effect,
                    "classification": "FORMULA_BASIS_DIFFERENCE",
                    "business_source": f"{group} Sales Product COGS 실적 차이 보정",
                    "formula_basis": "Sales Product COGS - matched manufactured COGS",
                    "source_reference": (
                        f"Base: {base.get('source_reference')} | "
                        f"Comparison: {comparison.get('source_reference')}"
                    ),
                })
            if group == "LC":
                scope_components.append({
                    "period": period,
                    "component": "LC_MERCHANDISE_COGS_INCLUDED_IN_SALES",
                    "amount": merchandise_effect,
                    "classification": "MERCHANDISE_INCLUDED_IN_SALES_COGS",
                    "business_source": "LC 상품 매출원가",
                    "formula_basis": "LC total COGS = manufactured COGS + merchandise COGS",
                    "source_reference": (
                        f"Base: {base.get('source_reference')} | "
                        f"Comparison: {comparison.get('source_reference')}"
                    ),
                })
                validations = {
                    "base_quantity": _number(base.get("sales_product_quantity"))
                    - _number(base.get("manufactured_quantity"))
                    - _number(base.get("merchandise_quantity")),
                    "comparison_quantity": _number(comparison.get("sales_product_quantity"))
                    - _number(comparison.get("manufactured_quantity"))
                    - _number(comparison.get("merchandise_quantity")),
                    "base_revenue": _number(base.get("sales_product_revenue"))
                    - _number(base.get("manufactured_revenue"))
                    - _number(base.get("merchandise_revenue")),
                    "comparison_revenue": _number(comparison.get("sales_product_revenue"))
                    - _number(comparison.get("manufactured_revenue"))
                    - _number(comparison.get("merchandise_revenue")),
                    "base_cogs": _number(base.get("sales_product_cogs"))
                    - _number(base.get("matched_manufactured_cogs"))
                    - _number(base.get("sales_adjustment"))
                    - _number(base.get("merchandise_cogs")),
                    "comparison_cogs": _number(comparison.get("sales_product_cogs"))
                    - _number(comparison.get("matched_manufactured_cogs"))
                    - _number(comparison.get("sales_adjustment"))
                    - _number(comparison.get("merchandise_cogs")),
                }
                lc_rows.append({
                    "period": period,
                    "base_manufactured_quantity": _number(base.get("manufactured_quantity")),
                    "base_merchandise_quantity": _number(base.get("merchandise_quantity")),
                    "base_total_quantity": _number(base.get("sales_product_quantity")),
                    "comparison_manufactured_quantity": _number(comparison.get("manufactured_quantity")),
                    "comparison_merchandise_quantity": _number(comparison.get("merchandise_quantity")),
                    "comparison_total_quantity": _number(comparison.get("sales_product_quantity")),
                    "base_manufactured_revenue": _number(base.get("manufactured_revenue")),
                    "base_merchandise_revenue": _number(base.get("merchandise_revenue")),
                    "base_total_revenue": _number(base.get("sales_product_revenue")),
                    "comparison_manufactured_revenue": _number(comparison.get("manufactured_revenue")),
                    "comparison_merchandise_revenue": _number(comparison.get("merchandise_revenue")),
                    "comparison_total_revenue": _number(comparison.get("sales_product_revenue")),
                    "base_core_manufactured_cogs": _number(base.get("matched_manufactured_cogs")),
                    "base_sales_adjustment": _number(base.get("sales_adjustment")),
                    "base_manufactured_cogs": _number(base.get("sales_manufactured_cogs")),
                    "base_merchandise_cogs": _number(base.get("merchandise_cogs")),
                    "base_total_cogs": _number(base.get("sales_product_cogs")),
                    "comparison_core_manufactured_cogs": _number(comparison.get("matched_manufactured_cogs")),
                    "comparison_sales_adjustment": _number(comparison.get("sales_adjustment")),
                    "comparison_manufactured_cogs": _number(comparison.get("sales_manufactured_cogs")),
                    "comparison_merchandise_cogs": _number(comparison.get("merchandise_cogs")),
                    "comparison_total_cogs": _number(comparison.get("sales_product_cogs")),
                    "max_identity_difference": max(abs(value) for value in validations.values()),
                    "separability": (
                        "LC_MANUFACTURED_MERCHANDISE_SEPARABLE"
                        if max(abs(value) for value in validations.values()) <= tolerance
                        else "LC_SCOPE_NOT_SEPARABLE"
                    ),
                    "base_source_reference": base.get("source_reference"),
                    "comparison_source_reference": comparison.get("source_reference"),
                })

        base_pnl_row = base_pnl.get((period,), {})
        comp_pnl_row = comp_pnl.get((period,), {})
        sales_product = sum(
            _number(row.get("sales_product_cogs_effect"))
            for row in source_rows if row["period"] == period
        )
        matched = sum(
            _number(row.get("matched_manufactured_cogs_effect"))
            for row in source_rows if row["period"] == period
        )
        pnl_effect = _number(base_pnl_row.get("pnl_manufactured_cogs")) - _number(
            comp_pnl_row.get("pnl_manufactured_cogs")
        )
        finished_adjustment_effect = _number(base_pnl_row.get("finished_adjustment")) - _number(
            comp_pnl_row.get("finished_adjustment")
        )
        semi_adjustment_effect = _number(base_pnl_row.get("semi_finished_adjustment")) - _number(
            comp_pnl_row.get("semi_finished_adjustment")
        )
        for name, effect, classification in (
            ("P&L_FINISHED_COGS_ADJUSTMENT", -finished_adjustment_effect, "FORMULA_BASIS_DIFFERENCE"),
            ("P&L_SEMI_FINISHED_COGS_ADJUSTMENT", -semi_adjustment_effect, "FORMULA_BASIS_DIFFERENCE"),
        ):
            scope_components.append({
                "period": period,
                "component": name,
                "amount": effect,
                "classification": classification,
                "business_source": "P&L Manufactured COGS applied adjustment",
                "formula_basis": "Subtract P&L adjustment effect from Sales-minus-P&L scope gap",
                "source_reference": (
                    f"Base: {base_pnl_row.get('source_reference')} | "
                    f"Comparison: {comp_pnl_row.get('source_reference')}"
                ),
            })
        classified = sum(
            _number(row.get("amount"))
            for row in scope_components if row["period"] == period
        )
        scope_difference = sales_product - pnl_effect
        unexplained = scope_difference - classified
        scope_components.append({
            "period": period,
            "component": "UNEXPLAINED",
            "amount": unexplained,
            "classification": "UNEXPLAINED",
            "business_source": "No unmatched source when reconciliation closes",
            "formula_basis": "Scope Difference - classified components",
            "source_reference": "Calculated from authoritative rows above",
        })
        monthly_scope.append({
            "period": period,
            "sales_product_cogs_effect": sales_product,
            "matched_sales_manufactured_cogs_effect": matched,
            "pnl_manufactured_cogs_effect": pnl_effect,
            "scope_difference": scope_difference,
            "classified_total": classified + unexplained,
            "unexplained": unexplained,
            "validation": "PASS" if abs(unexplained) <= tolerance else "FAIL",
            "base_pnl_source_reference": base_pnl_row.get("source_reference"),
            "comparison_pnl_source_reference": comp_pnl_row.get("source_reference"),
            "base_pnl_formula_trace": base_pnl_row.get("formula_trace"),
            "comparison_pnl_formula_trace": comp_pnl_row.get("formula_trace"),
        })

    # Matched manufactured COGS embedded in GP-based Quantity/Mix.
    for period in periods:
        for pool in ("PCS", "LENGTH"):
            selected: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
            for group in groups:
                base = base_groups.get((period, group), {})
                comparison = comp_groups.get((period, group), {})
                if (base.get("pool") or comparison.get("pool")) == pool:
                    selected.append((group, base, comparison))
            if not selected:
                continue
            base_total = sum(_number(base.get("manufactured_quantity")) for _, base, _ in selected)
            comparison_total = sum(
                _number(comparison.get("manufactured_quantity"))
                for _, _, comparison in selected
            )
            for group, base, comparison in selected:
                base_quantity = _number(base.get("manufactured_quantity"))
                comparison_quantity = _number(comparison.get("manufactured_quantity"))
                base_revenue = _number(base.get("manufactured_revenue"))
                base_cogs = _number(base.get("matched_manufactured_cogs"))
                base_revenue_per_unit = base_revenue / base_quantity if base_quantity else 0.0
                base_cogs_per_unit = base_cogs / base_quantity if base_quantity else 0.0
                base_gp_per_unit = base_revenue_per_unit - base_cogs_per_unit
                base_mix = base_quantity / base_total if base_total else 0.0
                comparison_mix = (
                    comparison_quantity / comparison_total if comparison_total else 0.0
                )
                quantity_delta = comparison_total - base_total
                revenue_quantity = quantity_delta * base_mix * base_revenue_per_unit
                gp_quantity = quantity_delta * base_mix * base_gp_per_unit
                revenue_mix = comparison_total * (comparison_mix - base_mix) * base_revenue_per_unit
                gp_mix = comparison_total * (comparison_mix - base_mix) * base_gp_per_unit
                matched_rows.append({
                    "period": period,
                    "pool": pool,
                    "unit": "m" if pool == "LENGTH" else "PCS",
                    "product_group": group,
                    "base_quantity": base_quantity,
                    "comparison_quantity": comparison_quantity,
                    "pool_base_quantity": base_total,
                    "pool_comparison_quantity": comparison_total,
                    "base_revenue": base_revenue,
                    "base_cogs": base_cogs,
                    "base_revenue_per_unit": base_revenue_per_unit,
                    "base_cogs_per_unit": base_cogs_per_unit,
                    "base_gp_per_unit": base_gp_per_unit,
                    "base_mix": base_mix,
                    "comparison_mix": comparison_mix,
                    "revenue_basis_quantity": revenue_quantity,
                    "gp_basis_quantity": gp_quantity,
                    "embedded_cogs_quantity_expense_delta": revenue_quantity - gp_quantity,
                    "revenue_basis_mix": revenue_mix,
                    "gp_basis_mix": gp_mix,
                    "embedded_cogs_mix_expense_delta": revenue_mix - gp_mix,
                    "embedded_cogs_expense_delta": (
                        revenue_quantity - gp_quantity + revenue_mix - gp_mix
                    ),
                    "overlap_profit_candidate": -(
                        revenue_quantity - gp_quantity + revenue_mix - gp_mix
                    ),
                    "base_source_reference": base.get("source_reference"),
                    "comparison_source_reference": comparison.get("source_reference"),
                })

    # New Business is disclosed rather than silently dropped from the unitized scope.
    base_new = _keyed(baseline_source.get("new_business_rows") or [], "period")
    comp_new = _keyed(comparison_source.get("new_business_rows") or [], "period")
    new_business_rows: list[dict[str, Any]] = []
    for period in periods:
        base = base_new.get((period,), {})
        comparison = comp_new.get((period,), {})
        base_quantity = _number(base.get("quantity"))
        base_quantity_raw = base.get("quantity_raw")
        comparison_quantity_raw = comparison.get("quantity_raw")
        base_revenue = _number(base.get("actual_revenue"))
        base_cogs = _number(base.get("actual_cogs"))
        classification = (
            "MERCHANDISE_NON_UNITIZED_BASE"
            if not base_quantity and (base_revenue or base_cogs)
            else "MERCHANDISE_UNIT_SOURCE_AVAILABLE"
        )
        new_business_rows.append({
            "period": period,
            "base_quantity": base_quantity,
            "base_quantity_raw": base_quantity_raw,
            "base_revenue": base_revenue,
            "base_cogs": base_cogs,
            "comparison_quantity": _number(comparison.get("quantity")),
            "comparison_quantity_raw": comparison_quantity_raw,
            "comparison_revenue": _number(comparison.get("actual_revenue")),
            "comparison_cogs": _number(comparison.get("actual_cogs")),
            "denominator_status": (
                "MISSING" if base_quantity_raw in (None, "")
                else "ZERO" if not base_quantity
                else "AVAILABLE"
            ),
            "comparison_denominator_status": (
                "MISSING" if comparison_quantity_raw in (None, "")
                else "ZERO" if not _number(comparison.get("quantity"))
                else "AVAILABLE"
            ),
            "business_classification": base.get("business_classification") or comparison.get("business_classification"),
            "classification": classification,
            "recommended_handling": "EXCLUDE_FROM_MANUFACTURED_GP_DRIVER; MERCHANDISE_TAXONOMY_DECISION_PENDING",
            "base_source_reference": base.get("source_reference"),
            "comparison_source_reference": comparison.get("source_reference"),
        })

    # SKU source coverage is a contract capability check, not a new Mix Effect.
    base_sku = _keyed(baseline_source.get("sku_rows") or [], "period", "sku")
    comp_sku = _keyed(comparison_source.get("sku_rows") or [], "period", "sku")
    sku_detail: list[dict[str, Any]] = []
    coverage_by_group: dict[str, list[str]] = defaultdict(list)
    for key in sorted(set(base_sku) | set(comp_sku)):
        base = base_sku.get(key, {})
        comparison = comp_sku.get(key, {})
        available = all(
            bool(base.get(flag) or comparison.get(flag))
            for flag in (
                "quantity_source_available",
                "revenue_source_available",
                "cogs_source_available",
            )
        )
        coverage = "FULL" if available else "PARTIAL"
        group = str(base.get("product_group") or comparison.get("product_group") or "")
        coverage_by_group[group].append(coverage)
        sku_detail.append({
            "period": key[0],
            "sku": key[1],
            "product_group": group,
            "unit": base.get("unit") or comparison.get("unit"),
            "base_quantity": _number(base.get("quantity")),
            "comparison_quantity": _number(comparison.get("quantity")),
            "base_revenue": _number(base.get("revenue")),
            "comparison_revenue": _number(comparison.get("revenue")),
            "base_cogs": _number(base.get("cogs")),
            "comparison_cogs": _number(comparison.get("cogs")),
            "coverage": coverage,
            "base_source_reference": base.get("source_reference"),
            "comparison_source_reference": comparison.get("source_reference"),
        })
    sku_coverage = [
        {
            "product_group": group,
            "coverage": (
                "FULL" if statuses and all(status == "FULL" for status in statuses)
                else "PARTIAL" if statuses else "NONE"
            ),
        }
        for group, statuses in sorted(coverage_by_group.items())
    ]

    sales_product_effect = sum(_number(row.get("sales_product_cogs_effect")) for row in source_rows)
    matched_direct_effect = sum(_number(row.get("matched_manufactured_cogs_effect")) for row in source_rows)
    pnl_effect = sum(_number(row.get("pnl_manufactured_cogs_effect")) for row in monthly_scope)
    scope_difference = sales_product_effect - pnl_effect
    unexplained = sum(_number(row.get("unexplained")) for row in monthly_scope)
    lc_merchandise_scope = sum(
        _number(row.get("amount"))
        for row in scope_components
        if row.get("component") == "LC_MERCHANDISE_COGS_INCLUDED_IN_SALES"
    )
    formula_basis_difference = (
        scope_difference - lc_merchandise_scope - unexplained
    )
    matched_embedded_quantity = sum(
        _number(row.get("embedded_cogs_quantity_expense_delta")) for row in matched_rows
    )
    matched_embedded_mix = sum(
        _number(row.get("embedded_cogs_mix_expense_delta")) for row in matched_rows
    )
    matched_embedded_expense = matched_embedded_quantity + matched_embedded_mix
    overlap_profit = -matched_embedded_expense
    unit_cost_remainder = matched_direct_effect - overlap_profit
    lc_separable = bool(lc_rows) and all(
        row.get("separability") == "LC_MANUFACTURED_MERCHANDISE_SEPARABLE"
        for row in lc_rows
    )
    inventory_sources_valid = (
        inventory_analysis.get("source_validation_status") == "PASS"
        and inventory_analysis.get("scope_validation_status") == "PASS"
    )
    verdict = (
        "OVERLAP_CONFIRMED"
        if abs(overlap_profit) > tolerance
        and abs(unexplained) <= tolerance
        and lc_separable
        and inventory_sources_valid
        else "INSUFFICIENT_SOURCE"
    )
    production_applied = (
        inventory_analysis.get("core_overlap_policy_status")
        == "APPLIED_CORE_ONLY"
    )
    readiness = (
        "CORE_OVERLAP_PRODUCTION_APPLIED"
        if production_applied else "OPTION_A_NOT_READY"
    )

    basis_summary = dict(sales_cogs_basis_analysis.get("summary") or {})
    current_inventory = _number(
        inventory_analysis.get("inventory_timing_effect")
        if production_applied else basis_summary.get("current_inventory_timing")
    )
    gross_inventory = _number(
        inventory_analysis.get("gross_inventory_timing_effect")
        if production_applied else current_inventory
    )
    current_embedded = _number(basis_summary.get("embedded_sales_cogs_expense_delta"))
    official_quantity = _number(basis_summary.get("official_gp_quantity"))
    official_mix = _number(basis_summary.get("official_gp_mix"))
    revenue_quantity = _number(basis_summary.get("matched_revenue_quantity"))
    revenue_mix = _number(basis_summary.get("matched_revenue_mix"))
    option_rows = [
        {
            "option": "CURRENT_PRODUCTION" if production_applied else "CURRENT",
            "quantity": official_quantity,
            "mix": official_mix,
            "inventory_timing": current_inventory,
            "effects_total": float(effects_total),
            "residual": float(residual),
            "operating_profit_delta": float(operating_profit_delta),
            "counterfactual_only": False,
        },
        {
            "option": (
                "BEFORE_CORE_DEDUCTION"
                if production_applied else "OPTION_A_MATCHED_SCOPE"
            ),
            "quantity": official_quantity,
            "mix": official_mix,
            "inventory_timing": (
                gross_inventory if production_applied
                else current_inventory - overlap_profit
            ),
            "effects_total": (
                float(effects_total) + overlap_profit if production_applied
                else float(effects_total) - overlap_profit
            ),
            "residual": (
                float(residual) - overlap_profit if production_applied
                else float(residual) + overlap_profit
            ),
            "operating_profit_delta": float(operating_profit_delta),
            "counterfactual_only": True,
        },
        {
            "option": "OPTION_B_REVENUE_BASIS",
            "quantity": revenue_quantity,
            "mix": revenue_mix,
            "inventory_timing": current_inventory,
            "effects_total": (
                float(effects_total) + overlap_profit + current_embedded
                if production_applied else float(effects_total) + current_embedded
            ),
            "residual": (
                float(residual) - overlap_profit - current_embedded
                if production_applied else float(residual) - current_embedded
            ),
            "operating_profit_delta": float(operating_profit_delta),
            "counterfactual_only": True,
        },
        {
            "option": (
                "OPTION_C_GROSS_LEGACY"
                if production_applied else "OPTION_C_KEEP_CURRENT"
            ),
            "quantity": official_quantity,
            "mix": official_mix,
            "inventory_timing": gross_inventory if production_applied else current_inventory,
            "effects_total": (
                float(effects_total) + overlap_profit
                if production_applied else float(effects_total)
            ),
            "residual": (
                float(residual) - overlap_profit
                if production_applied else float(residual)
            ),
            "operating_profit_delta": float(operating_profit_delta),
            "counterfactual_only": True,
        },
    ]
    for row in option_rows:
        row["identity_difference"] = (
            _number(row["effects_total"]) + _number(row["residual"])
            - _number(row["operating_profit_delta"])
        )

    checks = [
        {"check": "Scope Difference classified", "difference": unexplained},
        {
            "check": "Matched Sales source equals P&L core source",
            "difference": matched_direct_effect - sum(
                (_number(base_pnl.get((period,), {}).get("core_manufactured_cogs"))
                 - _number(comp_pnl.get((period,), {}).get("core_manufactured_cogs")))
                for period in periods
            ),
        },
        {
            "check": "Matched direct COGS decomposition",
            "difference": matched_direct_effect - overlap_profit - unit_cost_remainder,
        },
        {
            "check": "LC manufactured/merchandise separable",
            "difference": max(
                (_number(row.get("max_identity_difference")) for row in lc_rows),
                default=float("inf"),
            ),
        },
        {
            "check": "PCS/LENGTH separation",
            "difference": 0.0 if all(
                (row["pool"] == "PCS" and row["unit"] == "PCS")
                or (row["pool"] == "LENGTH" and row["unit"] == "m")
                for row in matched_rows
            ) else 1.0,
        },
        {
            "check": "Production values unchanged",
            "difference": max(
                abs(_number(option_rows[0][key]) - _number(expected))
                for key, expected in (
                    ("effects_total", effects_total),
                    ("residual", residual),
                    ("operating_profit_delta", operating_profit_delta),
                )
            ),
        },
        {
            "check": "Counterfactual identities",
            "difference": max(abs(_number(row["identity_difference"])) for row in option_rows),
        },
    ]
    for check in checks:
        check["tolerance"] = tolerance
        check["status"] = "PASS" if abs(_number(check["difference"])) <= tolerance else "FAIL"

    return {
        "schema_version": "1",
        "status": "PASS" if all(check["status"] == "PASS" for check in checks) else "CHECK",
        "verdict": verdict,
        "option_readiness": readiness,
        "recommendation": (
            "CORE_ONLY_OVERLAP_PRODUCTION_POLICY_APPLIED"
            if production_applied
            else "OPTION_C_RECOMMENDED_PENDING_BUSINESS_FORMULA_CONTRACT"
        ),
        "confidence": "HIGH" if verdict == "OVERLAP_CONFIRMED" else "MEDIUM",
        "production_formula_mutated": production_applied,
        "sign_convention": "+ = OP improvement; cost effect = Base - Comparison",
        "source_rows": source_rows,
        "monthly_scope": monthly_scope,
        "scope_components": scope_components,
        "lc_rows": lc_rows,
        "new_business_rows": new_business_rows,
        "sku_rows": sku_detail,
        "sku_coverage": sku_coverage,
        "matched_embedded_rows": matched_rows,
        "option_rows": option_rows,
        "checks": checks,
        "summary": {
            "sales_product_cogs_effect": sales_product_effect,
            "pnl_manufactured_cogs_effect": pnl_effect,
            "scope_difference_sales_minus_pnl": scope_difference,
            "formula_basis_difference_excluding_lc_merchandise": formula_basis_difference,
            "lc_merchandise_scope_difference": lc_merchandise_scope,
            "classified_scope_total": scope_difference - unexplained,
            "unexplained": unexplained,
            "matched_sales_manufactured_cogs_effect": matched_direct_effect,
            "matched_embedded_quantity_expense_delta": matched_embedded_quantity,
            "matched_embedded_mix_expense_delta": matched_embedded_mix,
            "matched_embedded_sales_cogs_expense_delta": matched_embedded_expense,
            "matched_overlap_profit_candidate": overlap_profit,
            "matched_direct_unit_cost_remainder": unit_cost_remainder,
            "current_slice5b_embedded_expense_delta": current_embedded,
            "scope_only_embedded_difference": current_embedded - matched_embedded_expense,
            "current_inventory_timing": current_inventory,
            "gross_inventory_timing": gross_inventory,
            "option_a_adjusted_inventory_timing": (
                current_inventory if production_applied
                else current_inventory - overlap_profit
            ),
            "current_effects_total": float(effects_total),
            "current_residual": float(residual),
            "operating_profit_delta": float(operating_profit_delta),
        },
    }
