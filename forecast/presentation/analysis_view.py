from __future__ import annotations

from typing import Any

from ..sales_comparison import calculate_sales_effect_rows, sales_effect_totals
from .formatting import format_million


PRODUCT_ORDER = ("SW", "BW", "LC", "FS", "신사업")


def _number(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _effect_map(result: dict[str, Any]) -> dict[str, float]:
    return {
        str(row.get("code")): _number(row.get("profit_effect"))
        for row in result.get("effects", [])
    }


def _pnl_map(result: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(row.get("code")): row for row in result.get("pnl", [])}


def _sales_view(result: dict[str, Any], baseline_fx: float, comparison_fx: float) -> dict[str, Any]:
    analysis = result.get("sales_analysis") or {}
    if analysis.get("rows"):
        calculated = list(analysis["rows"])
        totals = dict(analysis.get("totals") or {})
        baseline_fx = _number(analysis.get("baseline_fx_krw_per_usd"))
        comparison_fx = _number(analysis.get("comparison_fx_krw_per_usd"))
    else:
        # Backward compatibility for comparison results stored before
        # sales_analysis became part of the deterministic Result schema.
        legacy_rows = calculate_sales_effect_rows(
            result.get("sales_groups", []), baseline_fx, comparison_fx
        )
        calculated = [row.to_dict() for row in legacy_rows]
        totals = sales_effect_totals(legacy_rows)
    by_group = {str(row.get("product_group")): row for row in calculated}
    rows: list[dict[str, Any]] = []
    for group in PRODUCT_ORDER:
        row = by_group.get(group)
        if row is None:
            continue
        unit = "m" if group == "FS" else "PCS"
        rows.append({
            "product_group": group,
            "quantity_unit": unit,
            "baseline_quantity": row["baseline_quantity"],
            "comparison_quantity": row["comparison_quantity"],
            "quantity_delta": row["quantity_delta"],
            "baseline_amount": row["baseline_amount"],
            "comparison_amount": row["comparison_amount"],
            "revenue_delta": row["comparison_amount"] - row["baseline_amount"],
            "baseline_gross_margin_rate": row["baseline_gross_margin_rate"],
            "quantity_effect": row["quantity_effect"],
            "pure_price_delta_usd": row["pure_price_delta_usd"],
            "pure_price_effect": row["pure_price_effect"],
            "internal_effect": row["quantity_effect"] + row["pure_price_effect"],
            "sales_fx_effect": row["sales_fx_effect"],
            "total_sales_effect": row["total_sales_effect"],
        })

    baseline_amount = sum(_number(row.get("baseline_amount")) for row in calculated)
    baseline_gp = sum(
        _number(row.get("baseline_amount")) * _number(row.get("baseline_gross_margin_rate"))
        for row in calculated
    )
    rows.append({
        "product_group": "Total",
        "quantity_unit": None,
        "baseline_quantity": None,
        "comparison_quantity": None,
        "quantity_delta": None,
        "baseline_amount": baseline_amount,
        "comparison_amount": sum(_number(row.get("comparison_amount")) for row in calculated),
        "revenue_delta": sum(
            _number(row.get("comparison_amount")) - _number(row.get("baseline_amount"))
            for row in calculated
        ),
        "baseline_gross_margin_rate": baseline_gp / baseline_amount if baseline_amount else 0.0,
        "quantity_effect": totals["quantity_effect"],
        "pure_price_delta_usd": None,
        "pure_price_effect": totals["pure_price_effect"],
        "internal_effect": totals["quantity_effect"] + totals["pure_price_effect"],
        "sales_fx_effect": totals["sales_fx_effect"],
        "total_sales_effect": totals["total_sales_effect"],
    })
    return {
        "baseline_fx_krw_per_usd": baseline_fx,
        "comparison_fx_krw_per_usd": comparison_fx,
        "rows": rows,
        "totals": totals,
    }


def _activity_view(result: dict[str, Any]) -> list[dict[str, Any]]:
    production = result.get("production", [])

    def sum_prefix(prefix: str, field: str) -> float:
        return sum(
            _number(row.get(field))
            for row in production
            if str(row.get("code", "")).startswith(prefix)
        )

    rows: list[dict[str, Any]] = []
    for process, group, unit in (
        ("전공정", "FS", "m"),
        ("후공정", "SW", "PCS"),
        ("후공정", "BW", "PCS"),
        ("후공정", "LC", "PCS"),
    ):
        baseline = sum_prefix(group, "baseline")
        comparison = sum_prefix(group, "comparison")
        rows.append({
            "process": process,
            "production_basis": group,
            "unit": unit,
            "baseline": baseline,
            "comparison": comparison,
            "delta": comparison - baseline,
            "change_rate": ((comparison / baseline) - 1.0) if baseline else None,
            "calculation_driver": process == "전공정",
        })
    back_rows = [row for row in rows if row["process"] == "후공정"]
    baseline = sum(row["baseline"] for row in back_rows)
    comparison = sum(row["comparison"] for row in back_rows)
    rows.append({
        "process": "후공정 합계",
        "production_basis": "SW+BW+LC",
        "unit": "PCS",
        "baseline": baseline,
        "comparison": comparison,
        "delta": comparison - baseline,
        "change_rate": ((comparison / baseline) - 1.0) if baseline else None,
        "calculation_driver": True,
    })
    return rows


def _material_view(result: dict[str, Any]) -> dict[str, Any]:
    detailed = result.get("material_analysis") or {}
    source_rows = detailed.get("product_groups") or []
    by_group = {str(row.get("product_group")): row for row in source_rows}
    rows: list[dict[str, Any]] = []
    for group in PRODUCT_ORDER:
        source = by_group.get(group)
        if source is None:
            continue
        rows.append({
            "product_group": group,
            "unit": "원/m" if group == "FS" else "원/PCS",
            "baseline_unit_cost": source.get("baseline_unit_cost"),
            "comparison_unit_cost": source.get("comparison_unit_cost"),
            "unit_cost_delta": source.get("unit_cost_delta"),
            "nonwoven_price_ex_fx": source.get("nonwoven_price_ex_fx"),
            "nonwoven_jpy": source.get("nonwoven_jpy"),
            "materials_ex_nonwoven": source.get("materials_ex_nonwoven"),
            "total": source.get("total"),
            "calculation_status": source.get(
                "calculation_status",
                "미산출: 제품군별 원재료·부직포·JPY observable mapping 필요",
            ),
        })
    return {
        "rows": rows,
        "total": detailed.get("total"),
        "nonwoven_price_ex_fx": detailed.get("nonwoven_price_ex_fx"),
        "nonwoven_jpy": detailed.get("nonwoven_jpy"),
        "materials_ex_nonwoven": detailed.get("materials_ex_nonwoven"),
        "jpy_fx_unit": "KRW/JPY",
        "calculation_status": detailed.get(
            "calculation_status",
            "미산출: 현재 Golden Model 비교 매핑에 제품군별 원재료·부직포·JPY 데이터가 없음",
        ),
    }


def _manufacturing_view(result: dict[str, Any]) -> dict[str, Any]:
    accounts = list(result.get("manufacturing_accounts") or [])
    return {
        "activities": _activity_view(result),
        "accounts": accounts,
        "variable_effect": sum(
            _number(row.get("final_profit_effect"))
            for row in accounts
            if row.get("classification") == "variable" and row.get("final_profit_effect") is not None
        ),
        "fixed_effect": sum(
            _number(row.get("final_profit_effect"))
            for row in accounts
            if row.get("classification") == "fixed" and row.get("final_profit_effect") is not None
        ),
        "has_uncomputed_accounts": any(row.get("final_profit_effect") is None for row in accounts),
    }


def _sga_view(result: dict[str, Any]) -> dict[str, Any]:
    accounts = list(result.get("sga_accounts") or [])
    return {
        "accounts": accounts,
        "variable_effect": sum(
            _number(row.get("profit_effect"))
            for row in accounts if row.get("classification") == "variable"
        ),
        "fixed_effect": sum(
            _number(row.get("profit_effect"))
            for row in accounts if row.get("classification") == "fixed"
        ),
        "tariff_effect": sum(
            _number(row.get("profit_effect"))
            for row in accounts if row.get("classification") == "tariff"
        ),
    }


def _summary_view(
    result: dict[str, Any],
    sales: dict[str, Any],
    material: dict[str, Any],
    manufacturing: dict[str, Any],
    sga: dict[str, Any],
) -> dict[str, Any]:
    pnl = _pnl_map(result)
    effects = _effect_map(result)
    material_effect = material.get("total")
    if material_effect is None:
        material_effect = sum(effects.get(code, 0.0) for code in (
            "product_raw_material", "semi_raw_material", "customs_refund"
        ))
    tariff_effect = effects.get("tariff", sga.get("tariff_effect", 0.0))
    categories = [
        ("판매수량", sales["totals"]["quantity_effect"]),
        ("판매단가", sales["totals"]["pure_price_effect"]),
        ("매출환율", sales["totals"]["sales_fx_effect"]),
        ("원부재료", material_effect),
        ("변동 제조경비", manufacturing["variable_effect"]),
        ("고정 제조경비", manufacturing["fixed_effect"]),
        ("변동 판관비", sga["variable_effect"]),
        ("고정 판관비", sga["fixed_effect"]),
        ("관세", tariff_effect),
    ]
    effects_total = _number(result.get("effects_total"))
    identified_other = effects_total - sum(value for _, value in categories)
    rows = [{"factor": label, "profit_effect": value} for label, value in categories]
    rows.extend([
        {"factor": "기타 주요 손익요인", "profit_effect": identified_other},
        {"factor": "영업이익 증감", "profit_effect": _number(result.get("operating_profit_delta"))},
    ])
    ranked = sorted(rows[:-1], key=lambda row: abs(row["profit_effect"]), reverse=True)
    narrative_parts = []
    for row in ranked[:3]:
        value = row["profit_effect"]
        if not value:
            continue
        direction = "개선" if value > 0 else "악화"
        narrative_parts.append(f"{row['factor']} {format_million(abs(value))} {direction}")
    narrative = (
        f"영업이익은 기준 대비 {format_million(abs(_number(result.get('operating_profit_delta'))))} "
        f"{'개선' if _number(result.get('operating_profit_delta')) >= 0 else '감소'}했습니다."
    )
    if narrative_parts:
        narrative += " 주요 변동은 " + ", ".join(narrative_parts) + "입니다."
    return {
        "baseline_operating_profit": _number(pnl.get("operating_profit", {}).get("baseline")),
        "comparison_operating_profit": _number(pnl.get("operating_profit", {}).get("comparison")),
        "operating_profit_delta": _number(result.get("operating_profit_delta")),
        "effects_total": effects_total,
        "residual": _number(result.get("residual")),
        "reconciled": bool(result.get("reconciled")),
        "status": "PASS" if result.get("reconciled") else "CHECK",
        "bridge": rows,
        "effect_ranking": [
            {"rank": rank, "factor": row["factor"], "profit_effect": row["profit_effect"]}
            for rank, row in enumerate(ranked, 1)
        ],
        "narrative": narrative,
    }


def build_analysis_view(
    result: dict[str, Any],
    *,
    baseline_sales_fx: float = 1480.0,
    comparison_sales_fx: float = 1480.0,
) -> dict[str, Any]:
    """Create the UI/AI result model from deterministic engine output.

    This is the only presentation adapter. Streamlit renders this structure and
    never reads Golden Model cells or performs financial calculations itself.
    Raw monetary values remain KRW until a renderer calls the common formatter.
    """
    sales = _sales_view(result, baseline_sales_fx, comparison_sales_fx)
    material = _material_view(result)
    manufacturing = _manufacturing_view(result)
    sga = _sga_view(result)
    summary = _summary_view(result, sales, material, manufacturing, sga)
    return {
        "metadata": {
            "baseline": result.get("baseline", {}),
            "comparison": result.get("comparison", {}),
            "period": result.get("period", {}),
            "currency_display_unit": "KRW million",
            "raw_currency_unit": "KRW",
            "delta_definition": "comparison - baseline",
            "profit_effect_sign": "+ means OP improvement; - means deterioration",
        },
        "summary": summary,
        "sales": sales,
        "material": material,
        "manufacturing": manufacturing,
        "sga": sga,
    }
