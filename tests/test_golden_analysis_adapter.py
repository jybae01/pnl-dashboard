from __future__ import annotations

import json

from openpyxl import Workbook, load_workbook

from forecast.analysis.configuration import AnalysisConfig
from forecast.analysis.golden_adapter import GoldenAnalysisAdapter
from forecast.comparison import GenericComparisonEngine, PeriodOption
from forecast.storage import ModelMeta
from forecast.workbook import GoldenWorkbook


def _meta(identifier: str) -> ModelMeta:
    return ModelMeta(
        identifier, identifier, "계획", 2026, 1, 12,
        "2026-01-01", "V1", True, f"{identifier}.xlsx", "now",
    )


def _build_workbook(path, *, comparison: bool = False) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Data"
    sheet["B287"] = "★제조경비 명세서_입력"
    sheet["C289"] = "노무비"
    sheet["D290"] = "급료"
    sheet["C296"] = "제조경비"
    for row, account in (
        (297, "수도광열비"),
        (298, "소모품비"),
        (304, "원자재운반비"),
        (305, "외주가공비"),
        (306, "신규 제조계정"),
    ):
        sheet.cell(row, 3, "변동비" if row in {297, 298, 304, 305} else "고정비")
        sheet.cell(row, 4, account)
    sheet["B321"] = "*제조원가 변동비/고정비 비율"

    sheet["B1166"] = "★판매관리비 관리 명세서"
    sheet["B1167"] = "판매비"
    for row, classification, account in (
        (1168, "변동비", "운반비"),
        (1170, "변동비", "브랜드사용료"),
        (1194, "변동비", "포장비"),
    ):
        sheet.cell(row, 2, classification)
        sheet.cell(row, 3, account)
    sheet["B1197"] = "일반관리비"
    for row, account in ((1198, "급여"), (1214, "운반비"), (1221, "신규 판관계정")):
        sheet.cell(row, 2, "고정비")
        sheet.cell(row, 3, account)
    sheet["B1244"] = "★손익계산서"
    sheet["C325"] = "제조원가"
    sheet["C1269"] = "1. 제품 매출원가(천원)"
    sheet["C1280"] = "2. 반제품 매출원가(천원)"

    column = 5
    def put(row: int, base: float, target: float | None = None):
        sheet.cell(row, column, target if comparison and target is not None else base)

    put(9, 10, 12)
    put(205, 1_000)
    put(206, 10_000, 12_000)
    put(208, 1_000)
    put(209, 0)
    put(211, 10_000, 12_000)
    # Finished-product front unit cost is the mapped front amount divided by
    # the mapped front production basis; allocation-ratio rows are unrelated.
    put(128, 1_000, 1_000)
    put(425, 100)
    put(426, 1_000, 1_200)
    put(430, 0)
    put(431, 0)
    put(435, 0)
    put(436, 0)

    put(32, 100, 90)
    put(35, 1)
    put(38, 0)
    put(41, 1)
    put(1593, 100, 90)
    # Slice 5D production contract requires authoritative, positive Base
    # denominators for every manufactured product group.  These core-only
    # sources deliberately exclude the adjustment/merchandise rows.
    put(1632, 10, 10)
    put(1645, 10, 10)
    put(1668, 10, 10)
    put(1720, 10, 10)
    put(1031, 100, 90)
    put(1056, 0, 0)
    put(1081, 10, 10)
    put(1106, 0, 0)
    put(1131, 10, 10)
    put(473, 10, 10)
    put(494, 0, 0)
    put(515, 0, 0)
    put(1595, 100, 90)
    put(1634, 10, 10)
    put(1647, 10, 10)
    put(1670, 10, 10)
    put(1722, 10, 10)
    put(1154, 120, 110)
    put(536, 10, 10)
    for row, base, target in (
        (532, 10, 20), (533, 1_000, 2_400),
        (1026, 2, 4), (1027, 40, 100),
        (1051, 3, 6), (1052, 90, 180),
        (1076, 5, 7), (1077, 200, 350),
        (1101, 5, 3), (1102, 300, 150),
        (1126, 8, 10), (1127, 560, 800),
    ):
        put(row, base, target)
    put(556, 60)
    put(557, 40)
    put(568, 10)
    put(569, 0)
    for row, value in ((897, 60), (904, 40), (580, 1), (583, 1)):
        put(row, value)
    for row in (956, 957):
        put(row, 1)
    put(273, 0.1)
    put(274, 0)
    put(275, 0)
    put(685, 300, 100)
    put(694, 0)
    put(697, 0)
    put(699, 300, 100)
    put(788, 0.5)
    put(789, 0.5)
    for row in (790, 791, 792):
        put(row, 0)
    for row, base, target in (
        (899, 0, 0), (900, 50, 50), (906, 0, 0), (907, 50, 50),
    ):
        put(row, base, target)

    # Other material groups are valid zero-activity rows in this fixture.
    for row in (
        44, 47, 50, 53, 56, 59, 62, 65, 68, 71, 74, 77,
        119, 122, 125, 558, 559, 560, 570, 571, 911, 918, 925,
        586, 589, 592, 958, 959, 960, 913, 914, 920, 921, 927,
    ):
        put(row, 0)

    put(345, 0.5, 0.9)
    put(346, 0.2, 0.9)
    put(347, 0.4, 0.9)
    for row, base, target in (
        (290, 100, 110),
        (297, 1_000, 900),
        (298, 200, 180),
        (304, 100, 80),
        (305, 500, 450),
        (306, 50, 40),
    ):
        put(row, base, target)
    put(119, 100, 80)
    put(556, 60, 60)
    put(557, 40, 40)
    put(558, 0, 20)
    put(568, 10, 20)

    # Comparison realization rate = COGS / current-period manufacturing input = 1.
    put(1268, 200)
    put(325, 200)
    put(1269, 200)
    put(1280, 0)
    put(1248, 300)
    put(1306, 25)
    put(1276, 100)
    put(1273, 0)
    put(1274, 0)
    put(1285, 0)
    put(1277, 25)
    put(1286, 25)
    put(1278, 25)
    put(1287, 0)
    put(1279, 25)
    put(1288, 0)

    for row, base, target in (
        (1168, 10, 20), (1170, 30, 25), (1194, 40, 35),
        (1198, 50, 45), (1214, 5, 6), (1221, 7, 8),
    ):
        put(row, base, target)
    workbook.save(path)


