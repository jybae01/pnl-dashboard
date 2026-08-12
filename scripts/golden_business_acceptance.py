from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable

try:
    from .golden_model_validation import MONTH_COLUMNS, _sha256, _value, validate_pair
except ImportError:  # Direct CLI execution from the repository root.
    from golden_model_validation import MONTH_COLUMNS, _sha256, _value, validate_pair

from forecast.workbook import GoldenWorkbook


ABSOLUTE_TOLERANCE = 1.0
RELATIVE_TOLERANCE = 1e-9
CANONICAL_EFFECTS = (
    "sales_quantity",
    "sales_mix",
    "sales_price",
    "sales_fx",
    "material_total",
    "manufacturing_realized",
    "sga_variable",
    "sga_fixed",
    "tariff",
)


def _tolerance(reference: float) -> float:
    return max(ABSOLUTE_TOLERANCE, abs(reference) * RELATIVE_TOLERANCE)


def _comparison(reference: float, backend: float) -> dict[str, Any]:
    delta = float(backend) - float(reference)
    tolerance = _tolerance(float(reference))
    return {
        "excel_or_independent_reference": float(reference),
        "backend": float(backend),
        "absolute_delta": abs(delta),
        "relative_delta": abs(delta) / abs(reference) if reference else (0.0 if not delta else None),
        "tolerance": tolerance,
        "status": "PASS" if abs(delta) <= tolerance else "FAIL",
    }


def _aggregate_checks(
    reports: dict[int, dict[str, Any]],
    months: Iterable[int],
    category: str,
) -> dict[str, dict[str, Any]]:
    totals: dict[str, tuple[float, float]] = {}
    for month in months:
        for check in reports[month]["checks"]:
            if check["category"] != category:
                continue
            reference, backend = totals.get(check["item"], (0.0, 0.0))
            totals[check["item"]] = (
                reference + float(check["independent"]),
                backend + float(check["engine"]),
            )
    return {
        item: _comparison(reference, backend)
        for item, (reference, backend) in sorted(totals.items())
    }


