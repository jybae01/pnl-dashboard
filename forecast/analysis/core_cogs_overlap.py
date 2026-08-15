from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping


_GROUPS = ("SW", "BW", "LC", "FS")
_POOL_BY_GROUP = {"SW": "PCS", "BW": "PCS", "LC": "PCS", "FS": "LENGTH"}
_UNIT_BY_POOL = {"PCS": "PCS", "LENGTH": "m"}


def _number(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


@dataclass
class CoreManufacturedCogsOverlap:
    """Core manufactured COGS already embedded in GP-based Quantity/Mix.

    The amounts use the OP-effect sign convention.  A positive overlap is an
    improvement already present in Sales Quantity/Mix and therefore deducted
    from Gross Inventory Timing.  Adjustment, merchandise, and other COGS
    sources never enter this contract.
    """

    quantity_overlap_effect: float = 0.0
    mix_overlap_effect: float = 0.0
    total_overlap_effect: float = 0.0
    source_validation_status: str = "UNVALIDATED"
    pool_validation_status: str = "UNVALIDATED"
    policy_status: str = "NOT_APPLIED"
    details: list[dict[str, Any]] = field(default_factory=list)
    monthly_details: list[dict[str, Any]] = field(default_factory=list)
    excluded_sources: tuple[str, ...] = (
        "PRODUCT_GROUP_ADJUSTMENTS",
        "P&L_FINISHED_ADJUSTMENT",
        "P&L_SEMI_FINISHED_ADJUSTMENT",
        "LC_MERCHANDISE",
        "NEW_BUSINESS_MERCHANDISE",
        "OTHER_COGS",
        "CURRENT_COST_ROW_323_PAID_SUPPLY",
    )


def _keyed(rows: Iterable[Mapping[str, Any]]) -> dict[tuple[str, str], Mapping[str, Any]]:
    output: dict[tuple[str, str], Mapping[str, Any]] = {}
    for row in rows:
        key = (str(row.get("period") or ""), str(row.get("product_group") or ""))
        if not all(key):
            raise ValueError("core manufactured COGS source is missing period/product_group")
        if key in output:
            raise ValueError(f"duplicate core manufactured COGS source: {key}")
        output[key] = row
    return output


def core_cogs_overlap_source(
    records: Iterable[Any],
) -> dict[str, list[dict[str, Any]]]:
    """Build the calculator contract from canonical adapter records."""

    rows: list[dict[str, Any]] = []
    for record in records:
        rows.append({
            "period": record.year_month,
            "product_group": record.product_group,
            "pool": record.pool,
            "unit": record.unit,
            "manufactured_quantity": record.sales_quantity,
            "matched_manufactured_cogs": record.core_manufactured_cogs,
            "quantity_source_available": (
                record.source_validation_status == "SOURCE_MAPPED"
                and record.quantity_source not in {"", "UNMAPPED"}
            ),
            "core_cogs_source_available": (
                record.source_validation_status == "SOURCE_MAPPED"
                and record.scope_validation_status == "CORE_ONLY"
                and record.core_cogs_source not in {"", "UNMAPPED"}
            ),
            "quantity_source_reference": record.quantity_source,
            "core_cogs_source_reference": record.core_cogs_source,
        })
    return {"group_rows": rows}


def calculate_core_manufactured_cogs_overlap(
    baseline_source: Mapping[str, Any],
    comparison_source: Mapping[str, Any],
    selected_months: Iterable[str],
) -> CoreManufacturedCogsOverlap:
    """Calculate the production overlap with authoritative core-only sources.

    Quantity follows the existing pool-total V1 Quantity formula and Mix uses
    the existing between-product-group V1 Mix formula.  PCS and LENGTH are
    calculated separately; only their KRW effects are summed.
    """

    selected = tuple(sorted(set(str(month) for month in selected_months)))
    if not selected:
        raise ValueError("core manufactured COGS overlap requires selected months")

    base_rows = _keyed(baseline_source.get("group_rows") or [])
    comparison_rows = _keyed(comparison_source.get("group_rows") or [])
    periods = tuple(sorted({period for period, _ in set(base_rows) | set(comparison_rows)}))
    if not set(selected).issubset(periods):
        raise ValueError("core manufactured COGS overlap source is missing a selected month")

    result = CoreManufacturedCogsOverlap(
        source_validation_status="PASS",
        pool_validation_status="PASS",
        policy_status="APPLIED_CORE_ONLY",
    )
    selected_set = set(selected)
    for period in periods:
        month_quantity = 0.0
        month_mix = 0.0
        for pool in ("PCS", "LENGTH"):
            groups = tuple(group for group in _GROUPS if _POOL_BY_GROUP[group] == pool)
            pairs: list[tuple[str, Mapping[str, Any], Mapping[str, Any]]] = []
            for group in groups:
                key = (period, group)
                if key not in base_rows or key not in comparison_rows:
                    raise ValueError(f"core manufactured COGS source is missing: {key}")
                base = base_rows[key]
                comparison = comparison_rows[key]
                expected_unit = _UNIT_BY_POOL[pool]
                if (
                    str(base.get("pool")) != pool
                    or str(comparison.get("pool")) != pool
                    or str(base.get("unit")) != expected_unit
                    or str(comparison.get("unit")) != expected_unit
                ):
                    raise ValueError(f"core manufactured COGS unit/pool mismatch: {key}")
                if not bool(base.get("quantity_source_available")):
                    raise ValueError(f"base core quantity source unavailable: {key}")
                if not bool(base.get("core_cogs_source_available")):
                    raise ValueError(f"base core manufactured COGS source unavailable: {key}")
                if not bool(comparison.get("quantity_source_available")):
                    raise ValueError(f"comparison core quantity source unavailable: {key}")
                if not bool(comparison.get("core_cogs_source_available")):
                    raise ValueError(f"comparison core manufactured COGS source unavailable: {key}")
                pairs.append((group, base, comparison))

            base_total = sum(_number(base.get("manufactured_quantity")) for _, base, _ in pairs)
            comparison_total = sum(
                _number(comparison.get("manufactured_quantity"))
                for _, _, comparison in pairs
            )
            if base_total <= 0.0:
                raise ValueError(f"base core quantity denominator is not positive: {(period, pool)}")

            for group, base, comparison in pairs:
                base_quantity = _number(base.get("manufactured_quantity"))
                comparison_quantity = _number(comparison.get("manufactured_quantity"))
                if base_quantity <= 0.0:
                    raise ValueError(
                        f"base core quantity denominator is not positive: {(period, group)}"
                    )
                base_core_cogs = _number(base.get("matched_manufactured_cogs"))
                base_cogs_per_unit = base_core_cogs / base_quantity
                base_mix = base_quantity / base_total
                comparison_mix = (
                    comparison_quantity / comparison_total if comparison_total else 0.0
                )
                embedded_quantity_expense = (
                    (comparison_total - base_total) * base_mix * base_cogs_per_unit
                )
                embedded_mix_expense = (
                    comparison_total
                    * (comparison_mix - base_mix)
                    * base_cogs_per_unit
                )
                quantity_overlap = -embedded_quantity_expense
                mix_overlap = -embedded_mix_expense
                total_overlap = quantity_overlap + mix_overlap
                month_quantity += quantity_overlap
                month_mix += mix_overlap
                result.details.append({
                    "period": period,
                    "selected": period in selected_set,
                    "pool": pool,
                    "unit": _UNIT_BY_POOL[pool],
                    "product_group": group,
                    "base_quantity": base_quantity,
                    "comparison_quantity": comparison_quantity,
                    "pool_base_quantity": base_total,
                    "pool_comparison_quantity": comparison_total,
                    "base_core_manufactured_cogs": base_core_cogs,
                    "base_core_cogs_per_unit": base_cogs_per_unit,
                    "base_mix": base_mix,
                    "comparison_mix": comparison_mix,
                    "embedded_quantity_cogs_expense": embedded_quantity_expense,
                    "embedded_mix_cogs_expense": embedded_mix_expense,
                    "quantity_overlap_effect": quantity_overlap,
                    "mix_overlap_effect": mix_overlap,
                    "total_overlap_effect": total_overlap,
                    "base_quantity_source_reference": base.get("quantity_source_reference"),
                    "base_core_cogs_source_reference": base.get("core_cogs_source_reference"),
                    "comparison_quantity_source_reference": comparison.get("quantity_source_reference"),
                    "comparison_core_cogs_source_reference": comparison.get("core_cogs_source_reference"),
                    "adjustment_excluded": True,
                    "merchandise_excluded": True,
                    "validation_status": "PASS",
                })
        month_total = month_quantity + month_mix
        result.monthly_details.append({
            "period": period,
            "selected": period in selected_set,
            "quantity_overlap_effect": month_quantity,
            "mix_overlap_effect": month_mix,
            "total_overlap_effect": month_total,
            "validation_status": "PASS",
        })

    result.quantity_overlap_effect = sum(
        _number(row.get("quantity_overlap_effect"))
        for row in result.monthly_details
        if row.get("selected")
    )
    result.mix_overlap_effect = sum(
        _number(row.get("mix_overlap_effect"))
        for row in result.monthly_details
        if row.get("selected")
    )
    result.total_overlap_effect = (
        result.quantity_overlap_effect + result.mix_overlap_effect
    )
    return result