def _adapter() -> GoldenAnalysisAdapter:
    mapping = json.loads(open("config/model_mapping.json", encoding="utf-8").read())
    production_evidence_mapping = json.loads(
        open("config/analysis_production_evidence_sources.json", encoding="utf-8").read()
    )
    config = AnalysisConfig.load("config/analysis_v1.json")
    return GoldenAnalysisAdapter(mapping, config, production_evidence_mapping)


def test_adapter_calculates_material_three_part_identity_from_golden_cells(tmp_path):
    base_path = tmp_path / "base.xlsx"
    comparison_path = tmp_path / "comparison.xlsx"
    _build_workbook(base_path)
    _build_workbook(comparison_path, comparison=True)
    adapter = _adapter()
    base = adapter.build(GoldenWorkbook(base_path), _meta("base"), (1,))
    comparison = adapter.build(GoldenWorkbook(comparison_path), _meta("comparison"), (1,))
    result = adapter.material_analysis(base, comparison)
    sw = next(row for row in result["product_groups"] if row["product_group"] == "SW")

    assert sw["baseline_unit_cost"] == 11
    assert sw["comparison_unit_cost"] == 13
    assert sw["total"] == -180
    assert sw["nonwoven_price_ex_fx"] == 0
    assert sw["nonwoven_jpy"] == -180
    assert sw["materials_ex_nonwoven"] == 0
    assert sw["total"] == (
        sw["nonwoven_price_ex_fx"]
        + sw["nonwoven_jpy"]
        + sw["materials_ex_nonwoven"]
    )
    assert result["jpy_fx_unit"] == "KRW/JPY"
    sw_trace = next(
        row for row in result["trace_rows"] if row["product_group"] == "SW"
    )
    assert "Data!E211" in sw_trace["base_source_reference"]
    assert "Data!E1593" in sw_trace["comparison_source_reference"]
    nonwoven_trace = result["nonwoven_trace_rows"][0]
    assert "Data!E206" in nonwoven_trace["base_source_reference"]
    assert "Data!E9" in nonwoven_trace["comparison_source_reference"]
    assert nonwoven_trace["canonical_fields"].endswith("jpy_fx_krw_per_jpy")
    assert "mcm" not in str(result).lower()
    assert "yield" not in str(result).lower()


