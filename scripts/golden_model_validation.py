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
        "validation-base", "Validation Base", "ê³„íš", 2026, 1, 12,
        "2026-01-01", "V1", True, base_path.name, "validation",
    )
    comparison_meta = ModelMeta(
        "validation-comparison", "Validation Comparison", "ì¶”ì •", 2026, 1, 12,
        "2026-07-01", "V1", True, comparison_path.name, "validation",
        tariff_adjustment_monthly={str(month): tariff_adjustment},
    )
    period = PeriodOption(f"M{month:02d}", f"{month}ì›”", (month,), "ì›”")
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
        check("íŒë§¤íš¨ê³¼", item, "Data sales-group rows + selling transport", independent, sales_engine[item])
    gross_profit0 = sum(float(row["a0"]) - float(row["c0"]) for row in raw_sales.values())
    amount0 = sum(float(row["a0"]) for row in raw_sales.values())
    weighted_gp_rate = gross_profit0 / amount0 if amount0 else 0.0
    check(
        "íŒë§¤íš¨ê³¼", "baseline weighted GP rate", "sales group amount/cogs rows",
        weighted_gp_rate,
        sum(float(row["baseline_amount"]) * float(row["baseline_gross_margin_rate"]) for row in result.sales_groups)
        / sum(float(row["baseline_amount"]) for row in result.sales_groups),
        tolerance=1e-12,
    )

    material = mapping["analysis_adapter"]["material"]
    material_total = 0.0
    material_group_independent: dict[str, float] = {}
    for group, spec in material["groups"].items():
        production0 = sum(_value(base, column,çnw¶‰žËkºwµçA™á}¡…¹•Ìè‘¥ÑmÍÑÈ°™±½…Ñt€ôíô(€€€™½È½‘”°ÍÁ•Œ¥¸µ…ÁÁ¥¹l‰Í…±•Ì‰t¹¥Ñ•µÌ ¤è(€€€€€€€¥˜½‘”¹ÍÑ…ÉÑÍÝ¥Ñ  ‰M|ˆ¤è(€€€€€€€€€€€ÅÕ…¹Ñ¥Ñå}¡…¹•Ím•±°¡ÍÁ•l‰ÅÕ…¹Ñ¥Ñå}É½Ü‰t¥t€ôÙ…±Õ”¡ÍÁ•l‰ÅÕ…¹Ñ¥Ñå}É½Ü‰t¤€¨€Ä¸ÀÔ(€€€€€€€€€€€ÅÕ…¹Ñ¥Ñå}¡…¹•Ím•±°¡ÍÁ•l‰…µ½Õ¹Ñ}É½Ü‰t¥t€ôÙ…±Õ”¡ÍÁ•l‰…µ½Õ¹Ñ}É½Ü‰t¤€¨€Ä¸ÀÔ(€€€€€€€™á}¡…¹•Ím•±°¡ÍÁ•l‰…µ½Õ¹Ñ}É½Ü‰t¥t€ôÙ…±Õ”¡ÍÁ•l‰…µ½Õ¹Ñ}É½Ü‰t¤€¨€ ÄÔÀÀ¸À€¼€ÄÐÔÀ¸À¤(€€€±}½½‘Í}…µ½Õ¹Ñ}É½Ü€ô¥¹Ð¡µ…ÁÁ¥¹l‰±}½½‘Ì‰ul‰…µ½Õ¹Ñ}É½Ü‰t¤(€€€™á}¡…¹•Ím•±°¡±}½½‘Í}…µ½Õ¹Ñ}É½Ü¥t€ô€ (€€€€€€€Ù…±Õ”¡±}½½‘Í}…µ½Õ¹Ñ}É½Ü¤€¨€ ÄÔÀÀ¸À€¼€ÄÐÔÀ¸À¤(€€€€¤((€€€Í•¹…É¥½Ì€ôl(€€€€€€€ì(€€€€€€€€€€€€‰½‘”ˆè€‰Í…±•Í}ÅÕ…¹Ñ¥Ñäˆ°(€€€€€€€€€€€€‰±…‰•°ˆè€‰M…±•ÌÅÕ…¹Ñ¥Ñä½¹±äˆ°(€€€€€€€€€€€€‰¡…¹•ÌˆèÅÕ…¹Ñ¥Ñå}¡…¹•Ì°(€€€€€€€€€€€€‰Ñ…É•Ñ}•™™•ÑÌˆèl‰Í…±•Í}ÅÕ…¹Ñ¥Ñä‰t°(€€€€€€€ô°(€€€€€€€ì(€€€€€€€€€€€€‰½‘”ˆè€‰ÁÉ½‘ÕÑ}É½ÕÁ}µ¥àˆ°(€€€€€€€€€€€€‰±…‰•°ˆè€‰AÉ½‘ÕÐµÉ½ÕÀ5¥à½¹±äˆ°(€€€€€€€€€€€€‰¡…¹•Ìˆèì(€€€€€€€€€€€€€€€•±°¡ÍÝl‰ÅÕ…¹Ñ¥Ñå}É½Ü‰t¤èÍÝ}Ä€¬µ¥á}‘•±Ñ„°(€€€€€€€€€€€€€€€•±°¡ÍÝl‰…µ½Õ¹Ñ}É½Ü‰t¤èÍÝ}„€¬µ¥á}‘•±Ñ„€¨€¡ÍÝ}„€¼ÍÝ}Ä¥˜ÍÝ}Ä•±Í”€À¸À¤°(€€€€€€€€€€€€€€€•±°¡‰Ýl‰ÅÕ…¹Ñ¥Ñå}É½Ü‰t¤è‰Ý}Ä€´µ¥á}‘•±Ñ„°(€€€€€€€€€€€€€€€•±°¡‰Ýl‰…µ½Õ¹Ñ}É½Ü‰t¤è‰Ý}„€´µ¥á}‘•±Ñ„€¨€¡‰Ý}„€¼‰Ý}Ä¥˜‰Ý}Ä•±Í”€À¸À¤°(€€€€€€€€€€€ô°(€€€€€€€€€€€€‰Ñ…É•Ñ}•™™•ÑÌˆèl‰Í…±•Í}µ¥à‰t°(€€€€€€€ô°(€€€€€€€ì(€€€€€€€€€€€€‰½‘”ˆè€‰Í…±•Í}ÁÉ¥”ˆ°(€€€€€€€€€€€€‰±…‰•°ˆè€‰M…±•ÌÁÉ¥”½¹±äˆ°(€€€€€€€€€€€€‰¡…¹•Ìˆèí•±°¡ÍÝl‰…µ½Õ¹Ñ}É½Ü‰t¤èÍÝ}„€¨€Ä¸ÀÕô°(€€€€€€€€€€€€‰Ñ…É•Ñ}•™™•ÑÌˆèl‰Í…±•Í}ÁÉ¥”‰t°(€€€€€€€ô°(€€€€€€€ì(€€€€€€€€€€€€‰½‘”ˆè€‰Í…±•Í}™àˆ°(€€€€€€€€€€€€‰±…‰•°ˆè€‰M…±•Ì`½¹±äˆ°(€€€€€€€€€€€€‰¡…¹•Ìˆè™á}¡…¹•Ì°(€€€€€€€€€€€€‰‰…Í•±¥¹•}Í…±•Í}™àˆè€ÄÐÔÀ¸À°(€€€€€€€€€€€€‰½µÁ…É¥Í½¹}Í…±•Í}™àˆè€ÄÔÀÀ¸À°(€€€€€€€€€€€€‰•áÑ•É¹…±}Í½ÕÉ•Ìˆèl‰Í…±•Í}™à‰t°(€€€€€€€€€€€€‰Ñ…É•Ñ}•™™•ÑÌˆèl‰Í…±•Í}™à‰t°(€€€€€€€ô°(€€€€€€€ì(€€€€€€€€€€€€‰½‘”ˆè€‰©Áäˆ°(€€€€€€€€€€€€‰±…‰•°ˆè€‰)Ad½¹±äˆ°(€€€€€€€€€€€€‰¡…¹•Ìˆèí•±° ä¤èÙ…±Õ” ä¤€¨€Ä¸ÀÍô°(€€€€€€€€€€€€‰Ñ…É•Ñ}•™™•ÑÌˆèl‰µ…Ñ•É¥…±}Ñ½Ñ…°‰t°(€€€€€€€ô°(€€€€€€€ì(€€€€€€€€€€€€‰½‘”ˆè€‰¹½¹Ý½Ù•¹}ÁÉ¥”ˆ°(€€€€€€€€€€€€‰±…‰•°ˆè€‰9½¹Ý½Ù•¸ÁÉ¥”½¹±äˆ°(€€€€€€€€€€€€‰¡…¹•Ìˆèí•±° ÄÄ¤èÙ…±Õ” ÄÄ¤€¨€Ä¸ÀÍô°(€€€€€€€€€€€€‰Ñ…É•Ñ}•™™•ÑÌˆèl‰µ…Ñ•É¥…±}Ñ½Ñ…°‰t°(€€€€€€€ô°(€€€€€€€ì(€€€€€€€€€€€€‰½‘”ˆè€‰µ…Ñ•É¥…±Í}•á}¹½¹Ý½Ù•¸ˆ°(€€€€€€€€€€€€‰±…‰•°ˆè€‰5…Ñ•É¥…±Ì•á±Õ‘¥¹œ¹½¹Ý½Ù•¸½¹±äˆ°(€€€€€€€€€€€€‰¡…¹•Ìˆèí•±° ÈÀä¤èÙ…±Õ” ÈÀä¤€¬€ÄÁ|ÀÀÁ|ÀÀÀ¸Áô°(€€€€€€€€€€€€‰Ñ…É•Ñ}•™™•ÑÌˆèl‰µ…Ñ•É¥…±}Ñ½Ñ…°‰t°(€€€€€€€ô°(€€€€€€€ì(€€€€€€€€€€€€‰½‘”ˆè€‰µ…¹Õ™…ÑÕÉ¥¹}Ù…É¥…‰±”ˆ°(€€€€€€€€€€€€‰±…‰•°ˆè€‰=¹”Ù…É¥…‰±”µ…¹Õ™…ÑÕÉ¥¹œ…½Õ¹Ðˆ°(€€€€€€€€€€€€‰¡…¹•Ìˆèí•±° ÈäÜ¤èÙ…±Õ” ÈäÜ¤€¬€ÄÁ|ÀÀÁ|ÀÀÀ¸Áô°(€€€€€€€€€€€€‰Ñ…É•Ñ}•™™•ÑÌˆèl‰µ…¹Õ™…ÑÕÉ¥¹}É•…±¥é•‰t°(€€€€€€€ô°(€€€€€€€ì(€€€€€€€€€€€€‰½‘”ˆè€‰µ…¹Õ™…ÑÕÉ¥¹}Í…±…Éäˆ°(€€€€€€€€€€€€‰±…‰•°ˆè€‰5…¹Õ™…ÑÕÉ¥¹œÍ…±…Éä½¹±äˆ°(€€€€€€€€€€€€‰¡…¹•Ìˆèí•±° ÈäÀ¤èÙ…±Õ” ÈäÀ¤€¬€ÔÁ|ÀÀÁ|ÀÀÀ¸Áô°(€€€€€€€€€€€€‰Ñ…É•Ñ}•™™•ÑÌˆèl‰µ…¹Õ™…ÑÕÉ¥¹}É•…±¥é•‰t°(€€€€€€€ô°(€€€€€€€ì(€€€€€€€€€€€€‰½‘”ˆè€‰ÁÉ½‘ÕÑ¥½¹}ÅÕ…¹Ñ¥Ñäˆ°(€€€€€€€€€€€€‰±…‰•°ˆè€‰AÉ½‘ÕÑ¥½¸ÅÕ…¹Ñ¥Ñä½¹±äˆ°(€€€€€€€€€€€€‰¡…¹•Ìˆèí•±° ÔÔØ¤èÙ…±Õ” ÔÔØ¤€¨€Ä¸ÀÕô°(€€€€€€€€€€€€‰Ñ…É•Ñ}•™™•ÑÌˆèl‰µ…Ñ•É¥…±}Ñ½Ñ…°ˆ°€‰µ…¹Õ™…ÑÕÉ¥¹}É•…±¥é•‰t°(€€€€€€€ô°(€€€€€€€ì(€€€€€€€€€€€€‰½‘”ˆè€‰Í…}Ù…É¥…‰±”ˆ°(€€€€€€€€€€€€‰±…‰•°ˆè€‰=¹”Ù…É¥…‰±”M…½Õ¹Ðˆ°(€€€€€€€€€€€€‰¡…¹•Ìˆèí•±° ÄÄäÐ¤èÙ…±Õ” ÄÄäÐ¤€¬€ÄÁ|ÀÀÁ|ÀÀÀ¸Áô°(€€€€€€€€€€€€‰Ñ…É•Ñ}•™™•ÑÌˆèl‰Í…}Ù…É¥…‰±”‰t°(€€€€€€€ô°(€€€€€€€ì(€€€€€€€€€€€€‰½‘”ˆè€‰Í…}™¥á•ˆ°(€€€€€€€€€€€€‰±…‰•°ˆè€‰=¹”™¥á•M…½Õ¹Ðˆ°(€€€€€€€€€€€€‰¡…¹•Ìˆèí•±° ÄÈÀÀ¤èÙ…±Õ” ÄÈÀÀ¤€¬€ÄÁ|ÀÀÁ|ÀÀÀ¸Áô°(€€€€€€€€€€€€‰Ñ…É•Ñ}•™™•ÑÌˆèl‰Í…}™¥á•‰t°(€€€€€€€ô°(€€€€€€€ì(€€€€€€€€€€€€‰½‘”ˆè€‰ÕÍÑ½µ•É}™É•¥¡Ðˆ°(€€€€€€€€€€€€‰±…‰•°ˆè€‰ÕÍÑ½µ•Èµ‘•±¥Ù•ÉäÑÉ…¹ÍÁ½ÉÐ½¹±äˆ°(€€€€€€€€€€€€‰¡…¹•Ìˆèí•±° ÄÄØà¤èÙ…±Õ” ÄÄØà¤€¬€ÄÁ|ÀÀÁ|ÀÀÀ¸Áô°(€€€€€€€€€€€€‰Ñ…É•Ñ}•™™•ÑÌˆèl‰Í…±•Í}ÅÕ…¹Ñ¥Ñäˆ°€‰Í…±•Í}ÁÉ¥”‰t°(€€€€€€€ô°(€€€€€€€ì(€€€€€€€€€€€€‰½‘”ˆè€‰Ñ…É¥™˜ˆ°(€€€€€€€€€€€€‰±…‰•°ˆè€‰Q…É¥™˜½¹±äˆ°(€€€€€€€€€€€€‰¡…¹•Ìˆèíô°(€€€€€€€€€€€€‰Ñ…É¥™™}…‘©ÕÍÑµ•¹Ðˆè€ÄÍ|ÀÀÁ|ÀÀÀ¸À°(€€€€€€€€€€€€‰•áÑ•É¹…±}Í½ÕÉ•Ìˆèl‰Ñ…É¥™˜‰t°(€€€€€€€€€€€€‰Ñ…É•Ñ}•™™•ÑÌˆèl‰Ñ…É¥™˜‰t°(€€€€€€€ô°(€€€t((€€€…ÑÕ…±}•™™•Ñ}½‘•Ì€ôì(€€€€€€€€‰Í…±•Í}ÅÕ…¹Ñ¥Ñäˆ°€‰Í…±•Í}µ¥àˆ°€‰Í…±•Í}ÁÉ¥”ˆ°€‰Í…±•Í}™àˆ°(€€€€€€€€‰µ…Ñ•É¥…±}Ñ½Ñ…°ˆ°€‰µ…¹Õ™…ÑÕÉ¥¹}É•…±¥é•ˆ°€‰Í…}Ù…É¥…‰±”ˆ°(€€€€€€€€‰Í…}™¥á•ˆ°€‰Ñ…É¥™˜ˆ°(€€€ô(€€€É•½É‘Ìè±¥ÍÑm‘¥ÑmÍÑÈ°¹åut€ômt(€€€™½ÈÍ•¹…É¥¼¥¸Í•¹…É¥½Ìè(€€€€€€€¥˜Í•¹…É¥½}½‘•Ì¥Ì¹½Ð9½¹”…¹Í•¹…É¥½l‰½‘”‰t¹½Ð¥¸Í•¹…É¥½}½‘•Ìè(€€€€€€€€€€€½¹Ñ¥¹Õ”(€€€€€€€Í•¹…É¥½}‰…Í•}Á…Ñ €ô‰…Í•}Á…Ñ (€€€€€€€Á…¥É}½¹ÑÉ½±Ìè±¥ÍÑm‘¥ÑmÍÑÈ°¹åut€ômt(€€€€€€€¥˜Í•¹…É¥½l‰½‘”‰t€ôô€‰Í…±•Í}ÅÕ…¹Ñ¥Ñäˆè(€€€€€€€€€€€€Œ½¹ÑÉ½±±•Á…¥ÈÉ•µ½Ù•ÌÕÍÑ½µ•È™É•¥¡Ð™É½´‰½Ñ Í¥‘•Ì¸€%Ð(€€€€€€€€€€€€Œ…Ù½¥‘Ì¥¹Ù•¹Ñ¥¹œ…¸…±±½…Ñ¥½¸…É½ÍÌAL…¹L19Q …¹(€€€€€€€€€€€€Œ±•…Ù•Ì™É•¥¡ÐÑ¼¥ÑÌ‘•‘¥…Ñ•¥Í½±…Ñ¥½¸Í•¹…É¥¼¸(€€€€€€€€€€€Í•¹…É¥½}‰…Í•}Á…Ñ €ô½ÕÑÁÕÑ}‘¥È€¼€‰Í…±•Í}ÅÕ…¹Ñ¥Ñå}‰…Í•}½¹ÑÉ½±±•¹á±Íàˆ(€€€€€€€€€€€Í¡ÕÑ¥°¹½ÁäÈ¡‰…Í•}Á…Ñ °Í•¹…É¥½}‰…Í•}Á…Ñ ¤(€€€€€€€€€€€½¹ÑÉ½±±•€ô½±‘•¹]½É­‰½½¬¡Í•¹…É¥½}‰…Í•}Á…Ñ ¤(€€€€€€€€€€€½¹ÑÉ½±±•¹Í•Ñ}¥¹ÁÕÐ (€€€€€€€€€€€€€€€•±° ÄÄØà¤°€À¸À°€‰Ù…±¥‘…Ñ¥½¸¹Í…±•Í}ÅÕ…¹Ñ¥Ñäˆ°(€€€€€€€€€€€€€€€€‰½¹ÑÉ½±±•Á…¥È•á±Õ‘•ÌÕÍÑ½µ•È™É•¥¡Ðˆ°…±±½Ý}™½ÉµÕ±„õQÉÕ”°(€€€€€€€€€€€€¤(€€€€€€€€€€€½¹ÑÉ½±±•¹É•…±Õ±…Ñ” ¤(€€€€€€€€€€€½¹ÑÉ½±±•¹Í…Ù”¡Í•¹…É¥½}‰…Í•}Á…Ñ ¤(€€€€€€€€€€€Á…¥É}½¹ÑÉ½±Ì¹…ÁÁ•¹¡ì(€€€€€€€€€€€€€€€€‰…‘‘É•ÍÌˆè•±° ÄÄØà¤°(€€€€€€€€€€€€€€€€‰½É¥¥¹…±}Ù…±Õ”ˆèÙ…±Õ” ÄÄØà¤°(€€€€€€€€€€€€€€€€‰½¹ÑÉ½±±•‘}Ù…±Õ”ˆè€À¸À°(€€€€€€€€€€€€€€€€‰…ÁÁ±¥•‘}Ñ¼ˆèl‰‰…Í”ˆ°€‰½µÁ…É¥Í½¸‰t°(€€€€€€€€€€€€€€€€‰±…ÍÍ¥™¥…Ñ¥½¸ˆè€‰=9QI=11}QMQ}MMU5AQ%=8ˆ°(€€€€€€€€€€€€€€€€‰É•…Í½¸ˆè€‰•á±Õ‘”µ¥á•µÕ¹¥ÐÕÍÑ½µ•È™É•¥¡Ð™É½´ÅÕ…¹Ñ¥Ñäµ½¹±ä¥Í½±…Ñ¥½¸ˆ°(€€€€€€€€€€€ô¤(€€€€€€€½µÁ…É¥Í½¹}Á…Ñ €ô½ÕÑÁÕÑ}‘¥È€¼˜‰íÍ•¹…É¥½l½‘”uô¹á±Íàˆ(€€€€€€€Í¡ÕÑ¥°¹½ÁäÈ¡Í•¹…É¥½}‰…Í•}Á…Ñ °½µÁ…É¥Í½¹}Á…Ñ ¤(€€€€€€€Ý½É­‰½½¬€ô½±‘•¹]½É­‰½½¬¡½µÁ…É¥Í½¹}Á…Ñ ¤(€€€€€€€™½È…‘‘É•ÍÌ°¹•Ý}Ù…±Õ”¥¸Í•¹…É¥½l‰¡…¹•Ì‰t¹¥Ñ•µÌ ¤è(€€€€€€€€€€€Ý½É­‰½½¬¹Í•Ñ}¥¹ÁÕÐ (€€€€€€€€€€€€€€€…‘‘É•ÍÌ°(€€€€€€€€€€€€€€€¹•Ý}Ù…±Õ”°(€€€€€€€€€€€€€€€˜‰Ù…±¥‘…Ñ¥½¸¹íÍ•¹…É¥½l½‘”uôˆ°(€€€€€€€€€€€€€€€€‰Í¥¹±”µ‘É¥Ù•È¥Í½±…Ñ¥½¸ˆ°(€€€€€€€€€€€€€€€…±±½Ý}™½ÉµÕ±„õQÉÕ”°(€€€€€€€€€€€€¤(€€€€€€€Ý½É­‰½½¬¹É•…±Õ±…Ñ” ¤(€€€€€€€Ý½É­‰½½¬¹Í…Ù”¡½µÁ…É¥Í½¹}Á…Ñ ¤(€€€€€€€¡…¹•‘}Í½ÕÉ•Ì€ôÍ½ÉÑ•¡Í•¹…É¥½l‰¡…¹•Ì‰t¤(€€€€€€€É•Á½ÉÐ€ôÙ…±¥‘…Ñ•}Á…¥È (€€€€€€€€€€€Í•¹…É¥½}‰…Í•}Á…Ñ °(€€€€€€€€€€€½µÁ…É¥Í½¹}Á…Ñ °(€€€€€€€€€€€µ…ÁÁ¥¹}Á…Ñ °(€€€€€€€€€€€µ½¹Ñ õµ½¹Ñ °(€€€€€€€€€€€‰…Í•±¥¹•}Í…±•Í}™àõ™±½…Ð¡Í•¹…É¥¼¹•Ð ‰‰…Í•±¥¹•}Í…±•Í}™àˆ°€ÄÐÔÀ¸À¤¤°(€€€€€€€€€€€½µÁ…É¥Í½¹}Í…±•Í}™àõ™±½…Ð¡Í•¹…É¥¼¹•Ð ‰½µÁ…É¥Í½¹}Í…±•Í}™àˆ°€ÄÐÔÀ¸À¤¤°(€€€€€€€€€€€Ñ…É¥™™}…‘©ÕÍÑµ•¹Ðõ™±½…Ð¡Í•¹…É¥¼¹•Ð ‰Ñ…É¥™™}…‘©ÕÍÑµ•¹Ðˆ°€À¸À¤¤°(€€€€€€€€€€€¡…¹•‘}Í½ÕÉ•Ìõ¡…¹•‘}Í½ÕÉ•Ì°(€€€€€€€€¤(€€€€€€€½µÁ…É¥Í½¹}É•ÍÕ±Ð€ôÉ•Á½ÉÑl‰½µÁ…É¥Í½¹}É•ÍÕ±Ð‰t(€€€€€€€‘•Á•¹‘•¹ä€ôÉ•Á½ÉÑl‰™½ÉµÕ±…}•Ù…±Õ…Ñ¥½¸‰ul‰½µÁ…É¥Í½¹}Á¹±}‘•Á•¹‘•¹ä‰t(€€€€€€€¥¹‘•Á•¹‘•¹Ð€ôÉ•Á½ÉÑl‰¥¹‘•Á•¹‘•¹Ñ}•™™•ÑÌ‰t(€€€€€€€•áÁ•Ñ•‘}Ñ½Ñ…°€ôÍÕ´ (€€€€€€€€€€€¥¹‘•Á•¹‘•¹Ñm½‘•t(€€€€€€€€€€€™½È½‘”¥¸€ (€€€€€€€€€€€€€€€€‰Í…±•Í}ÅÕ…¹Ñ¥Ñäˆ°€‰Í…±•Í}µ¥àˆ°€‰Í…±•Í}ÁÉ¥”ˆ°€‰Í…±•Í}™àˆ°(€€€€€€€€€€€€€€€€‰µ…Ñ•É¥…±}Ñ½Ñ…°ˆ°€‰µ…¹Õ™…ÑÕÉ¥¹}É•…±¥é•ˆ°€‰Í…}Ù…É¥…‰±”ˆ°(€€€€€€€€€€€€€€€€‰Í…}™¥á•ˆ°€‰Ñ…É¥™˜ˆ°(€€€€€€€€€€€€¤(€€€€€€€€¤(€€€€€€€…ÑÕ…±}‰å}½‘”€ôì(€€€€€€€€€€€É½Ýl‰½‘”‰tè™±½…Ð¡É½Ü¹•Ð ‰ÁÉ½™¥Ñ}•™™•Ðˆ¤½È€À¸À¤(€€€€€€€€€€€™½ÈÉ½Ü¥¸½µÁ…É¥Í½¹}É•ÍÕ±Ñl‰•™™•ÑÌ‰t(€€€€€€€€€€€¥˜É½Ýl‰½‘”‰t¥¸…ÑÕ…±}•™™•Ñ}½‘•Ì(€€€€€€€ô(€€€€€€€¹½¹é•É½}•™™•ÑÌ€ôì(€€€€€€€€€€€½‘”è…µ½Õ¹Ð™½È½‘”°…µ½Õ¹Ð¥¸…ÑÕ…±}‰å}½‘”¹¥Ñ•µÌ ¤(€€€€€€€€€€€¥˜…‰Ì¡…µ½Õ¹Ð¤€ø€Ä¸À(€€€€€€€ô(€€€€€€€Ñ…É•Ñ}•™™•ÑÌ€ôÍ•Ð¡Í•¹…É¥½l‰Ñ…É•Ñ}•™™•ÑÌ‰t¤(€€€€€€€Õ¹•áÁ•Ñ•‘}•™™•ÑÌ€ôì(€€€€€€€€€€€½‘”è…µ½Õ¹Ð™½È½‘”°…µ½Õ¹Ð¥¸¹½¹é•É½}•™™•ÑÌ¹¥Ñ•µÌ ¤(€€€€€€€€€€€¥˜½‘”¹½Ð¥¸Ñ…É•Ñ}•™™•ÑÌ(€€€€€€€ô(€€€€€€€É•Í¥‘Õ…°€ô™±½…Ð¡½µÁ…É¥Í½¹}É•ÍÕ±Ñl‰É•Í¥‘Õ…°‰t¤(€€€€€€€¥˜¹½Ð¡…¹•‘}Í½ÕÉ•Ì…¹Í•¹…É¥¼¹•Ð ‰•áÑ•É¹…±}Í½ÕÉ•Ìˆ¤è(€€€€€€€€€€€±…ÍÍ¥™¥…Ñ¥½¸€ô€‰AMM}aQI91}I%YHˆ(€€€€€€€€€€€…ÕÍ”€ô9½¹”(€€€€€€€•±¥˜‘•Á•¹‘•¹ål‰…¡•‘}™…±±‰…­}½Õ¹Ð‰tè(€€€€€€€€€€€±…ÍÍ¥™¥…Ñ¥½¸€ô€‰=I5U1}%9=5A1Q}11	,ˆ(€€€€€€€€€€€…ÕÍ”€ô€‰=I5U1}Y1UQ=I}@ˆ(€€€€€€€•±¥˜‘•Á•¹‘•¹ål‰Õ¹±¥¹­•‘}Í½ÕÉ•Ì‰tè(€€€€€€€€€€€±…ÍÍ¥™¥…Ñ¥½¸€ô€‰=I5U1}U91%9-ˆ(€€€€€€€€€€€…ÕÍ”€ô€ (€€€€€€€€€€€€€€€€‰%9Q9Q%=91}M=A}@ˆ(€€€€€€€€€€€€€€€¥˜Í•¹…É¥½l‰½‘”‰t¥¸ì‰¹½¹Ý½Ù•¹}ÁÉ¥”‰ô(€€€€€€€€€€€€€€€•±Í”€‰5AA%9}@ˆ(€€€€€€€€€€€€¤(€€€€€€€•±¥˜Õ¹•áÁ•Ñ•‘}•™™•ÑÌè(€€€€€€€€€€€±…ÍÍ¥™¥…Ñ¥½¸€ô€‰M9I%=}9=Q}%M=1Qˆ(€€€€€€€€€€€…ÕÍ”€ô€‰Y1%Q%=9}IQ%Pˆ(€€€€€€€•±¥˜…‰Ì¡É•Í¥‘Õ…°¤€ø€Ä¸Àè(€€€€€€€€€€€±…ÍÍ¥™¥…Ñ¥½¸€ô€‰A=1%e}5AA%9}9%Qˆ(€€€€€€€€€€€…ÕÍ”€ô€ (€€€€€€€€€€€€€€€€‰%9Y9Q=Ie}Q%5%9ˆ(€€€€€€€€€€€€€€€¥˜Í•¹…É¥½l‰½‘”‰t¹ÍÑ…ÉÑÍÝ¥Ñ  ‰µ…¹Õ™…ÑÕÉ¥¹|ˆ¤(€€€€€€€€€€€€€€€½ÈÍ•¹…É¥½l‰½‘”‰t¥¸ì(€€€€€€€€€€€€€€€€€€€€‰©Áäˆ°€‰¹½¹Ý½Ù•¹}ÁÉ¥”ˆ°€‰µ…Ñ•É¥…±Í}•á}¹½¹Ý½Ù•¸ˆ(€€€€€€€€€€€€€€€ô(€€€€€€€€€€€€€€€•±Í”€‰%9Q9Q%=91}M=A}@ˆ(€€€€€€€€€€€€€€€¥˜Í•¹…É¥½l‰½‘”‰t€ôô€‰ÁÉ½‘ÕÑ}É½ÕÁ}µ¥àˆ(€€€€€€€€€€€€€€€•±Í”€‰%9Y9Q=Ie}Q%5%9ˆ(€€€€€€€€€€€€€€€¥˜Í•¹…É¥½l‰½‘”‰t€ôô€‰ÁÉ½‘ÕÑ¥½¹}ÅÕ…¹Ñ¥Ñäˆ(€€€€€€€€€€€€€€€•±Í”€‰U9aA1%9ˆ(€€€€€€€€€€€€¤(€€€€€€€•±Í”è(€€€€€€€€€€€±…ÍÍ¥™¥…Ñ¥½¸€ô€‰AMM}=I5U1}=5A1Qˆ(€€€€€€€€€€€…ÕÍ”€ô9½¹”(€€€€€€€É•½É‘Ì¹…ÁÁ•¹¡ì(€€€€€€€€€€€€‰½‘”ˆèÍ•¹…É¥½l‰½‘”‰t°(€€€€€€€€€€€€‰±…‰•°ˆèÍ•¹…É¥½l‰±…‰•°‰t°(€€€€€€€€€€€€‰¡…¹•‘}Í½ÕÉ•Ìˆè¡…¹•‘}Í½ÕÉ•Ì°(€€€€€€€€€€€€‰•áÑ•É¹…±}Í½ÕÉ•ÌˆèÍ•¹…É¥¼¹•Ð ‰•áÑ•É¹…±}Í½ÕÉ•Ìˆ°mt¤°(€€€€€€€€€€€€‰Á…¥É}½¹ÑÉ½±ÌˆèÁ…¥É}½¹ÑÉ½±Ì°(€€€€€€€€€€€€‰™½ÉµÕ±…}ÍÑ…ÑÕÌˆè€ (€€€€€€€€€€€€€€€€‰aQI91}I%YHˆ(€€€€€€€€€€€€€€€¥˜¹½Ð¡…¹•‘}Í½ÕÉ•Ì…¹Í•¹…É¥¼¹•Ð ‰•áÑ•É¹…±}Í½ÕÉ•Ìˆ¤(€€€€€€€€€€€€€€€•±Í”€‰=I5U1}=5A1Qˆ(€€€€€€€€€€€€€€€¥˜‘•Á•¹‘•¹ål‰™½ÉµÕ±…}½µÁ±•Ñ”‰t(€€€€€€€€€€€€€€€•±Í”€‰=I5U1}%9=5A1Qˆ(€€€€€€€€€€€€¤°(€€€€€€€€€€€€‰™…±±‰…­}•±±Ìˆè‘•Á•¹‘•¹ål‰™…±±‰…­}•±±Ì‰t°(€€€€€€€€€€€€‰Õ¹±¥¹­•‘}Í½ÕÉ•Ìˆè‘•Á•¹‘•¹ål‰Õ¹±¥¹­•‘}Í½ÕÉ•Ì‰t°(€€€€€€€€€€€€‰‘•Á•¹‘•¹å}Á…Ñ¡Ìˆè‘•Á•¹‘•¹ål‰Í½ÕÉ•}Á…Ñ¡Ì‰t°(€€€€€€€€€€€€‰½Á•É…Ñ¥¹}ÁÉ½™¥Ñ}‘•±Ñ„ˆè½µÁ…É¥Í½¹}É•ÍÕ±Ñl‰½Á•É…Ñ¥¹}ÁÉ½™¥Ñ}‘•±Ñ„‰t°(€€€€€€€€€€€€‰•áÁ•Ñ•‘}‘•Ñ•Éµ¥¹¥ÍÑ¥}•™™•Ðˆè•áÁ•Ñ•‘}Ñ½Ñ…°°(€€€€€€€€€€€€‰…ÑÕ…±}‘•Ñ•Éµ¥¹¥ÍÑ¥}•™™•Ðˆè½µÁ…É¥Í½¹}É•ÍÕ±Ñl‰•™™•ÑÍ}Ñ½Ñ…°‰t°(€€€€€€€€€€€€‰Ñ…É•Ñ}•™™•ÑÌˆèÍ•¹…É¥½l‰Ñ…É•Ñ}•™™•ÑÌ‰t°(€€€€€€€€€€€€‰¹½¹é•É½}•™™•ÑÌˆè¹½¹é•É½}•™™•ÑÌ°(€€€€€€€€€€€€‰Õ¹•áÁ•Ñ•‘}•™™•ÑÌˆèÕ¹•áÁ•Ñ•‘}•™™•ÑÌ°(€€€€€€€€€€€€‰É•Í¥‘Õ…°ˆèÉ•Í¥‘Õ…°°(€€€€€€€€€€€€‰¥‘•¹Ñ¥Ñå}‘•±Ñ„ˆè€ (€€€€€€€€€€€€€€€½µÁ…É¥Í½¹}É•ÍÕ±Ñl‰•™™•ÑÍ}Ñ½Ñ…°‰t€¬É•Í¥‘Õ…°(€€€€€€€€€€€€€€€€´½µÁ…É¥Í½¹}É•ÍÕ±Ñl‰½Á•É…Ñ¥¹}ÁÉ½™¥Ñ}‘•±Ñ„‰t(€€€€€€€€€€€€¤°(€€€€€€€€€€€€‰±…ÍÍ¥™¥…Ñ¥½¸ˆè±…ÍÍ¥™¥…Ñ¥½¸°(€€€€€€€€€€€€‰É•Í¥‘Õ…±}…ÕÍ”ˆè…ÕÍ”°(€€€€€€€ô¤(€€€É•ÑÕÉ¸ì‰µ½¹Ñ ˆèµ½¹Ñ °€‰Í•¹…É¥½ÌˆèÉ•½É‘Íô(()‘•˜Ù…±¥‘…Ñ•}•á•±}…±Õ±…Ñ•‘}Á…¥È (€€€‰…Í•}Á…Ñ èA…Ñ ð9½¹”°(€€€½µÁ…É¥Í½¹}Á…Ñ èA…Ñ ð9½¹”°(€€€µ…ÁÁ¥¹}Á…Ñ èA…Ñ °(€€€€¨°(€€€µ½¹Ñ è¥¹Ð€ô€Ü°(¤€´ø‘¥ÑmÍÑÈ°¹åtè(€€€€ˆˆ‰I•…µ½¹±ä…•ÁÑ…¹”…Ñ”™½ÈÑÝ¼Ý½É­‰½½­Ì…±Õ±…Ñ•…¹Í…Ù•‰äá•°¸ˆˆˆ(€€€¥˜€ (€€€€€€€‰…Í•}Á…Ñ ¥Ì9½¹”(€€€€€€€½È½µÁ…É¥Í½¹}Á…Ñ ¥Ì9½¹”(€€€€€€€½È¹½Ð‰…Í•}Á…Ñ ¹¥Í}™¥±” ¤(€€€€€€€½È¹½Ð½µÁ…É¥Í½¹}Á…Ñ ¹¥Í}™¥±” ¤(€€€€¤è(€€€€€€€É•ÑÕÉ¸ì(€€€€€€€€€€€€‰µ½‘”ˆè€‰•á•±}…±Õ±…Ñ•‘}Á…¥Èˆ°(€€€€€€€€€€€€‰ÍÑ…ÑÕÌˆè€‰	1=-}9=}a1}1U1Q}A%Hˆ°(€€€€€€€€€€€€‰‰…Í”ˆèÍÑÈ¡‰…Í•}Á…Ñ ¤¥˜‰…Í•}Á…Ñ •±Í”9½¹”°(€€€€€€€€€€€€‰½µÁ…É¥Í½¸ˆèÍÑÈ¡½µÁ…É¥Í½¹}Á…Ñ ¤¥˜½µÁ…É¥Í½¹}Á…Ñ •±Í”9½¹”°(€€€€€€€ô((€€€É•Á½ÉÐ€ôÙ…±¥‘…Ñ•}Á…¥È¡‰…Í•}Á…Ñ °½µÁ…É¥Í½¹}Á…Ñ °µ…ÁÁ¥¹}Á…Ñ °µ½¹Ñ õµ½¹Ñ ¤(€€€™½ÉµÕ±„€ôÉ•Á½ÉÑl‰™½ÉµÕ±…}•Ù…±Õ…Ñ¥½¸‰t(€€€±½ÍÕÉ•Ì€ôì(€€€€€€€€‰‰…Í”ˆè™½ÉµÕ±…l‰‰…Í•}Á¹±}™Õ±±}‘•Á•¹‘•¹ä‰t°(€€€€€€€€‰½µÁ…É¥Í½¸ˆè™½ÉµÕ±…l‰½µÁ…É¥Í½¹}Á¹±}™Õ±±}‘•Á•¹‘•¹ä‰t°(€€€ô(€€€µ…ÁÁ¥¹œ€ô©Í½¸¹±½…‘Ì¡µ…ÁÁ¥¹}Á…Ñ ¹É•…‘}Ñ•áÐ¡•¹½‘¥¹œô‰ÕÑ˜´àˆ¤¤(€€€½±Õµ¸€ô5=9Q!}=1U59Mmµ½¹Ñ¡t(€€€½É•}½ÕÑÁÕÑÌ€ôì(€€€€€€€¹…µ”è˜‰í½±Õµ¹õíÉ½Ýôˆ(€€€€€€€™½È¹…µ”°É½Ü¥¸µ…ÁÁ¥¹l‰½µÁ…É¥Í½¸‰ul‰Á¹±}É½ÝÌ‰t¹¥Ñ•µÌ ¤(€€€ô(€€€™É•Í¡¹•ÍÌ€ôì(€€€€€€€Í¥‘”èì(€€€€€€€€€€€€‰…¡•‘}™…±±‰…­}½Õ¹Ðˆè±½ÍÕÉ•l‰…¡•‘}™…±±‰…­}½Õ¹Ð‰t°(€€€€€€€€€€€€‰…¡•‘}¹Õµ•É¥}µ¥Íµ…Ñ¡}½Õ¹Ðˆè±½ÍÕÉ•l‰…¡•‘}¹Õµ•É¥}µ¥Íµ…Ñ¡}½Õ¹Ð‰t°(€€€€€€€€€€€€‰™…±±‰…­}•±±Ìˆè±½ÍÕÉ•l‰™…±±‰…­}•±±Ì‰t°(€€€€€€€€€€€€‰…¡•‘}µ¥Íµ…Ñ¡}•±±Ìˆè±½ÍÕÉ•l‰…¡•‘}µ¥Íµ…Ñ¡}•±±Ì‰t°(€€€€€€€€€€€€‰½É•}½ÕÑÁÕÑÌˆè½É•}½ÕÑÁÕÑÌ°(€€€€€€€€€€€€‰½É•}½ÕÑÁÕÑ}¥ÍÍÕ•}•±±ÌˆèÍ½ÉÑ• (€€€€€€€€€€€€€€€Í•Ð¡½É•}½ÕÑÁÕÑÌ¹Ù…±Õ•Ì ¤¤(€€€€€€€€€€€€€€€€˜€¡Í•Ð¡±½ÍÕÉ•l‰™…±±‰…­}•±±Ì‰t¤ðÍ•Ð¡±½ÍÕÉ•l‰…¡•‘}µ¥Íµ…Ñ¡}•±±Ì‰t¤¤(€€€€€€€€€€€€¤°(€€€€€€€€€€€€‰ÍÑ…ÑÕÌˆè€ (€€€€€€€€€€€€€€€€‰AMLˆ(€€€€€€€€€€€€€€€¥˜±½ÍÕÉ•l‰…¡•‘}™…±±‰…­}½Õ¹Ð‰t€ôô€À(€€€€€€€€€€€€€€€…¹±½ÍÕÉ•l‰…¡•‘}¹Õµ•É¥}µ¥Íµ…Ñ¡}½Õ¹Ð‰t€ôô€À(€€€€€€€€€€€€€€€•±Í”€‰!,ˆ(€€€€€€€€€€€€¤°(€€€€€€€ô(€€€€€€€™½ÈÍ¥‘”°±½ÍÕÉ”¥¸±½ÍÕÉ•Ì¹¥Ñ•µÌ ¤(€€€ô(€€€Í½ÕÉ•}¡•­Ì€ômÉ½Ü™½ÈÉ½Ü¥¸É•Á½ÉÑl‰¡•­Ì‰t¥˜É½Ýl‰ÍÑ…ÑÕÌ‰t€ôô€‰!,‰t(€€€±•Ù•±|Ä€ô€‰AMLˆ¥˜¹½ÐÍ½ÕÉ•}¡•­Ì•±Í”€‰!,ˆ(€€€±•Ù•±|È€ô€‰AMLˆ¥˜…±°¡É½Ýl‰ÍÑ…ÑÕÌ‰t€ôô€‰AMLˆ™½ÈÉ½Ü¥¸™É•Í¡¹•ÍÌ¹Ù…±Õ•Ì ¤¤•±Í”€‰!,ˆ(€€€É•ÍÕ±Ð€ôÉ•Á½ÉÑl‰½µÁ…É¥Í½¹}É•ÍÕ±Ð‰t(€€€±•Ù•±|Ì€ô€‰AMLˆ¥˜É•ÍÕ±Ñl‰É•½¹¥±•‰t•±Í”€‰!,ˆ(€€€É•Á½ÉÑl‰•á•±}Á…¥É}…•ÁÑ…¹”‰t€ôì(€€€€€€€€‰µ½‘”ˆè€‰•á•±}…±Õ±…Ñ•‘}Á…¥Èˆ°(€€€€€€€€‰É•…‘}½¹±äˆèQÉÕ”°(€€€€€€€€‰…¡•‘}™É•Í¡¹•ÍÌˆè™É•Í¡¹•ÍÌ°(€€€€€€€€‰±•Ù•±|Å}…±Õ±…Ñ¥½¹}¥‘•¹Ñ¥Ñäˆè±•Ù•±|Ä°(€€€€€€€€‰±•Ù•±|É}Ý½É­‰½½­}ÁÉ½Á……Ñ¥½¸ˆè±•Ù•±|È°(€€€€€€€€‰±•Ù•±|Í}½Á}‰É¥‘•}½µÁ±•Ñ•¹•ÍÌˆè±•Ù•±|Ì°(€€€€€€€€‰½Á•É…Ñ¥¹}ÁÉ½™¥Ñ}‘•±Ñ„ˆèÉ•ÍÕ±Ñl‰½Á•É…Ñ¥¹}ÁÉ½™¥Ñ}‘•±Ñ„‰t°(€€€€€€€€‰•™™•ÑÍ}Ñ½Ñ…°ˆèÉ•ÍÕ±Ñl‰•™™•ÑÍ}Ñ½Ñ…°‰t°(€€€€€€€€‰É•Í¥‘Õ…°ˆèÉ•ÍÕ±Ñl‰É•Í¥‘Õ…°‰t°(€€€€€€€€‰É•Í¥‘Õ…±}É…Ñ¥¼ˆèÉ•Á½ÉÑl‰É•Í¥‘Õ…±}…¹…±åÍ¥Ì‰ul‰É…Ñ¥½}Ñ½}½Á•É…Ñ¥¹}ÁÉ½™¥Ñ}‘•±Ñ„‰t°(€€€€€€€€‰Í½ÕÉ•}±•Ù•±}¡•­ÌˆèÍ½ÕÉ•}¡•­Ì°(€€€€€€€€‰ÍÑ…ÑÕÌˆè€‰AMLˆ¥˜€¡±•Ù•±|Ä°±•Ù•±|È°±•Ù•±|Ì¤€ôô€ ‰AMLˆ°€‰AMLˆ°€‰AMLˆ¤•±Í”€‰!,ˆ°(€€€ô(€€€É•ÑÕÉ¸É•Á½ÉÐ(()‘•˜µ…¥¸ ¤€´ø¥¹Ðè(€€€Á…ÉÍ•È€ô…ÉÁ…ÉÍ”¹ÉÕµ•¹ÑA…ÉÍ•È ¤(€€€Á…ÉÍ•È¹…‘‘}…ÉÕµ•¹Ð ˆ´µ‰…Í”ˆ°ÑåÁ”õA…Ñ ¤(€€€Á…ÉÍ•È¹…‘‘}…ÉÕµ•¹Ð ˆ´µ½µÁ…É¥Í½¸ˆ°ÑåÁ”õA…Ñ ¤(€€€Á…ÉÍ•È¹…‘‘}…ÉÕµ•¹Ð ˆ´µµ…ÁÁ¥¹œˆ°ÑåÁ”õA…Ñ °‘•™…Õ±ÐõA…Ñ  ‰½¹™¥œ½µ½‘•±}µ…ÁÁ¥¹œ¹©Í½¸ˆ¤¤(€€€Á…ÉÍ•È¹…‘‘}…ÉÕµ•¹Ð ˆ´µ•¹•É…Ñ”µ½µÁ…É¥Í½¸ˆ°…Ñ¥½¸ô‰ÍÑ½É•}ÑÉÕ”ˆ¤(€€€Á…ÉÍ•È¹…‘‘}…ÉÕµ•¹Ð ˆ´µ•á•°µ…±Õ±…Ñ•µÁ…¥Èˆ°…Ñ¥½¸ô‰ÍÑ½É•}ÑÉÕ”ˆ¤(€€€Á…ÉÍ•È¹…‘‘}…ÉÕµ•¹Ð ˆ´µ½ÕÑÁÕÐˆ°ÑåÁ”õA…Ñ ¤(€€€…ÉÌ€ôÁ…ÉÍ•È¹Á…ÉÍ•}…ÉÌ ¤(€€€¥˜…ÉÌ¹•á•±}…±Õ±…Ñ•‘}Á…¥Èè(€€€€€€€É•Á½ÉÐ€ôÙ…±¥‘…Ñ•}•á•±}…±Õ±…Ñ•‘}Á…¥È¡…ÉÌ¹‰…Í”°…ÉÌ¹½µÁ…É¥Í½¸°…ÉÌ¹µ…ÁÁ¥¹œ¤(€€€•±Í”è(€€€€€€€¥˜…ÉÌ¹‰…Í”¥Ì9½¹”½È…ÉÌ¹½µÁ…É¥Í½¸¥Ì9½¹”è(€€€€€€€€€€€Á…ÉÍ•È¹•ÉÉ½È ˆ´µ‰…Í”…¹€´µ½µÁ…É¥Í½¸…É”É•ÅÕ¥É•½ÕÑÍ¥‘”Á…¥Èµ‰±½­•È¡•­Ìˆ¤(€€€€€€€¥˜…ÉÌ¹•¹•É…Ñ•}½µÁ…É¥Í½¸è(€€€€€€€€€€€…ÉÌ¹½µÁ…É¥Í½¸¹Á…É•¹Ð¹µ­‘¥È¡Á…É•¹ÑÌõQÉÕ”°•á¥ÍÑ}½¬õQÉÕ”¤(€€€€€€€€€€€‰Õ¥±‘}½µÁ…É¥Í½¸¡…ÉÌ¹‰…Í”°…ÉÌ¹½µÁ…É¥Í½¸°…ÉÌ¹µ…ÁÁ¥¹œ¤(€€€€€€€É•Á½ÉÐ€ôÙ…±¥‘…Ñ•}Á…¥È¡…ÉÌ¹‰…Í”°…ÉÌ¹½µÁ…É¥Í½¸°…ÉÌ¹µ…ÁÁ¥¹œ¤(€€€É•¹‘•É•€ô©Í½¸¹‘ÕµÁÌ¡É•Á½ÉÐ°•¹ÍÕÉ•}…Í¥¤õ…±Í”°¥¹‘•¹ÐôÈ°‘•™…Õ±ÐõÍÑÈ¤(€€€¥˜…ÉÌ¹½ÕÑÁÕÐè(€€€€€€€…ÉÌ¹½ÕÑÁÕÐ¹Á…É•¹Ð¹µ­‘¥È¡Á…É•¹ÑÌõQÉÕ”°•á¥ÍÑ}½¬õQÉÕ”¤(€€€€€€€…ÉÌ¹½ÕÑÁÕÐ¹ÝÉ¥Ñ•}Ñ•áÐ¡É•¹‘•É•°•¹½‘¥¹œô‰ÕÑ˜´àˆ¤(€€€•±Í”è(€€€€€€€ÁÉ¥¹Ð¡É•¹‘•É•¤(€€€É•ÑÕÉ¸€À(()¥˜}}¹…µ•}|€ôô€‰}}µ…¥¹}|ˆè(€€€É…¥Í”MåÍÑ•µá¥Ð¡µ…¥¸ ¤¤(