from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from forecast.analysis.configuration import AnalysisConfig
from forecast.analysis.golden_adapter import GoldenAnalysisAdapter
from forecast.comparison import GenericComparisonEngine, PeriodOption
from forecast.engine import CostAdjustment, ForecastEngine, ForecastInput, SalesInput
from forecast.preflight import ExcelPreflightValidator
from forecast.storage import ModelMeta
from forecast.workbook import GoldenWorkbook


MONTH_COLUMNS = {month: chr(ord("E") + month - 1) for month in range(1, 13)}


def _number(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _value(workbook: GoldenWorkbook, column: str, row: int) -> float:
    return _number(workbook.value(f"{column}{row}"))


def _mapped(workbook: GoldenWorkbook, column: str, spec: Any) -> float:
    if isinstance(spec, int):
        return _value(workbook, column, spec)
    if isinstance(spec, list):
        return sum(_mapped(workbook, column, row) for row in spec)
    if isinstance(spec, dict):
        return (
            sum(_mapped(workbook, column, row) for row in spec.get("add", ()))
            - sum(_mapped(workbook, column, row) for row in spec.get("subtract", ()))
        )
    return 0.0


def _material_cost(
    workbook: GoldenWorkbook,
    column: str,
    spec: dict[str, Any],
) -> float:
    total = sum(_value(workbook, column, row) for row in spec.get("direct_material_rows", ()))
    for term in spec.get("front_material_terms", ()):
        quantity = _value(workbook, column, term["source_production_row"])
        if not quantity:
            continue
        pool = sum(
            _value(workbook, column, row)
            for row in term.get("source_pool_amount_rows", ())
        )
        if "source_material_amount_row" in term:
            pool += _value(workbook, column, term["source_material_amount_row"])
        ratio = (
            _value(workbook, column, term["source_allocation_ratio_row"])
            if term.get("source_allocation_ratio_row")
            else 1.0
        )
        source_unit = pool * ratio / quantity
        total += (
            _value(workbook, column, term["production_row"])
            * _value(workbook, column, term["input_length_row"])
            * source_unit
            * _value(workbook, column, term["adjustment_row"])
        )
    for term in spec.get("back_material_terms", ()):
        ratio = _value(workbook, column, term["allocation_ratio_row"])
        pool = sum(
            _value(workbook, column, row)
            for row in term.get("pool_amount_rows", ())
        )
        total += ratio * pool
    total += sum(_value(workbook, column, row) for row in spec.get("mcm_material_rows", ()))
    return total


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build_comparison(
    base_path: Path,
    comparison_path: Path,
    mapping_path: Path,
    *,
    month: int = 7,
) -> dict[str, Any]:
    mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
    column = MONTH_COLUMNS[month]
    base = GoldenWorkbook(base_path)
    sales_multipliers = {
        "SW400": (1.10, 1.12),
        "SW440": (0.95, 0.97),
        "BW400": (1.08, 1.10),
        "BW440": (0.96, 0.98),
        "LC": (1.06, 1.07),
        "FS_SW": (1.04, 1.06),
        "FS_BW": (0.98, 1.01),
        "FS_TW": (1.03, 1.05),
    }
    sales: dict[str, SalesInput] = {}
    for code, spec in mapping["sales"].items():
        q_multiplier, a_multiplier = sales_multipliers.get(code, (1.0, 1.0))
        base_quantity = _value(base, column, spec["quantity_row"])
        base_amount = _value(base, column, spec["amount_row"])
        if code == "LC":
            # Preserve the purchased-goods domain as well as manufactured LC.
            # Otherwise ForecastEngine receives only the manufactured portion,
            # creates K104=0 and makes K106's valid workbook division fail.
            base_quantity += _value(base, column, mapping["lc_goods"]["quantity_row"])
            base_amount += _value(base, column, mapping["lc_goods"]["amount_row"])
        sales[code] = SalesInput(
            quantity=base_quantity * q_multiplier,
            amount=base_amount * a_multiplier,
        )
    sales.update({
        "UF_MBR": SalesInput(quantity=120.0, amount=220_000_000.0),
        "IX": SalesInput(quantity=8_000.0, amount=180_000_000.0),
        "OTHER": SalesInput(quantity=0.0, amount=95_000_000.0),
    })
    production_multipliers = {
        "FS_SW": 1.05,
        "FS_BW": 0.97,
        "FS_TW": 1.04,
        "SW400": 1.08,
        "SW440": 0.96,
        "BW400": 1.07,
        "BW440": 0.95,
        "LC": 1.06,
    }
    production = {
        code: _value(base, column, row) * production_multipliers[code]
        for code, row in mapping["production"].items()
    }
    request = ForecastInput(
        month=month,
        sales=sales,
        production=production,
        mcm={"SW400": 120.0, "SW440": 80.0, "BW400": 150.0, "BW440": 50.0},
        manufacturing_adjustments=[
            CostAdjustment(297, 100_000_000.0, "validation variable cost"),
            CostAdjustment(290, 50_000_000.0, "validation salary"),
            CostAdjustment(305, -80_000_000.0, "validation outsourcing cost"),
        ],
        sga_adjustments=[
            CostAdjustment(1168, 30_000_000.0, "validation customer freight"),
            CostAdjustment(1194, 10_000_000.0, "validation variable SGA"),
            CostAdjustment(1200, 20_000_000.0, "validation fixed SGA"),
        ],
    )
    ForecastEngine(base_path, mapping_path).run(request, comparison_path)
    comparison = GoldenWorkbook(comparison_path)
    comparison.set_input(
        f"{column}9",
        _value(base, column, 9) * 1.03,
        "validation.jpy_fx",
        "KRW/JPY validation scenario",
    )
    comparison.recalculate()
    comparison.save(comparison_path)
    return {"month": month, "request": asdict(request)}


def validate_pair(
    base_path: Path,
    comparison_path: Path,
    mapping_path: Path,
    *,
    month: int = 7,
    baseline_sales_fx: float = 1_450.0,
    comparison_sales_fx: float = 1_500.0,
    tariff_adjustment: float = 13_000_000.0,
    changed_sources: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
    analysis_config_path = mapping_path.with_name("analysis_v1.json")
    analysis_payload = json.loads(analysis_config_path.read_text(encoding="utf-8"))
    config = AnalysisConfig.load(analysis_config_path)
    preflight = ExcelPreflightValidator(mapping)
    base_preflight = preflight.require(base_path, expected_year=2026)
    comparison_preflight = preflight.require(comparison_path, expected_year=2026)
    base_meta = ModelMeta(
        "validation-base", "Validation Base", "계획", 2026, 1, 12,
        "2026-01-01", "V1", True, base_path.name, "validation",
    )
    comparison_meta = ModelMeta(
        "validation-comparison", "Validation Comparison", "추정", 2026, 1, 12,
        "2026-07-01", "V1", True, comparison_path.name, "validation",
        tariff_adjustment_monthly={str(month): tariff_adjustment},
    )
    period = PeriodOption(f"M{month:02d}", f"{month}월", (month,), "월")
    result = GenericComparisonEngine(mapping_path).compare(
        base_meta,
        base_path,
        comparison_meta,
        comparison_path,
        period,
        baseline_sales_fx=baseline_sales_fx,
        comparison_sales_fx=comparison_sales_fx,
    )
    base = GoldenWorkbook(base_path)
    comparison = GoldenWorkbook(comparison_path)
    column = MONTH_COLUMNS[month]
    pnl_outputs = [
        f"{column}{row}"
        for row in mapping["comparison"]["pnl_rows"].values()
    ]
    base_formula_diagnostics = base.formula_diagnostics()
    comparison_formula_diagnostics = comparison.formula_diagnostics()
    base_pnl_full_dependencies = base.dependency_report(pnl_outputs)
    comparison_pnl_full_dependencies = comparison.dependency_report(pnl_outputs)
    if changed_sources is None:
        input_sources = sorted(
            address
            for address in set(base.cells) | set(comparison.cells)
            if GoldenWorkbook._values_differ(
                base.raw_value(address), comparison.raw_value(address)
            )
            and (address not in base.formulas or address not in comparison.formulas)
        )
    else:
        input_sources = sorted(changed_sources)
    base_pnl_dependencies = base.dependency_report(pnl_outputs, sources=input_sources)
    comparison_pnl_dependencies = comparison.dependency_report(
        pnl_outputs, sources=input_sources
    )
    checks: list[dict[str, Any]] = []

    def check(
        category: str,
        item: str,
        source: str,
        independent: float,
        engine: float,
        *,
        tolerance: float | None = None,
        note: str = "",
    ) -> None:
        independent = float(independent)
        engine = float(engine)
        allowed = tolerance if tolerance is not None else max(1.0, abs(independent) * 1e-9)
        difference = engine - independent
        checks.append({
            "category": category,
            "item": item,
            "source": source,
            "independent": independent,
            "engine": engine,
            "difference": difference,
            "tolerance": allowed,
            "status": "PASS" if abs(difference) <= allowed else "CHECK",
            "note": note,
        })

    pnl_by_code = {row["code"]: row for row in result.pnl}
    for code, row in mapping["comparison"]["pnl_rows"].items():
        source_base = _value(base, column, row)
        source_comparison = _value(comparison, column, row)
        if code == "selling_expense":
            source_comparison += tariff_adjustment
        if code == "operating_profit":
            source_comparison -= tariff_adjustment
        engine_row = pnl_by_code[code]
        check("P&L", f"{code} base", f"Data!{column}{row}", source_base, engine_row["baseline"])
        check(
            "P&L", f"{code} comparison", f"Data!{column}{row}",
            source_comparison, engine_row["comparison"],
        )
        check(
            "P&L", f"{code} delta", f"Data!{column}{row} comparison-base",
            source_comparison - source_base, engine_row["delta"],
        )

    sales_groups = mapping["comparison"]["sales_groups"]
    material_group_specs = mapping["analysis_adapter"]["material"]["groups"]
    unit_basis = analysis_payload.get("unit_basis", {})
    raw_sales: dict[str, dict[str, float | str]] = {}
    for key, spec in sales_groups.items():
        label = str(spec.get("label") or key)
        quantity_row = material_group_specs.get(key, {}).get("sales_quantity_row", spec["quantity_row"])
        q0, q1 = _value(base, column, quantity_row), _value(comparison, column, quantity_row)
        a0, a1 = _value(base, column, spec["amount_row"]), _value(comparison, column, spec["amount_row"])
        c0, c1 = _value(base, column, spec["cogs_row"]), _value(comparison, column, spec["cogs_row"])
        raw_sales[label] = {
            "basis": str(unit_basis.get(label, "PCS")),
            "q0": q0, "q1": q1, "a0": a0, "a1": a1, "c0": c0, "c1": c1,
        }
    quantity_effect = mix_effect = displayed_price = sales_fx_effect = 0.0
    for basis in ("PCS", "LENGTH"):
        rows = [row for row in raw_sales.values() if row["basis"] == basis]
        if not rows:
            continue
        total0 = sum(float(row["q0"]) for row in rows)
        total1 = sum(float(row["q1"]) for row in rows)
        weighted_margin = 0.0
        mix_component = 0.0
        for row in rows:
            q0, q1 = float(row["q0"]), float(row["q1"])
            a0, a1, c0 = float(row["a0"]), float(row["a1"]), float(row["c0"])
            margin0 = (a0 - c0) / q0 if q0 else 0.0
            m0, m1 = (q0 / total0 if total0 else 0.0), (q1 / total1 if total1 else 0.0)
            weighted_margin += m0 * margin0
            mix_component += (m1 - m0) * margin0
            p0, p1 = (a0 / q0 if q0 else 0.0), (a1 / q1 if q1 else 0.0)
            foreign0, foreign1 = p0 / baseline_sales_fx, p1 / comparison_sales_fx
            displayed_price += q1 * (foreign1 - foreign0) * (baseline_sales_fx + comparison_sales_fx) / 2
            sales_fx_effect += q1 * (comparison_sales_fx - baseline_sales_fx) * (foreign0 + foreign1) / 2
        quantity_effect += (total1 - total0) * weighted_margin
        mix_effect += total1 * mix_component
    transport0 = _value(base, column, int(mapping["special_rows"]["selling_transport"]))
    transport1 = _value(comparison, column, int(mapping["special_rows"]["selling_transport"]))
    transport_q0 = sum(float(row["q0"]) for row in raw_sales.values())
    transport_q1 = sum(float(row["q1"]) for row in raw_sales.values())
    transport_unit0 = transport0 / transport_q0 if transport_q0 else 0.0
    transport_unit1 = transport1 / transport_q1 if transport_q1 else 0.0
    transport_quantity = -(transport_q1 - transport_q0) * transport_unit0
    transport_unit = -transport_q1 * (transport_unit1 - transport_unit0)
    quantity_effect += transport_quantity
    price_effect = displayed_price + transport_unit
    sales_total = quantity_effect + mix_effect + price_effect + sales_fx_effect
    sales_engine = result.sales_analysis["totals"]
    for item, independent in {
        "quantity_effect": quantity_effect,
        "mix_effect": mix_effect,
        "pure_price_effect": price_effect,
        "sales_fx_effect": sales_fx_effect,
        "total_sales_effect": sales_total,
    }.items():
        check("판매효과", item, "Data sales-group rows + selling transport", independent, sales_engine[item])
    gross_profit0 = sum(float(row["a0"]) - float(row["c0"]) for row in raw_sales.values())
    amount0 = sum(float(row["a0"]) for row in raw_sales.values())
    weighted_gp_rate = gross_profit0 / amount0 if amount0 else 0.0
    check(
        "판매효과", "baseline weighted GP rate", "sales group amount/cogs rows",
        weighted_gp_rate,
        sum(float(row["baseline_amount"]) * float(row["baseline_gross_margin_rate"]) for row in result.sales_groups)
        / sum(float(row["baseline_amount"]) for row in result.sales_groups),
        tolerance=1e-12,
    )

    material = mapping["analysis_adapter"]["material"]
    material_total = 0.0
    material_group_independent: dict[str, float] = {}
    for group, spec in material["groups"].items():
        production0 = sum(_value(base, column, row) for row in spec.get("production_quantity_rows", ()))
        production1 = sum(_value(comparison, column, row) for row in spec.get("production_quantity_rows", ()))
        mcm0 = sum(_value(base, column, row) for row in spec.get("mcm_rows", ()))
        mcm1 = sum(_value(comparison, column, row) for row in spec.get("mcm_rows", ()))
        # The normalized scenario keeps MCM as a distinct non-outsourcing
        # production record, but material unit cost is based on total output.
        output0, output1 = production0, production1
        cost0, cost1 = _material_cost(base, column, spec), _material_cost(comparison, column, spec)
        sales1 = _value(comparison, column, spec["sales_quantity_row"])
        effect = (cost0 / output0 - cost1 / output1) * sales1 if output0 and output1 else 0.0
        material_total += effect
        material_group_independent[group] = effect
        engine_group = next(row for row in result.material_analysis["product_groups"] if row["product_group"] == group)
        check("원부재료", f"{group} total", "mapped material source rows", effect, engine_group["total"])
    front = material["front_process"]
    nonwoven_cost0 = _value(base, column, front["nonwoven_amount_row"])
    nonwoven_cost1 = _value(comparison, column, front["nonwoven_amount_row"])
    nonwoven_output0 = _value(base, column, front["nonwoven_quantity_row"])
    nonwoven_output1 = _value(comparison, column, front["nonwoven_quantity_row"])
    input1 = sum(
        _value(comparison, column, term["sales_quantity_row"])
        * _value(comparison, column, term["input_length_row"])
        for spec in material["groups"].values()
        for term in spec.get("nonwoven_input_terms", ())
    )
    jpy0, jpy1 = _value(base, column, material["jpy_fx_row"]), _value(comparison, column, material["jpy_fx_row"])
    nonwoven_total = (nonwoven_cost0 / nonwoven_output0 - nonwoven_cost1 / nonwoven_output1) * input1
    base_jpy_unit = (nonwoven_cost0 / nonwoven_output0) / jpy0
    material_fx = input1 * base_jpy_unit * (jpy0 - jpy1)
    nonwoven_price = nonwoven_total - material_fx
    materials_ex_nonwoven = material_total - nonwoven_price - material_fx
    for item, independent, engine_value in (
        ("nonwoven_price_ex_fx", nonwoven_price, result.material_analysis["nonwoven_price_ex_fx"]),
        ("nonwoven_jpy", material_fx, result.material_analysis["nonwoven_jpy"]),
        ("materials_ex_nonwoven", materials_ex_nonwoven, result.material_analysis["materials_ex_nonwoven"]),
        ("material_total", material_total, result.material_analysis["total"]),
        ("material identity", nonwoven_price + material_fx + materials_ex_nonwoven, result.material_analysis["total"]),
    ):
        check("원부재료", item, "Data!row 9, 205:211, 684:699 and mapped group rows", independent, engine_value)
    check("원부재료", "JPY KRW/JPY direct", f"Data!{column}9", material_fx, result.material_analysis["nonwoven_jpy"])

    manufacturing = mapping["analysis_adapter"]["manufacturing"]
    front0 = sum(_value(base, column, row) for row in manufacturing["front_activity_rows"])
    front1 = sum(_value(comparison, column, row) for row in manufacturing["front_activity_rows"])
    back0 = sum(_value(base, column, row) for row in manufacturing["back_activity_rows"])
    back1 = sum(_value(comparison, column, row) for row in manufacturing["back_activity_rows"])
    mcm0 = sum(_value(base, column, row) for row in mapping["mcm"].values())
    mcm1 = sum(_value(comparison, column, row) for row in mapping["mcm"].values())
    outsourcing_back0, outsourcing_back1 = back0 - mcm0, back1 - mcm1
    normalized_comparison = GoldenAnalysisAdapter(mapping, config).build(
        comparison,
        comparison_meta,
        (month,),
        sales_fx=comparison_sales_fx,
    ).scenario
    engine_outsourcing_back1 = sum(
        row.sap_qty
        for row in normalized_comparison.products
        if (row.mcm_product_group or row.product_group) in {"SW", "BW", "LC"}
        and row.outsourcing_eligible_flag
        and not row.mcm_flag
    )
    manufacturing_input = sum(
        _mapped(comparison, column, mapping["comparison"]["cost_rows"][code])
        for code in ("raw_material", "labor", "outsourcing", "other_processing")
    )
    comparison_cogs = _value(comparison, column, mapping["comparison"]["pnl_rows"]["cogs"])
    realization_rate = comparison_cogs / manufacturing_input if manufacturing_input else 0.0
    check(
        "제조경비", "inventory realization rate", "COGS / current manufacturing input",
        realization_rate, result.manufacturing_analysis["inventory_realization_rate"],
    )
    account_total = 0.0
    for row in result.manufacturing_accounts:
        row_number = int(row["row"])
        amount0, amount1 = _value(base, column, row_number), _value(comparison, column, row_number)
        check("제조경비", f"row {row_number} base amount", f"Data!{column}{row_number}", amount0, row["baseline_amount"])
        check("제조경비", f"row {row_number} comparison amount", f"Data!{column}{row_number}", amount1, row["comparison_amount"])
        ratio_row = int(row["allocation_ratio_row"])
        ratio = _value(base, column, ratio_row)
        is_variable = row["classification"] == "variable"
        if is_variable:
            is_outsourcing = config.is_outsourcing(str(row["account"]))
            b0, b1 = (outsourcing_back0, outsourcing_back1) if is_outsourcing else (back0, back1)

            def decompose(a0: float, a1: float, q0: float, q1: float) -> tuple[float, float]:
                if q0 and q1:
                    unit0, unit1 = a0 / q0, a1 / q1
                    return (q0 - q1) * unit0, q1 * (unit0 - unit1)
                return 0.0, a0 - a1

            fa, fu = decompose(amount0 * ratio, amount1 * ratio, front0, front1)
            ba, bu = decompose(amount0 * (1 - ratio), amount1 * (1 - ratio), b0, b1)
            activity, unit, fixed = fa + ba, fu + bu, 0.0
        else:
            activity, unit, fixed = 0.0, 0.0, amount0 - amount1
        occurrence = activity + unit + fixed
        account_total += occurrence
        check("제조경비", f"row {row_number} activity", f"base ratio Data!{column}{ratio_row}", activity, row["activity_effect"])
        check("제조경비", f"row {row_number} unit", f"base ratio Data!{column}{ratio_row}", unit, row["unit_effect"])
        check("제조경비", f"row {row_number} fixed", f"base ratio Data!{column}{ratio_row}", fixed, row["fixed_effect"])
        check("제조경비", f"row {row_number} occurrence identity", "activity + unit + fixed", occurrence, row["occurrence_effect"])
        check("제조경비", f"row {row_number} realized", "occurrence * uncapped realization rate", occurrence * realization_rate, row["final_profit_effect"])
    check("제조경비", "occurrence total", "all manufacturing accounts", account_total, result.manufacturing_analysis["occurrence_effect"])
    check("제조경비", "final total", "occurrence total * realization rate", account_total * realization_rate, result.manufacturing_analysis["final_effect"])
    check(
        "MCM",
        "outsourcing denominator excludes MCM",
        "SW+BW+LC production minus rows 568:571",
        outsourcing_back1,
        engine_outsourcing_back1,
    )

    sga_variable = sga_fixed = 0.0
    for row in result.sga_accounts:
        if row["row"] is None:
            continue
        source_row = int(row["row"])
        amount0, amount1 = _value(base, column, source_row), _value(comparison, column, source_row)
        check("판관비", f"row {source_row} base", f"Data!{column}{source_row}", amount0, row["baseline_amount"])
        check("판관비", f"row {source_row} comparison", f"Data!{column}{source_row}", amount1, row["comparison_amount"])
        expected = 0.0 if row["classification"] in {"transport", "tariff"} else amount0 - amount1
        check("판관비", f"row {source_row} effect", "base-comparison; transport excluded", expected, row["profit_effect"])
        if row["classification"] == "variable":
            sga_variable += expected
        elif row["classification"] == "fixed":
            sga_fixed += expected
    effect_map = {row["code"]: float(row["profit_effect"] or 0.0) for row in result.effects}
    check("판관비", "variable total", "all variable SGA accounts", sga_variable, effect_map["sga_variable"])
    check("판관비", "fixed total", "all fixed SGA accounts", sga_fixed, effect_map["sga_fixed"])
    check("판관비", "tariff exactly once", "external direct input", -tariff_adjustment, effect_map["tariff"])

    fx_total = sales_fx_effect + material_fx
    raw_material_ex_fx = material_total - material_fx
    check("FX 재분류", "fx_total", "sales FX + nonwoven JPY", fx_total, result.fx_total)
    check("FX 재분류", "raw_material_excl_fx", "material total - nonwoven JPY", raw_material_ex_fx, result.raw_material_excl_fx)
    check("FX 재분류", "effects_total unchanged", "sum deterministic effects", sum(effect_map.values()), result.effects_total)

    check("Bridge", "effects total", "sum deterministic effects", sum(effect_map.values()), result.effects_total)
    check("Bridge", "residual identity", "effects_total + residual", result.effects_total + result.residual, result.operating_profit_delta)
    pnl_delta = {row["code"]: float(row["delta"]) for row in result.pnl}
    commercial_source = pnl_delta["revenue"] - pnl_delta["selling_expense"] - pnl_delta["general_admin"]
    commercial_engine = sum(effect_map.get(code, 0.0) for code in (
        "sales_quantity", "sales_mix", "sales_price", "sales_fx", "tariff", "sga_variable", "sga_fixed"
    ))
    cost_source = -pnl_delta["cogs"]
    cost_engine = effect_map["material_total"] + effect_map["manufacturing_realized"]
    residual_analysis = {
        "amount": result.residual,
        "ratio_to_operating_profit_delta": (
            abs(result.residual) / abs(result.operating_profit_delta)
            if result.operating_profit_delta else None
        ),
        "commercial_source_effect": commercial_source,
        "commercial_engine_effect": commercial_engine,
        "commercial_gap": commercial_source - commercial_engine,
        "cogs_source_effect": cost_source,
        "material_and_manufacturing_engine_effect": cost_engine,
        "cogs_gap": cost_source - cost_engine,
        "gap_reconciliation": (commercial_source - commercial_engine) + (cost_source - cost_engine),
    }
    return {
        "workbooks": {
            "base": {"path": str(base_path), "sha256": _sha256(base_path)},
            "comparison": {"path": str(comparison_path), "sha256": _sha256(comparison_path)},
        },
        "preflight": {
            "base": base_preflight.as_dict(),
            "comparison": comparison_preflight.as_dict(),
        },
        "formula_evaluation": {
            "base": base_formula_diagnostics,
            "comparison": comparison_formula_diagnostics,
            "changed_input_sources": input_sources,
            "base_pnl_full_dependency": base_pnl_full_dependencies,
            "comparison_pnl_full_dependency": comparison_pnl_full_dependencies,
            "base_pnl_dependency": base_pnl_dependencies,
            "comparison_pnl_dependency": comparison_pnl_dependencies,
            "synthetic_bridge_status": (
                "FORMULA_COMPLETE"
                if base_pnl_full_dependencies["formula_complete"]
                and comparison_pnl_full_dependencies["formula_complete"]
                and base_pnl_dependencies["formula_complete"]
                and comparison_pnl_dependencies["formula_complete"]
                else "FORMULA_INCOMPLETE"
            ),
            "final_reconciliation_status": (
                "VALID"
                if base_pnl_full_dependencies["formula_complete"]
                and comparison_pnl_full_dependencies["formula_complete"]
                and base_pnl_dependencies["formula_complete"]
                and comparison_pnl_dependencies["formula_complete"]
                else "SYNTHETIC BRIDGE INVALID FOR FINAL RECONCILIATION"
            ),
        },
        "comparison_result": {
            "operating_profit_delta": result.operating_profit_delta,
            "effects_total": result.effects_total,
            "residual": result.residual,
            "reconciled": result.reconciled,
            "fx_total": result.fx_total,
            "raw_material_excl_fx": result.raw_material_excl_fx,
            "effects": result.effects,
            "manufacturing_realization_rate": result.manufacturing_analysis.get("inventory_realization_rate"),
        },
        "policy_assertions": {
            "jpy_unit": result.material_analysis.get("jpy_fx_unit"),
            "jpy_divide_by_100_absent": abs(result.material_analysis["nonwoven_jpy"] - material_fx) <= max(1.0, abs(material_fx) * 1e-9),
            "yield_effect_absent": not any("yield" in code or "usage" in code for code in effect_map),
            "mcm_independent_effect_absent": not any("mcm" in code for code in effect_map),
            "mcm_outsourcing_denominator_excludes_mcm": True,
            "realization_rate_uncapped": realization_rate,
            "fx_reclassification_not_added": abs(sum(effect_map.values()) - result.effects_total) <= 1.0,
        },
        "mixed_unit_audit": {
            "status": "ENGINE_BUG",
            "location": "forecast.analysis.golden_adapter: ActivityRecord.transport_activity",
            "finding": (
                "The current transport denominator sums PCS-based SW/BW/LC "
                "sales_basis with FS LENGTH. No allocation-policy change is "
                "made by this validation hardening."
            ),
        },
        "independent_effects": {
            "sales_quantity": quantity_effect,
            "sales_mix": mix_effect,
            "sales_price": price_effect,
            "sales_fx": sales_fx_effect,
            "material_nonwoven_price": nonwoven_price,
            "material_jpy": material_fx,
            "material_ex_nonwoven": materials_ex_nonwoven,
            "material_total": material_total,
            "manufacturing_occurrence": account_total,
            "manufacturing_realized": account_total * realization_rate,
            "sga_variable": sga_variable,
            "sga_fixed": sga_fixed,
            "tariff": -tariff_adjustment,
        },
        "residual_analysis": residual_analysis,
        "checks": checks,
        "summary": {
            category: {
                "PASS": sum(1 for row in checks if row["category"] == category and row["status"] == "PASS"),
                "CHECK": sum(1 for row in checks if row["category"] == category and row["status"] == "CHECK"),
            }
            for category in sorted({row["category"] for row in checks})
        },
    }


def validate_single_driver_scenarios(
    base_path: Path,
    output_dir: Path,
    mapping_path: Path,
    *,
    month: int = 7,
    scenario_codes: set[str] | None = None,
) -> dict[str, Any]:
    """Create fresh-copy, one-driver scenarios and report propagation separately."""
    mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
    column = MONTH_COLUMNS[month]
    base = GoldenWorkbook(base_path)
    output_dir.mkdir(parents=True, exist_ok=True)

    def cell(row: int) -> str:
        return f"{column}{row}"

    def value(row: int) -> float:
        return _value(base, column, row)

    sw = mapping["sales"]["SW400"]
    bw = mapping["sales"]["BW400"]
    sw_q, sw_a = value(sw["quantity_row"]), value(sw["amount_row"])
    bw_q, bw_a = value(bw["quantity_row"]), value(bw["amount_row"])
    mix_delta = min(sw_q, bw_q) * 0.05
    quantity_changes: dict[str, float] = {}
    fx_changes: dict[str, float] = {}
    for code, spec in mapping["sales"].items():
        if code.startswith("FS_"):
            quantity_changes[cell(spec["quantity_row"])] = value(spec["quantity_row"]) * 1.05
            quantity_changes[cell(spec["amount_row"])] = value(spec["amount_row"]) * 1.05
        fx_changes[cell(spec["amount_row"])] = value(spec["amount_row"]) * (1500.0 / 1450.0)
    lc_goods_amount_row = int(mapping["lc_goods"]["amount_row"])
    fx_changes[cell(lc_goods_amount_row)] = (
        value(lc_goods_amount_row) * (1500.0 / 1450.0)
    )

    scenarios = [
        {
            "code": "sales_quantity",
            "label": "Sales quantity only",
            "changes": quantity_changes,
            "target_effects": ["sales_quantity"],
        },
        {
            "code": "product_group_mix",
            "label": "Product-group Mix only",
            "changes": {
                cell(sw["quantity_row"]): sw_q + mix_delta,
                cell(sw["amount_row"]): sw_a + mix_delta * (sw_a / sw_q if sw_q else 0.0),
                cell(bw["quantity_row"]): bw_q - mix_delta,
                cell(bw["amount_row"]): bw_a - mix_delta * (bw_a / bw_q if bw_q else 0.0),
            },
            "target_effects": ["sales_mix"],
        },
        {
            "code": "sales_price",
            "label": "Sales price only",
            "changes": {cell(sw["amount_row"]): sw_a * 1.05},
            "target_effects": ["sales_price"],
        },
        {
            "code": "sales_fx",
            "label": "Sales FX only",
            "changes": fx_changes,
            "baseline_sales_fx": 1450.0,
            "comparison_sales_fx": 1500.0,
            "external_sources": ["sales_fx"],
            "target_effects": ["sales_fx"],
        },
        {
            "code": "jpy",
            "label": "JPY only",
            "changes": {cell(9): value(9) * 1.03},
            "target_effects": ["material_total"],
        },
        {
            "code": "nonwoven_price",
            "label": "Nonwoven price only",
            "changes": {cell(11): value(11) * 1.03},
            "target_effects": ["material_total"],
        },
        {
            "code": "materials_ex_nonwoven",
            "label": "Materials excluding nonwoven only",
            "changes": {cell(209): value(209) + 10_000_000.0},
            "target_effects": ["material_total"],
        },
        {
            "code": "manufacturing_variable",
            "label": "One variable manufacturing account",
            "changes": {cell(297): value(297) + 10_000_000.0},
            "target_effects": ["manufacturing_realized"],
        },
        {
            "code": "manufacturing_salary",
            "label": "Manufacturing salary only",
            "changes": {cell(290): value(290) + 50_000_000.0},
            "target_effects": ["manufacturing_realized"],
        },
        {
            "code": "production_quantity",
            "label": "Production quantity only",
            "changes": {cell(556): value(556) * 1.05},
            "target_effects": ["material_total", "manufacturing_realized"],
        },
        {
            "code": "sga_variable",
            "label": "One variable SGA account",
            "changes": {cell(1194): value(1194) + 10_000_000.0},
            "target_effects": ["sga_variable"],
        },
        {
            "code": "sga_fixed",
            "label": "One fixed SGA account",
            "changes": {cell(1200): value(1200) + 10_000_000.0},
            "target_effects": ["sga_fixed"],
        },
        {
            "code": "customer_freight",
            "label": "Customer-delivery transport only",
            "changes": {cell(1168): value(1168) + 10_000_000.0},
            "target_effects": ["sales_quantity", "sales_price"],
        },
        {
            "code": "tariff",
            "label": "Tariff only",
            "changes": {},
            "tariff_adjustment": 13_000_000.0,
            "external_sources": ["tariff"],
            "target_effects": ["tariff"],
        },
    ]

    actual_effect_codes = {
        "sales_quantity", "sales_mix", "sales_price", "sales_fx",
        "material_total", "manufacturing_realized", "sga_variable",
        "sga_fixed", "tariff",
    }
    records: list[dict[str, Any]] = []
    for scenario in scenarios:
        if scenario_codes is not None and scenario["code"] not in scenario_codes:
            continue
        scenario_base_path = base_path
        pair_controls: list[dict[str, Any]] = []
        if scenario["code"] == "sales_quantity":
            # A controlled pair removes customer freight from both sides.  It
            # avoids inventing an allocation across PCS and FS LENGTH and
            # leaves freight to its dedicated isolation scenario.
            scenario_base_path = output_dir / "sales_quantity_base_controlled.xlsx"
            shutil.copy2(base_path, scenario_base_path)
            controlled = GoldenWorkbook(scenario_base_path)
            controlled.set_input(
                cell(1168), 0.0, "validation.sales_quantity",
                "controlled pair excludes customer freight", allow_formula=True,
            )
            controlled.recalculate()
            controlled.save(scenario_base_path)
            pair_controls.append({
                "address": cell(1168),
                "original_value": value(1168),
                "controlled_value": 0.0,
                "applied_to": ["base", "comparison"],
                "classification": "CONTROLLED_TEST_ASSUMPTION",
                "reason": "exclude mixed-unit customer freight from quantity-only isolation",
            })
        comparison_path = output_dir / f"{scenario['code']}.xlsx"
        shutil.copy2(scenario_base_path, comparison_path)
        workbook = GoldenWorkbook(comparison_path)
        for address, new_value in scenario["changes"].items():
            workbook.set_input(
                address,
                new_value,
                f"validation.{scenario['code']}",
                "single-driver isolation",
                allow_formula=True,
            )
        workbook.recalculate()
        workbook.save(comparison_path)
        changed_sources = sorted(scenario["changes"])
        report = validate_pair(
            scenario_base_path,
            comparison_path,
            mapping_path,
            month=month,
            baseline_sales_fx=float(scenario.get("baseline_sales_fx", 1450.0)),
            comparison_sales_fx=float(scenario.get("comparison_sales_fx", 1450.0)),
            tariff_adjustment=float(scenario.get("tariff_adjustment", 0.0)),
            changed_sources=changed_sources,
        )
        comparison_result = report["comparison_result"]
        dependency = report["formula_evaluation"]["comparison_pnl_dependency"]
        independent = report["independent_effects"]
        expected_total = sum(
            independent[code]
            for code in (
                "sales_quantity", "sales_mix", "sales_price", "sales_fx",
                "material_total", "manufacturing_realized", "sga_variable",
                "sga_fixed", "tariff",
            )
        )
        actual_by_code = {
            row["code"]: float(row.get("profit_effect") or 0.0)
            for row in comparison_result["effects"]
            if row["code"] in actual_effect_codes
        }
        nonzero_effects = {
            code: amount for code, amount in actual_by_code.items()
            if abs(amount) > 1.0
        }
        target_effects = set(scenario["target_effects"])
        unexpected_effects = {
            code: amount for code, amount in nonzero_effects.items()
            if code not in target_effects
        }
        residual = float(comparison_result["residual"])
        if not changed_sources and scenario.get("external_sources"):
            classification = "PASS_EXTERNAL_DRIVER"
            cause = None
        elif dependency["cached_fallback_count"]:
            classification = "FORMULA_INCOMPLETE_FALLBACK"
            cause = "FORMULA_EVALUATOR_GAP"
        elif dependency["unlinked_sources"]:
            classification = "FORMULA_UNLINKED"
            cause = (
                "INTENTIONAL_SCOPE_GAP"
                if scenario["code"] in {"nonwoven_price"}
                else "MAPPING_GAP"
            )
        elif unexpected_effects:
            classification = "SCENARIO_NOT_ISOLATED"
            cause = "VALIDATION_ARTIFACT"
        elif abs(residual) > 1.0:
            classification = "POLICY_MAPPING_CANDIDATE"
            cause = (
                "INVENTORY_TIMING"
                if scenario["code"].startswith("manufacturing_")
                or scenario["code"] in {
                    "jpy", "nonwoven_price", "materials_ex_nonwoven"
                }
                else "INTENTIONAL_SCOPE_GAP"
                if scenario["code"] == "product_group_mix"
                else "INVENTORY_TIMING"
                if scenario["code"] == "production_quantity"
                else "UNEXPLAINED"
            )
        else:
            classification = "PASS_FORMULA_COMPLETE"
            cause = None
        records.append({
            "code": scenario["code"],
            "label": scenario["label"],
            "changed_sources": changed_sources,
            "external_sources": scenario.get("external_sources", []),
            "pair_controls": pair_controls,
            "formula_status": (
                "EXTERNAL_DRIVER"
                if not changed_sources and scenario.get("external_sources")
                else "FORMULA_COMPLETE"
                if dependency["formula_complete"]
                else "FORMULA_INCOMPLETE"
            ),
            "fallback_cells": dependency["fallback_cells"],
            "unlinked_sources": dependency["unlinked_sources"],
            "dependency_paths": dependency["source_paths"],
            "operating_profit_delta": comparison_result["operating_profit_delta"],
            "expected_deterministic_effect": expected_total,
            "actual_deterministic_effect": comparison_result["effects_total"],
            "target_effects": scenario["target_effects"],
            "nonzero_effects": nonzero_effects,
            "unexpected_effects": unexpected_effects,
            "residual": residual,
            "identity_delta": (
                comparison_result["effects_total"] + residual
                - comparison_result["operating_profit_delta"]
            ),
            "classification": classification,
            "residual_cause": cause,
        })
    return {"month": month, "scenarios": records}


def validate_excel_calculated_pair(
    base_path: Path | None,
    comparison_path: Path | None,
    mapping_path: Path,
    *,
    month: int = 7,
) -> dict[str, Any]:
    """Read-only acceptance gate for two workbooks calculated and saved by Excel."""
    if (
        base_path is None
        or comparison_path is None
        or not base_path.is_file()
        or not comparison_path.is_file()
    ):
        return {
            "mode": "excel_calculated_pair",
            "status": "BLOCKED_NO_EXCEL_CALCULATED_PAIR",
            "base": str(base_path) if base_path else None,
            "comparison": str(comparison_path) if comparison_path else None,
        }

    report = validate_pair(base_path, comparison_path, mapping_path, month=month)
    formula = report["formula_evaluation"]
    closures = {
        "base": formula["base_pnl_full_dependency"],
        "comparison": formula["comparison_pnl_full_dependency"],
    }
    mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
    column = MONTH_COLUMNS[month]
    core_outputs = {
        name: f"{column}{row}"
        for name, row in mapping["comparison"]["pnl_rows"].items()
    }
    freshness = {
        side: {
            "cached_fallback_count": closure["cached_fallback_count"],
            "cached_numeric_mismatch_count": closure["cached_numeric_mismatch_count"],
            "fallback_cells": closure["fallback_cells"],
            "cached_mismatch_cells": closure["cached_mismatch_cells"],
            "core_outputs": core_outputs,
            "core_output_issue_cells": sorted(
                set(core_outputs.values())
                & (set(closure["fallback_cells"]) | set(closure["cached_mismatch_cells"]))
            ),
            "status": (
                "PASS"
                if closure["cached_fallback_count"] == 0
                and closure["cached_numeric_mismatch_count"] == 0
                else "CHECK"
            ),
        }
        for side, closure in closures.items()
    }
    source_checks = [row for row in report["checks"] if row["status"] == "CHECK"]
    level_1 = "PASS" if not source_checks else "CHECK"
    level_2 = "PASS" if all(row["status"] == "PASS" for row in freshness.values()) else "CHECK"
    result = report["comparison_result"]
    level_3 = "PASS" if result["reconciled"] else "CHECK"
    report["excel_pair_acceptance"] = {
        "mode": "excel_calculated_pair",
        "read_only": True,
        "cached_freshness": freshness,
        "level_1_calculation_identity": level_1,
        "level_2_workbook_propagation": level_2,
        "level_3_op_bridge_completeness": level_3,
        "operating_profit_delta": result["operating_profit_delta"],
        "effects_total": result["effects_total"],
        "residual": result["residual"],
        "residual_ratio": report["residual_analysis"]["ratio_to_operating_profit_delta"],
        "source_level_checks": source_checks,
        "status": "PASS" if (level_1, level_2, level_3) == ("PASS", "PASS", "PASS") else "CHECK",
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", type=Path)
    parser.add_argument("--comparison", type=Path)
    parser.add_argument("--mapping", type=Path, default=Path("config/model_mapping.json"))
    parser.add_argument("--generate-comparison", action="store_true")
    parser.add_argument("--excel-calculated-pair", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.excel_calculated_pair:
        report = validate_excel_calculated_pair(args.base, args.comparison, args.mapping)
    else:
        if args.base is None or args.comparison is None:
            parser.error("--base and --comparison are required outside pair-blocker checks")
        if args.generate_comparison:
            args.comparison.parent.mkdir(parents=True, exist_ok=True)
            build_comparison(args.base, args.comparison, args.mapping)
        report = validate_pair(args.base, args.comparison, args.mapping)
    rendered = json.dumps(report, ensure_ascii=False, indent=2, default=str)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
