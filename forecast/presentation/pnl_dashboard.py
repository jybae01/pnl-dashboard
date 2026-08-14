from __future__ import annotations

import math
from typing import Any, Iterable, Mapping


PNL_REQUIRED_CODES = ("revenue", "cogs", "gross_profit", "operating_profit")
MANUFACTURING_COST_CODES = (
    "raw_material", "labor", "outsourcing", "other_processing",
    "processing_total", "manufacturing_expense",
)
PRODUCT_ORDER = ("SW", "BW", "LC", "FS", "신사업")
EFFECT_CODES = {
    "sales_quantity", "sales_mix", "sales_price", "sales_fx", "tariff",
    "material_total", "manufacturing_realized", "inventory_timing", "sga_variable", "sga_fixed",
}


def build_pnl_dashboard_snapshot(
    result: Mapping[str, Any],
    monthly_results: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Build the seven-block dashboard snapshot at calculation time.

    All values come from persisted deterministic comparison outputs. This
    mapper never opens a workbook and never invents a missing business field.
    """
    monthly = tuple(monthly_results)
    if not monthly:
        raise ValueError("at least one monthly comparison result is required")
    month_numbers = tuple(_single_month(row) for row in monthly)
    if month_numbers != tuple(sorted(set(month_numbers))):
        raise ValueError("monthly comparison results must be unique and ordered")

    period = _mapping(result.get("period"), "period")
    selected_months = tuple(_integer(value, "period month") for value in _list(period.get("months"), "period months"))
    if selected_months != month_numbers:
        raise ValueError("dashboard monthly results must cover the selected period exactly")

    pnl_rows = _indexed(result.get("pnl"), "code", "P&L")
    for code in PNL_REQUIRED_CODES:
        if code not in pnl_rows:
            raise ValueError(f"required P&L line is missing: {code}")
    latest_pnl = _indexed(monthly[-1].get("pnl"), "code", "monthly P&L")
    for code in PNL_REQUIRED_CODES:
        if code not in latest_pnl:
            raise ValueError(f"required monthly P&L line is missing: {code}")

    baseline = _mapping(result.get("baseline"), "baseline model")
    comparison = _mapping(result.get("comparison"), "comparison model")
    comparison_period_types = _mapping(
        comparison.get("period_types") or {}, "comparison period types"
    )
    actual_months = tuple(
        month for month in month_numbers
        if str(comparison_period_types.get(str(month)) or "").strip() == "실적"
    )
    if actual_months and actual_months != month_numbers[:len(actual_months)]:
        raise ValueError("actual months must be a contiguous prefix of the selected period")
    raw_statement = tuple(_financial_line(row) for row in _rows(result.get("pnl"), "P&L"))
    monthly_series = tuple(_monthly_row(row) for row in monthly)
    period_values = {code: _financial_line(pnl_rows[code]) for code in PNL_REQUIRED_CODES}
    latest_values = {code: _financial_line(latest_pnl[code]) for code in PNL_REQUIRED_CODES}
    _validate_pnl_identity(pnl_rows)
    _validate_pnl_identity(latest_pnl)
    statement = tuple(
        _with_comparison_ratio(row, period_values["revenue"]["comparison"])
        for row in raw_statement
    )

    manufacturing_accounts = tuple(
        _account_row(row, effect_key="final_profit_effect")
        for row in _rows(result.get("manufacturing_accounts"), "manufacturing accounts")
    )
    sga_accounts = tuple(
        _account_row(row, effect_key="profit_effect")
        for row in _rows(result.get("sga_accounts"), "SG&A accounts")
    )
    material = _mapping(result.get("material_analysis"), "material analysis")
    cost_rows = _indexed(result.get("cost_summary"), "code", "cost summary")
    manufacturing_costs = tuple(
        _with_comparison_ratio(
            _financial_line(cost_rows[code]), period_values["revenue"]["comparison"]
        )
        for code in MANUFACTURING_COST_CODES
        if code in cost_rows
    )
    _validate_manufacturing_subtotals(cost_rows)
    _validate_material_total(material)

    effects = tuple(_effect_row(row) for row in _rows(result.get("effects"), "effects"))
    if len(effects) != len(EFFECT_CODES) or {row["code"] for row in effects} != EFFECT_CODES:
        raise ValueError("dashboard requires the exact canonical ten-effect taxonomy")
    ranked = tuple(sorted(effects, key=lambda row: (-abs(row["profit_effect"]), row["code"])))
    residual = _number(result.get("residual"), "residual")
    effects_total = _number(result.get("effects_total"), "effects_total")
    op_delta = _number(result.get("operating_profit_delta"), "operating_profit_delta")
    if not _close(sum(row["profit_effect"] for row in effects), effects_total):
        raise ValueError("effect total does not match deterministic effects")
    if not _close(effects_total + residual, op_delta):
        raise ValueError("effects_total plus residual does not match operating profit delta")

    return {
        "snapshot_version": "1",
        "identity": {
            "baseline_model_id": _text(baseline.get("id"), "baseline model id"),
            "baseline_model_name": _text(baseline.get("name"), "baseline model name"),
            "comparison_model_id": _text(comparison.get("id"), "comparison model id"),
            "comparison_model_name": _text(comparison.get("name"), "comparison model name"),
            "model_year": _integer(baseline.get("year"), "model year"),
            "start_month": month_numbers[0],
            "end_month": month_numbers[-1],
            "available_months": list(month_numbers),
            "actual_months": list(actual_months),
            "actual_through_month": actual_months[-1] if actual_months else None,
        },
        "kpis": {
            "latest_month": month_numbers[-1],
            "revenue": _kpi(latest_values["revenue"], period_values["revenue"]),
            "gross_profit": _kpi(latest_values["gross_profit"], period_values["gross_profit"]),
            "operating_profit": _kpi(latest_values["operating_profit"], period_values["operating_profit"]),
            "latest_operating_margin": _margin(latest_values["operating_profit"], latest_values["revenue"]),
            "period_operating_margin": _margin(period_values["operating_profit"], period_values["revenue"]),
        },
        "monthly_series": [
            {
                **row,
                "comparison_period_type": (
                    str(comparison_period_types.get(str(row["month"])) or "").strip() or None
                ),
            }
            for row in monthly_series
        ],
        "pnl_statement": list(statement),
        "manufacturing": {
            "cost_lines": list(manufacturing_costs),
            "material_components": {
                "nonwoven_price_ex_fx": _optional_number(material.get("nonwoven_price_ex_fx")),
                "nonwoven_jpy": _optional_number(material.get("nonwoven_jpy")),
                "materials_ex_nonwoven": _optional_number(material.get("materials_ex_nonwoven")),
                "total": _optional_number(material.get("total")),
                "jpy_fx_unit": "KRW/JPY",
                "mcm_is_separate_effect": False,
            },
            "accounts": list(manufacturing_accounts),
            "fixed_cost_policy": {
                "manufacturing_effect_includes_variable_and_fixed": True,
                "fixed_manufacturing_is_not_a_separate_top_level_effect": True,
            },
            "inventory_timing": dict(_mapping(result.get("inventory_analysis"), "inventory analysis")),
        },
        "sga": {
            "accounts": list(sga_accounts),
            "fixed_scope": "fixed SG&A accounts excluding customer freight and tariff",
        },
        "product_groups": list(_product_groups(result)),
        "key_facts": {
            "effects": list(ranked),
            "effects_total": effects_total,
            "residual": residual,
            "operating_profit_delta": op_delta,
            "reconciled": _boolean(result.get("reconciled"), "reconciled"),
        },
    }


def _single_month(result: Mapping[str, Any]) -> int:
    period = _mapping(result.get("period"), "monthly period")
    months = _list(period.get("months"), "monthly period months")
    if len(months) != 1:
        raise ValueError("monthly dashboard source must contain exactly one month")
    month = _integer(months[0], "month")
    if month < 1 or month > 12:
        raise ValueError("month must be between 1 and 12")
    return month


def _monthly_row(result: Mapping[str, Any]) -> dict[str, Any]:
    month = _single_month(result)
    pnl = _indexed(result.get("pnl"), "code", "monthly P&L")
    for code in PNL_REQUIRED_CODES:
        if code not in pnl:
            raise ValueError(f"required monthly P&L line is missing: {code}")
    _validate_pnl_identity(pnl)
    values = {code: _financial_line(pnl[code]) for code in PNL_REQUIRED_CODES}
    return {
        "month": month,
        "revenue": values["revenue"],
        "cogs": values["cogs"],
        "gross_profit": values["gross_profit"],
        "operating_profit": values["operating_profit"],
        "baseline_operating_margin": _safe_ratio(
            values["operating_profit"]["baseline"], values["revenue"]["baseline"]
        ),
        "comparison_operating_margin": _safe_ratio(
            values["operating_profit"]["comparison"], values["revenue"]["comparison"]
        ),
    }


def _kpi(latest: Mapping[str, Any], period: Mapping[str, Any]) -> dict[str, Any]:
    return {"latest": dict(latest), "period": dict(period)}


def _margin(profit: Mapping[str, Any], revenue: Mapping[str, Any]) -> dict[str, Any]:
    baseline = _safe_ratio(profit["baseline"], revenue["baseline"])
    comparison = _safe_ratio(profit["comparison"], revenue["comparison"])
    return {
        "baseline": baseline,
        "comparison": comparison,
        "delta_percentage_points": (
            comparison - baseline if baseline is not None and comparison is not None else None
        ),
    }


def _safe_ratio(numerator: float, denominator: float) -> float | None:
    return numerator / denominator * 100.0 if denominator else None


def _financial_line(row: Mapping[str, Any]) -> dict[str, Any]:
    baseline = _number(row.get("baseline"), "baseline amount")
    comparison = _number(row.get("comparison"), "comparison amount")
    delta = _number(row.get("delta"), "amount delta")
    if not _close(comparison - baseline, delta):
        raise ValueError("financial line delta is inconsistent")
    return {
        "code": _text(row.get("code"), "line code"),
        "label": _text(row.get("label") or row.get("item") or row.get("factor"), "line label"),
        "baseline": baseline,
        "comparison": comparison,
        "delta": delta,
        "comparison_ratio_to_revenue": None,
    }


def _with_comparison_ratio(row: Mapping[str, Any], comparison_revenue: float) -> dict[str, Any]:
    return {
        **row,
        "comparison_ratio_to_revenue": (
            _number(row.get("comparison"), "comparison amount") / comparison_revenue * 100.0
            if comparison_revenue else None
        ),
    }


def _account_row(row: Mapping[str, Any], *, effect_key: str) -> dict[str, Any]:
    baseline = _number(row.get("baseline_amount"), "account baseline")
    comparison = _number(row.get("comparison_amount"), "account comparison")
    delta = _number(row.get("delta"), "account delta")
    if not _close(comparison - baseline, delta):
        raise ValueError("account delta is inconsistent")
    return {
        "account": _text(row.get("account"), "account"),
        "classification": _text(row.get("classification"), "classification"),
        "section": str(row.get("section") or ""),
        "baseline": baseline,
        "comparison": comparison,
        "delta": delta,
        "profit_effect": _optional_number(row.get(effect_key)),
        "inventory_realization_rate": _optional_number(row.get("inventory_realization_rate")),
        "activity_effect": _optional_number(row.get("activity_effect")),
        "unit_effect": _optional_number(row.get("unit_effect")),
        "fixed_effect": _optional_number(row.get("fixed_effect")),
    }


def _product_groups(result: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    source = _rows(result.get("sales_groups"), "sales groups")
    by_group = {str(row.get("product_group")): row for row in source}
    if len(by_group) != len(source):
        raise ValueError("product groups must be unique")
    output = []
    for group in PRODUCT_ORDER:
        row = by_group.get(group)
        if row is None:
            continue
        baseline_revenue = _number(row.get("baseline_amount"), "product baseline revenue")
        comparison_revenue = _number(row.get("comparison_amount"), "product comparison revenue")
        baseline_cogs = _number(row.get("baseline_cogs"), "product baseline COGS")
        comparison_cogs = _number(row.get("comparison_cogs"), "product comparison COGS")
        output.append({
            "code": group,
            "display_name": "4인치 LC" if group == "LC" else group,
            "quantity_unit": "m" if group == "FS" else "PCS",
            "baseline_quantity": _number(row.get("baseline_quantity"), "product baseline quantity"),
            "comparison_quantity": _number(row.get("comparison_quantity"), "product comparison quantity"),
            "baseline_revenue": baseline_revenue,
            "comparison_revenue": comparison_revenue,
            "revenue_delta": comparison_revenue - baseline_revenue,
            "baseline_cogs": baseline_cogs,
            "comparison_cogs": comparison_cogs,
            "baseline_gross_profit": baseline_revenue - baseline_cogs,
            "comparison_gross_profit": comparison_revenue - comparison_cogs,
        })
    return tuple(output)


def _effect_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "code": _text(row.get("code"), "effect code"),
        "label": _text(row.get("factor") or row.get("label"), "effect label"),
        "profit_effect": _number(row.get("profit_effect"), "profit effect"),
    }


def _validate_pnl_identity(rows: Mapping[str, Mapping[str, Any]]) -> None:
    for side in ("baseline", "comparison"):
        revenue = _number(rows["revenue"].get(side), f"{side} revenue")
        cogs = _number(rows["cogs"].get(side), f"{side} COGS")
        gp = _number(rows["gross_profit"].get(side), f"{side} gross profit")
        if not _close(revenue - cogs, gp):
            raise ValueError("gross profit must equal revenue minus COGS")
        if "selling_expense" in rows and "general_admin" in rows:
            selling = _number(rows["selling_expense"].get(side), f"{side} selling expense")
            admin = _number(rows["general_admin"].get(side), f"{side} general admin")
            op = _number(rows["operating_profit"].get(side), f"{side} operating profit")
            if not _close(gp - selling - admin, op):
                raise ValueError("operating profit must reconcile to P&L expense lines")


def _validate_manufacturing_subtotals(rows: Mapping[str, Mapping[str, Any]]) -> None:
    parts = ("labor", "outsourcing", "other_processing")
    if "processing_total" not in rows or not all(code in rows for code in parts):
        return
    for side in ("baseline", "comparison"):
        expected = sum(_number(rows[code].get(side), f"{side} {code}") for code in parts)
        if not _close(expected, _number(rows["processing_total"].get(side), f"{side} processing total")):
            raise ValueError("processing total does not match manufacturing components")


def _validate_material_total(material: Mapping[str, Any]) -> None:
    values = tuple(material.get(key) for key in (
        "nonwoven_price_ex_fx", "nonwoven_jpy", "materials_ex_nonwoven"
    ))
    if material.get("total") is not None and all(value is not None for value in values):
        if not _close(sum(_number(value, "material component") for value in values),
                      _number(material.get("total"), "material total")):
            raise ValueError("material total does not match material components")


def _indexed(value: Any, key: str, name: str) -> dict[str, Mapping[str, Any]]:
    rows = _rows(value, name)
    output: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        identity = _text(row.get(key), f"{name} key")
        if identity in output:
            raise ValueError(f"duplicate {name} key: {identity}")
        output[identity] = row
    return output


def _rows(value: Any, name: str) -> tuple[Mapping[str, Any], ...]:
    rows = _list(value, name)
    if any(not isinstance(row, Mapping) for row in rows):
        raise ValueError(f"{name} must contain objects")
    return tuple(rows)  # type: ignore[return-value]


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be an object")
    return value


def _list(value: Any, name: str) -> list[Any] | tuple[Any, ...]:
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{name} must be a list")
    return value


def _text(value: Any, name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{name} is required")
    return text


def _integer(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    return value


def _boolean(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be a boolean")
    return value


def _number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{name} must be finite")
    return number


def _optional_number(value: Any) -> float | None:
    return None if value is None else _number(value, "optional number")


def _close(left: float, right: float) -> bool:
    return abs(left - right) <= max(1.0, abs(left), abs(right)) * 1e-9