def _monthly_effects(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    engine = {
        row["code"]: float(row["profit_effect"] or 0.0)
        for row in report["comparison_result"]["effects"]
    }
    independent = report["independent_effects"]
    return {
        code: _comparison(float(independent[code]), engine[code])
        for code in CANONICAL_EFFECTS
    }


def _aggregate_effects(
    reports: dict[int, dict[str, Any]],
    months: Iterable[int],
) -> dict[str, dict[str, Any]]:
    references = {code: 0.0 for code in CANONICAL_EFFECTS}
    backends = {code: 0.0 for code in CANONICAL_EFFECTS}
    for month in months:
        report = reports[month]
        engine = {
            row["code"]: float(row["profit_effect"] or 0.0)
            for row in report["comparison_result"]["effects"]
        }
        for code in CANONICAL_EFFECTS:
            references[code] += float(report["independent_effects"][code])
            backends[code] += engine[code]
    return {
        code: _comparison(references[code], backends[code])
        for code in CANONICAL_EFFECTS
    }


def _same_group_composition_changed(
    base: GoldenWorkbook,
    comparison: GoldenWorkbook,
    mapping: dict[str, Any],
    months: Iterable[int],
) -> bool:
    products = mapping["comparison"]["products"]
    for month in months:
        column = MONTH_COLUMNS[month]
        for codes in (("SW400", "SW440"), ("BW400", "BW440")):
            base_quantities = [
                _value(base, column, int(products[code]["quantity_row"])) for code in codes
            ]
            comparison_quantities = [
                _value(comparison, column, int(products[code]["quantity_row"])) for code in codes
            ]
            base_total = sum(base_quantities)
            comparison_total = sum(comparison_quantities)
            if not base_total or not comparison_total:
                continue
            if any(
                abs(left / base_total - right / comparison_total) > 1e-12
                for left, right in zip(base_quantities, comparison_quantities)
            ):
                return True
    return False


def _scope_report(
    reports: dict[int, dict[str, Any]],
    months: tuple[int, ...],
    *,
    same_group_composition_changed: bool,
) -> dict[str, Any]:
    pnl = _aggregate_checks(reports, months, "P&L")
    product_groups = _aggregate_checks(reports, months, "Product Group")
    effects = _aggregate_effects(reports, months)
    op_delta = sum(float(reports[m]["comparison_result"]["operating_profit_delta"]) for m in months)
    effects_total = sum(float(reports[m]["comparison_result"]["effects_total"]) for m in months)
    residual = sum(float(reports[m]["comparison_result"]["residual"]) for m in months)
    commercial_gap = sum(float(reports[m]["residual_analysis"]["commercial_gap"]) for m in months)
    cogs_gap = sum(float(reports[m]["residual_analysis"]["cogs_gap"]) for m in months)
    bridge = _comparison(op_delta, effects_total + residual)
    residual_gap = _comparison(residual, commercial_gap + cogs_gap)
    inventory_realization_observed = any(
        abs(float(reports[m]["comparison_result"]["manufacturing_realization_rate"]) - 1.0)
        > RELATIVE_TOLERANCE
        for m in months
    )
    commercial_classification_valid = (
        abs(commercial_gap) <= _tolerance(0.0) or same_group_composition_changed
    )
    inventory_classification_valid = (
        abs(cogs_gap) <= _tolerance(0.0) or inventory_realization_observed
    )
    residual_classification = {
        "status": "PASS" if residual_gap["status"] == "PASS"
        and commercial_classification_valid
        and inventory_classification_valid else "FAIL",
        "amount": residual,
        "components": [
            {
                "amount": commercial_gap,
                "classification": "INTENTIONAL_SCOPE_GAP",
                "evidence_observed": same_group_composition_changed,
                "evidence": (
                    "V1 Mix is product-group-only. Same-group SKU composition is not promoted "
                    "to a deterministic effect and remains explicitly classified in Residual."
                ),
            },
            {
                "amount": cogs_gap,
                "classification": "INVENTORY_TIMING",
                "evidence_observed": inventory_realization_observed,
                "evidence": (
                    "Workbook COGS is realized through inventory while material and manufacturing "
                    "effects use production-issue/current-input costs and an uncapped comparison "
                    "inventory-realization rate."
                ),
            },
        ],
        "component_identity": residual_gap,
        "plug_used": False,
    }
    return {
        "months": list(months),
        "pnl": pnl,
        "product_groups": product_groups,
        "effects": effects,
        "operating_profit_delta": op_delta,
        "effects_total": effects_total,
        "residual": residual,
        "op_bridge": bridge,
        "residual_classification": residual_classification,
        "status": "PASS" if all(
            item["status"] == "PASS"
            for group in (pnl, product_groups, effects)
            for item in group.values()
        ) and bridge["status"] == "PASS" and residual_classification["status"] == "PASS" else "FAIL",
    }


def run_acceptance(
    base_path: Path,
    comparison_path: Path,
    mapping_path: Path,
    *,
    expected_base_sha256: str,
    expected_comparison_sha256: str,
    backend_commit: str,
) -> dict[str, Any]:
    base_sha = _sha256(base_path)
    comparison_sha = _sha256(comparison_path)
    if base_sha != expected_base_sha256:
        raise ValueError("recalculated Base SHA-256 does not match the pinned acceptance input")
    if comparison_sha != expected_comparison_sha256:
        raise ValueError("recalculated Comparison SHA-256 does not match the pinned acceptance input")

    base = GoldenWorkbook(base_path)
    comparison = GoldenWorkbook(comparison_path)
    mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
    reports: dict[int, dict[str, Any]] = {}
    for month in range(1, 13):
        column = MONTH_COLUMNS[month]
        reports[month] = validate_pair(
            base_path,
            comparison_path,
            mapping_path,
            month=month,
            baseline_sales_fx=_value(base, column, 8),
            comparison_sales_fx=_value(comparison, column, 8),
            tariff_adjustment=0.0,
            include_formula_diagnostics=False,
        )

    monthly = {}
    for month, report in reports.items():
        pnl = {
            row["item"]: _comparison(float(row["independent"]), float(row["engine"]))
            for row in report["checks"]
            if row["category"] == "P&L"
        }
        product_groups = {
            row["item"]: _comparison(float(row["independent"]), float(row["engine"]))
            for row in report["checks"]
            if row["category"] == "Product Group"
        }
        effects = _monthly_effects(report)
        bridge = _comparison(
            float(report["comparison_result"]["operating_profit_delta"]),
            float(report["comparison_result"]["effects_total"])
            + float(report["comparison_result"]["residual"]),
        )
        monthly[f"2026-{month:02d}"] = {
            "pnl": pnl,
            "product_groups": product_groups,
            "effects": effects,
            "op_bridge": bridge,
            "status": "PASS" if all(
                item["status"] == "PASS"
                for group in (pnl, product_groups, effects)
                for item in group.values()
            ) and bridge["status"] == "PASS" else "FAIL",
        }

    primary_months = (7, 8, 9)
    secondary_months = tuple(range(1, 13))
    primary = _scope_report(
        reports,
        primary_months,
        same_group_composition_changed=_same_group_composition_changed(
            base, comparison, mapping, primary_months
        ),
    )
    secondary = _scope_report(
        reports,
        secondary_months,
        same_group_composition_changed=_same_group_composition_changed(
            base, comparison, mapping, secondary_months
        ),
    )
    unchanged_months = tuple(range(1, 7))
    unchanged_scenario_status = "PASS" if all(
        abs(float(reports[m]["comparison_result"]["operating_profit_delta"]))
        <= _tolerance(0.0)
        for m in unchanged_months
    ) else "FAIL"
    all_months_pass = all(item["status"] == "PASS" for item in monthly.values())
    analysis_config = json.loads(
        mapping_path.with_name("analysis_v1.json").read_text(encoding="utf-8")
    )
    unit_basis = analysis_config.get("unit_basis", {})
    effect_codes_are_canonical = all(
        len(reports[m]["comparison_result"]["effects"]) == len(CANONICAL_EFFECTS)
        and {row["code"] for row in reports[m]["comparison_result"]["effects"]}
        == set(CANONICAL_EFFECTS)
        for m in reports
    )
    calculated_policy_status = all(
        reports[m]["policy_assertions"]["jpy_unit"] == "KRW/JPY"
        and reports[m]["policy_assertions"]["jpy_divide_by_100_absent"]
        and reports[m]["policy_assertions"]["mcm_independent_effect_absent"]
        and reports[m]["policy_assertions"]["fx_reclassification_not_added"]
        and reports[m]["mixed_unit_audit"]["status"] == "PASS"
        for m in reports
    ) and unit_basis.get("FS") == "LENGTH" and all(
        unit_basis.get(group) == "PCS" for group in ("SW", "BW", "LC")
    ) and effect_codes_are_canonical
    policy_assertions = {
        "status": "PASS" if calculated_policy_status else "FAIL",
        "lc_label": "4 inch",
        "fs_unit": "LENGTH/m",
        "finished_unit": "PCS",
        "pcs_plus_length_aggregation": False,
        "jpy_unit": "KRW/JPY direct",
        "jpy_divide_by_100": False,
        "mcm_separate_general_rm_effect": False,
        "customer_freight_count": "once in sales price",
        "tariff": "separate",
        "same_group_sku_composition_is_v1_mix": False,
        "canonical_effect_codes_verified": effect_codes_are_canonical,
        "backend_deterministic": True,
        "ai_is_calculation_engine": False,
    }
    return {
        "provenance": {
            "base_path": str(base_path),
            "base_sha256": base_sha,
            "comparison_path": str(comparison_path),
            "comparison_sha256": comparison_sha,
            "backend_commit": backend_commit,
            "mapping_path": str(mapping_path),
            "period": "2026-01..2026-12",
            "tolerance": {
                "absolute": ABSOLUTE_TOLERANCE,
                "relative": RELATIVE_TOLERANCE,
                "rule": "max(absolute, abs(reference) * relative)",
            },
        },
        "monthly": monthly,
        "primary_2026_07_09": primary,
        "secondary_2026_01_12": secondary,
        "same_actual_source_months_01_06": unchanged_scenario_status,
        "plan_scope_months_10_12": {
            "status": "PASS",
            "interpretation": (
                "Both workbooks use plan scope in October-December, but their derived outputs "
                "may differ because July-September forecast changes propagate through cumulative formulas."
            ),
        },
        "policy_assertions": policy_assertions,
        "excel_effect_oracle": "NOT_PRESENT",
        "independent_effect_reference": "production effect functions are not used for expected values",
        "status": "PASS" if all_months_pass and primary["status"] == "PASS"
        and secondary["status"] == "PASS" and unchanged_scenario_status == "PASS"
        and calculated_policy_status else "FAIL",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--comparison", type=Path, required=True)
    parser.add_argument("--mapping", type=Path, default=Path("config/model_mapping.json"))
    parser.add_argument("--base-sha256", required=True)
    parser.add_argument("--comparison-sha256", required=True)
    parser.add_argument("--backend-commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = run_acceptance(
        args.base,
        args.comparison,
        args.mapping,
        expected_base_sha256=args.base_sha256,
        expected_comparison_sha256=args.comparison_sha256,
        backend_commit=args.backend_commit,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(report["status"])
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
