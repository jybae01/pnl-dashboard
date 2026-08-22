from __future__ import annotations

from collections.abc import Iterable
import re
from typing import Any

from .schema import AnalysisScenario, ProductionEvidenceRecord


PRODUCT_ORDER = ("FS", "SW", "BW", "LC")
WEIGHTED_FORMULA_POLICY = (
    "SUM(selected-period production amount) / "
    "SUM(selected-period production quantity)"
)


def _weighted_unit_cost(amount: float, quantity: float) -> float | None:
    return amount / quantity if quantity else None


def _group_records(
    scenario: AnalysisScenario,
    product_group: str,
) -> list[ProductionEvidenceRecord]:
    return [
        row for row in scenario.production_evidence
        if row.product_group == product_group
    ]


def _unique(values: Iterable[Any]) -> list[Any]:
    return list(dict.fromkeys(values))


def _source_cells(reference: str) -> list[str]:
    return [cell.strip() for cell in re.split(r"\s*\+\s*", reference) if cell.strip()]


def _aggregate_side(rows: list[ProductionEvidenceRecord]) -> dict[str, Any]:
    quantity = sum(row.quantity for row in rows)
    amount = sum(row.amount for row in rows)
    return {
        "quantity": quantity,
        "amount": amount,
        "weighted_unit_cost": _weighted_unit_cost(amount, quantity),
        "quantity_sources": _unique(
            source
            for row in rows
            for source in _source_cells(row.quantity_source)
            if source
        ),
        "amount_sources": _unique(
            source
            for row in rows
            for source in _source_cells(row.amount_source)
            if source
        ),
    }


def _evidence_row(
    product_group: str,
    baseline_rows: list[ProductionEvidenceRecord],
    comparison_rows: list[ProductionEvidenceRecord],
) -> dict[str, Any]:
    if not baseline_rows or not comparison_rows:
        raise ValueError(f"production evidence is missing for {product_group}")
    sample = baseline_rows[0]
    expected_unit = "LENGTH" if product_group == "FS" else "PCS"
    if any(row.unit_basis != expected_unit for row in baseline_rows + comparison_rows):
        raise ValueError(f"production evidence unit mismatch for {product_group}")
    if any(row.formula_policy != WEIGHTED_FORMULA_POLICY for row in baseline_rows + comparison_rows):
        raise ValueError(f"production evidence formula policy mismatch for {product_group}")

    baseline = _aggregate_side(baseline_rows)
    comparison = _aggregate_side(comparison_rows)
    baseline_cost = baseline["weighted_unit_cost"]
    comparison_cost = comparison["weighted_unit_cost"]
    quantity_rows = _unique(
        source_row
        for row in baseline_rows + comparison_rows
        for source_row in row.quantity_source_rows
    )
    amount_rows = _unique(
        source_row
        for row in baseline_rows + comparison_rows
        for source_row in row.amount_source_rows
    )
    return {
        "process": sample.process,
        "production_basis": product_group,
        "unit": "m" if expected_unit == "LENGTH" else "PCS",
        "unit_cost_unit": "원/m" if expected_unit == "LENGTH" else "원/PCS",
        "baseline_quantity": baseline["quantity"],
        "comparison_quantity": comparison["quantity"],
        "quantity_delta": comparison["quantity"] - baseline["quantity"],
        "baseline_amount": baseline["amount"],
        "comparison_amount": comparison["amount"],
        "baseline_weighted_unit_cost": baseline_cost,
        "comparison_weighted_unit_cost": comparison_cost,
        "unit_cost_delta": (
            comparison_cost - baseline_cost
            if baseline_cost is not None and comparison_cost is not None
            else None
        ),
        "selected_period": sorted(
            set(row.year_month for row in baseline_rows + comparison_rows)
        ),
        "quantity_source_rows": quantity_rows,
        "amount_source_rows": amount_rows,
        "baseline_quantity_sources": baseline["quantity_sources"],
        "comparison_quantity_sources": comparison["quantity_sources"],
        "baseline_amount_sources": baseline["amount_sources"],
        "comparison_amount_sources": comparison["amount_sources"],
        "aggregation_basis": sample.aggregation_basis,
        "formula_policy": WEIGHTED_FORMULA_POLICY,
        "source_validation_status": "SOURCE_MAPPED",
    }


def calculate_production_evidence(
    baseline: AnalysisScenario,
    comparison: AnalysisScenario,
) -> list[dict[str, Any]]:
    """Build selected-period inventory-ledger evidence without touching Effects."""

    rows = [
        _evidence_row(
            group,
            _group_records(baseline, group),
            _group_records(comparison, group),
        )
        for group in PRODUCT_ORDER
    ]

    back_rows = [row for row in rows if row["production_basis"] in {"SW", "BW", "LC"}]
    if any(row["unit"] != "PCS" for row in back_rows):
        raise ValueError("back-process production evidence must use PCS only")
    base_quantity = sum(row["baseline_quantity"] for row in back_rows)
    comparison_quantity = sum(row["comparison_quantity"] for row in back_rows)
    base_amount = sum(row["baseline_amount"] for row in back_rows)
    comparison_amount = sum(row["comparison_amount"] for row in back_rows)
    base_cost = _weighted_unit_cost(base_amount, base_quantity)
    comparison_cost = _weighted_unit_cost(comparison_amount, comparison_quantity)
    rows.append({
        "process": "후공정 합계",
        "production_basis": "SW+BW+LC",
        "unit": "PCS",
        "unit_cost_unit": "원/PCS",
        "baseline_quantity": base_quantity,
        "comparison_quantity": comparison_quantity,
        "quantity_delta": comparison_quantity - base_quantity,
        "baseline_amount": base_amount,
        "comparison_amount": comparison_amount,
        "baseline_weighted_unit_cost": base_cost,
        "comparison_weighted_unit_cost": comparison_cost,
        "unit_cost_delta": (
            comparison_cost - base_cost
            if base_cost is not None and comparison_cost is not None
            else None
        ),
        "selected_period": _unique(
            month for row in back_rows for month in row["selected_period"]
        ),
        "quantity_source_rows": _unique(
            source_row for row in back_rows for source_row in row["quantity_source_rows"]
        ),
        "amount_source_rows": _unique(
            source_row for row in back_rows for source_row in row["amount_source_rows"]
        ),
        "baseline_quantity_sources": _unique(
            source for row in back_rows for source in row["baseline_quantity_sources"]
        ),
        "comparison_quantity_sources": _unique(
            source for row in back_rows for source in row["comparison_quantity_sources"]
        ),
        "baseline_amount_sources": _unique(
            source for row in back_rows for source in row["baseline_amount_sources"]
        ),
        "comparison_amount_sources": _unique(
            source for row in back_rows for source in row["comparison_amount_sources"]
        ),
        "aggregation_basis": "SW + BW + LC PCS weighted total",
        "formula_policy": WEIGHTED_FORMULA_POLICY,
        "source_validation_status": "SOURCE_MAPPED",
    })
    return rows