def test_finished_product_material_uses_front_basis_and_back_pairs_once(tmp_path):
    path = tmp_path / "raw-material.xlsx"
    _build_workbook(path)
    workbook = load_workbook(path)
    sheet = workbook["Data"]
    # Make the old pool/allocation route visibly disagree with the mapped
    # product cells.  It must not affect the normalized finished-product cost.
    sheet["E699"] = 999_999
    sheet["E273"] = 0.99
    sheet["E788"] = 0.99
    sheet["E789"] = 0.01
    workbook.save(path)

    adapted = _adapter().build(GoldenWorkbook(path), _meta("base"), (1,))
    sw = next(row for row in adapted.scenario.products if row.product_code == "SW_CORE")

    # (10,000 / 1,000) * (60 + 40) + (50 + 50); E900/E907 are included in
    # their back pairs and must not be added again as standalone MCM costs.
    assert sw.raw_material_cost == 1_100
    assert "Data!E699" not in sw.raw_material_cost_source
    roles = {(item["role"], item["source"]) for item in sw.raw_material_components}
    assert {
        ("front_amount", "Data!E211"),
        ("front_production_basis", "Data!E128"),
        ("production_quantity", "Data!E897"),
        ("input_length", "Data!E580"),
        ("adjustment", "Data!E956"),
        ("back_total_component", "Data!E899"),
        ("back_total_component", "Data!E900"),
        ("production_quantity", "Data!E904"),
        ("input_length", "Data!E583"),
        ("adjustment", "Data!E957"),
        ("back_total_component", "Data!E906"),
        ("back_total_component", "Data!E907"),
    } <= roles


def test_adapter_maps_inventory_ledger_production_quantity_and_amount_sources(tmp_path):
    path = tmp_path / "production-evidence.xlsx"
    _build_workbook(path)

    adapted = _adapter().build(GoldenWorkbook(path), _meta("base"), (1,))
    records = {row.product_group: row for row in adapted.scenario.production_evidence}

    assert (records["FS"].quantity, records["FS"].amount) == (10, 1_000)
    assert records["FS"].quantity_source == "Data!E532"
    assert records["FS"].amount_source == "Data!E533"
    assert (records["SW"].quantity, records["SW"].amount) == (5, 130)
    assert records["SW"].quantity_source_rows == (1026, 1051)
    assert records["SW"].amount_source_rows == (1027, 1052)
    assert (records["BW"].quantity, records["BW"].amount) == (10, 500)
    assert records["BW"].quantity_source_rows == (1076, 1101)
    assert records["BW"].amount_source_rows == (1077, 1102)
    assert (records["LC"].quantity, records["LC"].amount) == (8, 560)
    assert records["LC"].quantity_source == "Data!E1126"
    assert records["LC"].amount_source == "Data!E1127"


def test_inventory_ledger_evidence_changes_do_not_mutate_effects_or_op_bridge(tmp_path):
    base_path = tmp_path / "base.xlsx"
    comparison_path = tmp_path / "comparison.xlsx"
    _build_workbook(base_path)
    _build_workbook(comparison_path, comparison=True)
    engine = GenericComparisonEngine("config/model_mapping.json")
    period = PeriodOption("M01", "1월", (1,), "월")

    before = engine.compare(
        _meta("base"), base_path, _meta("comparison"), comparison_path, period
    )
    workbook = load_workbook(comparison_path)
    sheet = workbook["Data"]
    for row in (532, 1026, 1051, 1076, 1101, 1126):
        sheet[f"E{row}"] = float(sheet[f"E{row}"].value or 0) * 3 + 1
    for row in (533, 1027, 1052, 1077, 1102, 1127):
        sheet[f"E{row}"] = float(sheet[f"E{row}"].value or 0) * 7 + 10_000
    workbook.save(comparison_path)

    after = engine.compare(
        _meta("base"), base_path, _meta("comparison"), comparison_path, period
    )

    assert before.production_evidence != after.production_evidence
    assert before.effects == after.effects
    assert before.operating_profit_delta == after.operating_profit_delta
    assert before.effects_total == after.effects_total
    assert before.residual == after.residual
    assert before.reconciled == after.reconciled


