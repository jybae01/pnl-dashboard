from __future__ import annotations

import json
from io import BytesIO

from openpyxl import load_workbook

from forecast.analysis_export import build_comparison_audit_workbook
from forecast.sales_comparison import calculate_sales_effect_rows, sales_effect_totals


class FakeGoldenWorkbook:
    def __init__(self, path):
        self.path = str(path)
        self.formulas = {"E10": "=1+1", "E20": "=E10*2"}

    def value(self, cell):
        return 200.0 if "comparison" in self.path else 100.0


def test_build_comparison_audit_workbook(monkeypatch, tmp_path):
    monkeypatch.setattr("forecast.analysis_export.GoldenWorkbook", FakeGoldenWorkbook)
    mapping_path = tmp_path / "mapping.json"
    mapping_path.write_text(json.dumps({
        "manufacturing_input_rows": [289, 319],
        "comparison": {
            "pnl_rows": {"operating_profit": 10},
            "pnl_labels": {"operating_profit": "영업이익"},
            "products": {},
            "sales_groups": {"SW": {"label": "SW", "quantity_row": 10, "amount_row": 20, "cogs_row": 30}},
            "production_rows": {"SW400": 40},
            "production_labels": {"SW400": "SW400 생산량"},
            "mcm_rows": {"SW400": 50},
            "mcm_labels": {"SW400": "MCM SW400"},
            "cost_rows": {"raw_material": {"add": [60], "subtract": [61]}},
            "cost_labels": {"raw_material": "원재료비"},
            "effect_rows": {"revenue": 70},
            "effect_labels": {"revenue": "매출액"},
        },
        "analysis_adapter": {
            "material": {
                "jpy_fx_row": 9,
                "front_process": {
                    "nonwoven_quantity_row": 205,
                    "nonwoven_amount_row": 206,
                    "nonwoven_unit_row": 207,
                    "other_quantity_row": 208,
                    "other_amount_row": 209,
                    "other_unit_row": 210,
                    "total_amount_row": 211
                },
                "back_process": {"source_start_row": 684, "source_end_row": 699}
            },
            "account_discovery": {"manufacturing_start_marker": "제조경비"},
            "manufacturing": {
                "front_ratio_rows": {"labor": 345, "outsourcing": 346, "other_variable": 347}
            },
            "inventory_timing": {
                "current_manufacturing_cost": {"row": 325, "business_source": "당기투입제조원가"},
                "finished_goods_cogs": {"row": 1269, "business_source": "제품 매출원가"},
                "semi_finished_goods_cogs": {"row": 1280, "business_source": "반제품 매출원가"},
                "opening_inventory_units": {
                    "FS": {"quantity_rows": [529], "amount_rows": [530]},
                    "SW": {"quantity_rows": [1022, 1047], "amount_rows": [1023, 1048]},
                    "BW": {"quantity_rows": [1072, 1097], "amount_rows": [1073, 1098]},
                    "LC": {"quantity_rows": [1122], "amount_rows": [1123]}
                }
            }
        }
    }), encoding="utf-8")

    result = {
        "baseline": {"id": "base", "name": "기준", "model_type": "계획", "version": "V1"},
        "comparison": {"id": "comp", "name": "비교", "model_type": "실적", "version": "V1"},
        "period": {"label": "1월", "months": [1]},
        "pnl": [{"code": "operating_profit", "item": "영업이익", "baseline": 1000, "comparison": 1200, "delta": 200}],
        "effects": [
            {"code": "revenue", "factor": "매출액", "baseline": 1000, "comparison": 1200, "delta": 200, "profit_effect": 200},
            {"code": "inventory_timing", "factor": "재고·원가 반영시차 효과", "baseline": 1000, "comparison": 900, "delta": -100, "profit_effect": 60},
        ],
        "operating_profit_delta": 200,
        "effects_total": 260,
        "residual": -60,
        "reconciled": False,
        "cost_summary": [
            {"code": "raw_material", "item": "원재료비", "baseline": 300, "comparison": 350, "delta": 50},
            {"code": "selling_expense", "item": "판매비", "baseline": 100, "comparison": 90, "delta": -10},
        ],
        "mcm": [{"code": "SW400", "item": "MCM SW400", "baseline": 10, "comparison": 20, "delta": 10}],
        "production": [{"code": "SW400", "item": "SW400 생산량", "baseline": 100, "comparison": 110, "delta": 10}],
        "material_analysis": {
            "product_groups": [{
                "product_group": "SW", "baseline_unit_cost": 10, "comparison_unit_cost": 12,
                "unit_cost_delta": 2, "nonwoven_price_ex_fx": -50,
                "nonwoven_jpy": -30, "materials_ex_nonwoven": -120,
                "total": -200, "calculation_status": "완료",
            }],
        },
        "manufacturing_accounts": [{
            "row": 297, "account": "수도광열비", "classification": "variable",
            "allocation_ratio_row": 347, "baseline_front_ratios": [0.54],
            "baseline_amount": 100, "comparison_amount": 90, "delta": -10,
            "activity_effect": 4, "unit_effect": 6, "fixed_effect": 0,
            "occurrence_effect": 10, "inventory_realization_rate": 1.1,
            "inventory_realization_reference_only": True,
            "final_profit_effect": 10, "calculation_status": "완료",
        }],
        "inventory_analysis": {
            "manufactured_cogs_effect": 100,
            "current_manufacturing_cost_effect": 40,
            "inventory_timing_effect": 60,
            "source_validation_status": "PASS",
            "scope_validation_status": "PASS",
            "product_unit_coverage": "LIMITED",
            "materiality_status": "UNCONFIGURED",
            "persistence": "CONSISTENT",
            "primary": "NO_PRIMARY",
            "supporting": ["Rolling 3M CONSISTENT"],
            "reference": ["FS opening inventory unit cost"],
            "confidence": "LOW",
            "explanation_rule": "RULE_NO_PRIMARY:LIMITED_COVERAGE,MATERIALITY_UNCONFIGURED",
            "fallback_narrative": "Source만으로 단일 원인을 특정하기 어려움",
            "additive_bridge_status": "PASS",
            "current_cost_explanation_gap": 0,
            "scope_notes": ["제품+반제품 COGS only"],
            "source_details": [
                {"side": "BASE", "period": "2026-01", "business_source": "제품 매출원가", "canonical_field": "finished_goods_cogs", "unit": "KRW", "source_reference": "Data!E1269", "value": 700, "validation_status": "PASS"},
                {"side": "BASE", "period": "2026-01", "business_source": "반제품 매출원가", "canonical_field": "semi_finished_goods_cogs", "unit": "KRW", "source_reference": "Data!E1280", "value": 300, "validation_status": "PASS"},
                {"side": "BASE", "period": "2026-01", "business_source": "당기투입제조원가", "canonical_field": "current_manufacturing_cost", "unit": "KRW", "source_reference": "Data!E325", "value": 900, "validation_status": "PASS"},
                {"side": "COMPARISON", "period": "2026-01", "business_source": "제품 매출원가", "canonical_field": "finished_goods_cogs", "unit": "KRW", "source_reference": "Data!E1269", "value": 650, "validation_status": "PASS"},
                {"side": "COMPARISON", "period": "2026-01", "business_source": "반제품 매출원가", "canonical_field": "semi_finished_goods_cogs", "unit": "KRW", "source_reference": "Data!E1280", "value": 250, "validation_status": "PASS"},
                {"side": "COMPARISON", "period": "2026-01", "business_source": "당기투입제조원가", "canonical_field": "current_manufacturing_cost", "unit": "KRW", "source_reference": "Data!E325", "value": 860, "validation_status": "PASS"}
            ],
            "monthly_details": [
                {"period": "2025-11", "inventory_timing_effect": 20, "direction": "IMPROVEMENT", "source_reference": "Base: Data!C1269, Data!C1280, Data!C325 / Comparison: Data!C1269, Data!C1280, Data!C325"},
                {"period": "2025-12", "inventory_timing_effect": 30, "direction": "IMPROVEMENT", "source_reference": "Base: Data!D1269, Data!D1280, Data!D325 / Comparison: Data!D1269, Data!D1280, Data!D325"},
                {"period": "2026-01", "inventory_timing_effect": 60, "direction": "IMPROVEMENT", "source_reference": "Base: Data!E1269, Data!E1280, Data!E325 / Comparison: Data!E1269, Data!E1280, Data!E325"}
            ],
            "opening_inventory_units": [
                {"product_group": "FS", "unit_basis": "LENGTH", "specification": "FS", "base_unit_cost": 10, "comparison_unit_cost": 9, "evidence_direction": "IMPROVEMENT", "direction_aligned": True, "coverage": "LIMITED", "base_source_reference": "Data!E530 / Data!E529", "comparison_source_reference": "Data!E530 / Data!E529"},
                {"product_group": "LC", "unit_basis": "PCS", "specification": "4-inch", "base_unit_cost": 20, "comparison_unit_cost": 21, "evidence_direction": "DETERIORATION", "direction_aligned": False, "coverage": "LIMITED", "base_source_reference": "Data!E1123 / Data!E1122", "comparison_source_reference": "Data!E1123 / Data!E1122"}
            ]
        },
        "sga_accounts": [{
            "row": 1168, "section": "판매비", "account": "운반비",
            "classification": "transport", "baseline_amount": 10,
            "comparison_amount": 20, "delta": 10, "profit_effect": 0,
            "bridge_position": "판매효과",
        }],
    }
    result["evidence_provenance"] = {
        "result_id": "44444444-4444-4444-8444-444444444444",
        "analysis_request": {"start_month": 1, "end_month": 1},
    }
    sales_input = [{
        "product_group": "SW",
        "baseline_quantity": 100,
        "baseline_amount": 1_000_000,
        "baseline_gross_margin_rate": 0.3,
        "comparison_quantity": 110,
        "comparison_amount": 1_210_000,
        "comparison_gross_margin_rate": 0.32,
    }]
    sales_rows = calculate_sales_effect_rows(sales_input, 1400.0, 1450.0)
    totals = sales_effect_totals(sales_rows)
    totals.update({
        "mix_effect": 0.0,
        "baseline_transport_ex_tariff": 30_000_000.0,
        "comparison_transport_ex_tariff": 40_000_000.0,
        "transport_effect": -10_000_000.0,
        "sales_price_effect": totals["pure_price_effect"] - 10_000_000.0,
        "total_sales_effect": totals["total_sales_effect"] - 10_000_000.0,
    })

    payload = build_comparison_audit_workbook(
        result=result,
        sales_rows=sales_rows,
        sales_totals=totals,
        baseline_fx=1400.0,
        comparison_fx=1450.0,
        baseline_path=tmp_path / "baseline.xlsx",
        comparison_path=tmp_path / "comparison.xlsx",
        mapping_path=mapping_path,
    )

    workbook = load_workbook(BytesIO(payload), data_only=False)
    assert "원천셀_추적" in workbook.sheetnames
    assert workbook["판매효과_검증"]["D5"].value.startswith("=")
    assert workbook["판매효과_검증"]["Y6"].value == 30_000_000.0
    assert workbook["판매효과_검증"]["Z6"].value == 40_000_000.0
    assert workbook["판매효과_검증"]["AA6"].value == "=Y6-Z6"
    assert workbook["판매효과_검증"]["S6"].value == -10_000_000.0
    assert workbook["손익_정합성"]["G5"].value == "=E5-D5"
    assert workbook["원천셀_추적"].max_row > 4
    trace_cells = {
        cell.value
        for row in workbook["원천셀_추적"].iter_rows()
        for cell in row
        if isinstance(cell.value, str) and cell.value.startswith("E")
    }
    assert {"E9", "E205", "E211", "E325", "E1269", "E1280", "E684", "E699", "E289", "E319", "E345", "E347"} <= trace_cells
    assert workbook["README"]["B15"].value == "PASS"
    assert "44444444-4444-4444-8444-444444444444" in {
        cell.value for row in workbook["README"].iter_rows() for cell in row
    }
    material_text = " ".join(
        str(cell.value or "") for row in workbook["원부재료_검증"].iter_rows() for cell in row
    )
    assert "MCM SW400" not in material_text
    assert workbook["원부재료_검증"]["I5"].value == "=SUM(E5:G5)"
    assert workbook["생산제조경비_검증"]["O5"].value == "=SUM(I5:K5)"
    assert workbook["생산제조경비_검증"]["D5"].value == 347
    inventory_sheet = workbook["재고시차_검증"]
    assert inventory_sheet["B7"].value == "=B5+B6"
    assert inventory_sheet["C7"].value == "=C5+C6"
    assert inventory_sheet["D10"].value == "=B7-C7"
    assert inventory_sheet["D11"].value == "=B8-C8"
    assert inventory_sheet["D12"].value == "=D10-D11"
    assert "Data!E325" in inventory_sheet["G8"].value
    first_rolling_row = next(
        row
        for row in range(1, inventory_sheet.max_row + 1)
        if inventory_sheet[f"A{row}"].value == "2025-11"
    )
    assert "Data!C1269" in inventory_sheet[f"E{first_rolling_row}"].value
    reconciliation_sheet = workbook["손익_정합성"]
    inventory_bridge_row = next(
        row
        for row in range(5, reconciliation_sheet.max_row + 1)
        if reconciliation_sheet[f"B{row}"].value == "inventory_timing"
    )
    assert reconciliation_sheet[f"G{inventory_bridge_row}"].value == "='재고시차_검증'!D12"
    assert "G7:G8" in reconciliation_sheet["G11"].value
    assert "F10-(G11+F12)" in reconciliation_sheet["H13"].value
    assert "F12" in reconciliation_sheet["H14"].value
    assert workbook["README"]["B16"].value == "CHECK"
    assert workbook["판관비_검증"]["I5"].value == "판매효과"
