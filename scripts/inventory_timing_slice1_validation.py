from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from forecast.analysis_export import write_comparison_audit_workbook
from forecast.comparison import GenericComparisonEngine, PeriodOption
from forecast.storage import ModelMeta
from forecast.workbook import GoldenWorkbook


MONTH_COLUMNS = {month: chr(ord("E") + month - 1) for month in range(1, 13)}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _meta(identifier: str, name: str, model_type: str, path: Path) -> ModelMeta:
    return ModelMeta(
        identifier,
        name,
        model_type,
        2026,
        1,
        12,
        "2026-01-01",
        "V1",
        True,
        path.name,
        "slice1-validation",
    )


def _number(value: Any) -> float:
    return float(value) if isinstance(value, (int, float)) else 0.0


def _mapped(workbook: GoldenWorkbook, column: str, spec: Any) -> float:
    if isinstance(spec, int):
        return _number(workbook.value(f"{column}{spec}"))
    if isinstance(spec, list):
        return sum(_number(workbook.value(f"{column}{row}")) for row in spec)
    if isinstance(spec, dict):
        return sum(_number(workbook.value(f"{column}{row}")) for row in spec.get("add", ())) - sum(
            _number(workbook.value(f"{column}{row}")) for row in spec.get("subtract", ())
        )
    return 0.0


def _summary(
    result: Any,
    comparison_workbook: GoldenWorkbook,
    mapping_payload: dict[str, Any],
    *,
    legacy_realized_override: float | None = None,
) -> dict[str, Any]:
    effect_map = {
        row["code"]: float(row.get("profit_effect") or 0.0)
        for row in result.effects
    }
    current_manufacturing = float(effect_map["manufacturing_realized"])
    comparison_mapping = mapping_payload["comparison"]
    legacy_realized = legacy_realized_override
    if legacy_realized is None:
        result_months = tuple(int(month) for month in result.period["months"])
        if len(result_months) != 1:
            raise ValueError("aggregate legacy realization requires a monthly override")
        month = result_months[0]
        column = MONTH_COLUMNS[month]
        old_input = sum(
            _mapped(comparison_workbook, column, comparison_mapping["cost_rows"][code])
            for code in ("raw_material", "labor", "outsourcing", "other_processing")
        )
        cogs = _number(
            comparison_workbook.value(
                f"{column}{comparison_mapping['pnl_rows']['cogs']}"
            )
        )
        old_rate = cogs / old_input if old_input else 0.0
        legacy_realized = current_manufacturing * old_rate
    inventory = result.inventory_analysis
    return {
        "period": result.period,
        "operating_profit_delta": result.operating_profit_delta,
        "effects": effect_map,
        "effects_total": result.effects_total,
        "residual": result.residual,
        "bridge_total": result.effects_total + result.residual,
        "bridge_pass": abs(
            result.effects_total + result.residual - result.operating_profit_delta
        ) <= max(1.0, abs(result.operating_profit_delta) * 1e-9),
        "manufacturing_occurrence_effect": current_manufacturing,
        "legacy_realization_applied_effect": legacy_realized,
        "realization_removal_difference": current_manufacturing - legacy_realized,
        "current_manufacturing_cost_effect": inventory.get(
            "current_manufacturing_cost_effect"
        ),
        "current_cost_related_effects": inventory.get("current_cost_related_effects"),
        "double_counting_gap": inventory.get("current_cost_explanation_gap"),
        "additive_bridge_status": inventory.get("additive_bridge_status"),
        "inventory_timing": inventory,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("base", type=Path)
    parser.add_argument("comparison", type=Path)
    parser.add_argument("--mapping", type=Path, default=Path("config/model_mapping.json"))
    parser.add_argument("--start-month", type=int, default=7)
    parser.add_argument("--end-month", type=int, default=9)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--workbook-output", type=Path)
    args = parser.parse_args()

    base = args.base.resolve()
    comparison = args.comparison.resolve()
    mapping = args.mapping.resolve()
    months = tuple(range(args.start_month, args.end_month + 1))
    engine = GenericComparisonEngine(mapping)
    mapping_payload = json.loads(mapping.read_text(encoding="utf-8"))
    comparison_workbook = GoldenWorkbook(comparison)
    base_meta = _meta("slice1-base", "Golden Base", "계획", base)
    comparison_meta = _meta("slice1-comparison", "Golden Comparison", "비교", comparison)

    monthly: list[dict[str, Any]] = []
    for month in months:
        result = engine.compare(
            base_meta,
            base,
            comparison_meta,
            comparison,
            PeriodOption(f"M{month:02d}", f"{month}월", (month,), "월"),
        )
        monthly.append(_summary(result, comparison_workbook, mapping_payload))

    period = PeriodOption(
        f"R{args.start_month:02d}_{args.end_month:02d}",
        f"{args.start_month}~{args.end_month}월",
        months,
        "범위",
    )
    aggregate = engine.compare(base_meta, base, comparison_meta, comparison, period)
    aggregate_dict = asdict(aggregate)
    aggregate_summary = _summary(
        aggregate,
        comparison_workbook,
        mapping_payload,
        legacy_realized_override=sum(
            float(item["legacy_realization_applied_effect"]) for item in monthly
        ),
    )
    report = {
        "sources": {
            "base": {"path": str(base), "sha256": _sha256(base)},
            "comparison": {"path": str(comparison), "sha256": _sha256(comparison)},
            "mapping": str(mapping),
        },
        "monthly": monthly,
        "aggregate": aggregate_summary,
    }

    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    if args.workbook_output:
        args.workbook_output.parent.mkdir(parents=True, exist_ok=True)
        sales_analysis = aggregate_dict.get("sales_analysis", {})
        write_comparison_audit_workbook(
            args.workbook_output,
            result=aggregate_dict,
            sales_rows=sales_analysis.get("rows", ()),
            sales_totals=sales_analysis.get("totals", {}),
            baseline_fx=float(sales_analysis.get("baseline_fx_krw_per_usd") or 0.0),
            comparison_fx=float(sales_analysis.get("comparison_fx_krw_per_usd") or 0.0),
            baseline_path=base,
            comparison_path=comparison,
            mapping_path=mapping,
        )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