def test_adapter_marks_blank_inventory_source_as_validation_failure(tmp_path):
    path = tmp_path / "blank-inventory-source.xlsx"
    _build_workbook(path)
    workbook = load_workbook(path)
    workbook["Data"]["E325"] = None
    workbook.save(path)

    adapted = _adapter().build(GoldenWorkbook(path), _meta("base"), (1,))

    assert adapted.scenario.inventory_costs[0].source_validation_status == "FAIL"
    assert adapted.scenario.inventory_costs[0].scope_validation_status == "FAIL"


def test_material_uses_direct_input_total_rows_211_and_699(tmp_path):
    base_path = tmp_path / "base.xlsx"
    comparison_path = tmp_path / "comparison.xlsx"
    _build_workbook(base_path)
    _build_workbook(comparison_path)
    workbook = load_workbook(comparison_path)
    workbook["Data"]["E211"] = 11_000
    workbook["Data"]["E699"] = 400
    workbook.save(comparison_path)
    adapter = _adapter()
    base = adapter.build(GoldenWorkbook(base_path), _meta("base"), (1,))
    comparison = adapter.build(GoldenWorkbook(comparison_path), _meta("comparison"), (1,))
    result = adapter.material_analysis(base, comparison)

    assert result["total"] < 0
    assert result["nonwoven_price_ex_fx"] == 0
    assert result["nonwoven_jpy"] == 0
    assert result["materials_ex_nonwoven"] == result["total"]


def test_adapter_calculates_all_manufacturing_accounts_with_baseline_ratios(tmp_path):
    base_path = tmp_path / "base.xlsx"
    comparison_path = tmp_path / "comparison.xlsx"
    _build_workbook(base_path)
    _build_workbook(comparison_path, comparison=True)
    adapter = _adapter()
    base = adapter.build(GoldenWorkbook(base_path), _meta("base"), (1,))
    comparison = adapter.build(GoldenWorkbook(comparison_path), _meta("comparison"), (1,))
    accounts, analysis = adapter.manufacturing_accounts(base, comparison)

    assert [row["account"] for row in accounts] == [
        "급료", "수도광열비", "소모품비", "원자재운반비", "외주가공비", "신규 제조계정",
    ]
    utilities = next(row for row in accounts if row["account"] == "수도광열비")
    assert utilities["classification"] == "variable"
    assert utilities["allocation_ratio_row"] == 347
    assert utilities["baseline_front_ratios"] == [0.4]
    assert utilities["activity_effect"] + utilities["unit_effect"] == 100
    assert utilities["occurrence_effect"] == (
        utilities["baseline_amount"] - utilities["comparison_amount"]
    )
    assert utilities["inventory_realization_rate"] == 1
    assert utilities["final_profit_effect"] == 100
    assert analysis["inventory_realization_rate"] == 1
    utilities_trace = next(
        row for row in analysis["trace_rows"] if row["account"] == "수도광열비"
    )
    assert utilities_trace["base_amount_source"] == "Data!E297"
    assert utilities_trace["front_ratio_source"] == "Data!E347"
    assert utilities_trace["base_front_allocated"] == 400
    assert utilities_trace["comparison_front_allocated"] == 360
    assert utilities_trace["validation_status"] == "SOURCE_MAPPED"
    assert all("기타 제조경비" not in row["account"] for row in accounts)


def test_adapter_discovers_new_sga_rows_and_keeps_transport_sections_distinct(tmp_path):
    path = tmp_path / "model.xlsx"
    _build_workbook(path)
    adapter = _adapter()
    adapted = adapter.build(GoldenWorkbook(path), _meta("base"), (1,))
    rows = adapted.sga_source_rows

    assert any(row["account"] == "신규 판관계정" for row in rows)
    selling_transport = next(
        row for row in rows if row["account"] == "운반비" and row["section"] == "판매비"
    )
    general_transport = next(
        row for row in rows if row["account"] == "운반비" and row["section"] == "일반관리비"
    )
    assert selling_transport["row"] == 1168
    assert general_transport["row"] == 1214


def test_adapter_does_not_create_mixed_unit_transport_activity(tmp_path):
    path = tmp_path / "model.xlsx"
    _build_workbook(path)
    adapted = _adapter().build(
        GoldenWorkbook(path), _meta("base"), (1,), sales_fx=1500.0
    )

    assert any(row.unit_basis == "PCS" for row in adapted.scenario.products)
    assert any(row.unit_basis == "LENGTH" for row in adapted.scenario.products)
    assert adapted.scenario.activities[0].transport_activity == 0.0
    assert all(row.sales_fx == 1500.0 for row in adapted.scenario.products)
