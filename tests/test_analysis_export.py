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
                "current_manufacturing_cost_components": {
                    "raw_material_production_issue": {"row": 321, "business_source": "원부재료비(생산출고)"},
                    "raw_material_tariff_refund": {"row": 322, "business_source": "원재료 관세환급액"},
                    "paid_supply": {"row": 323, "business_source": "유상사급"},
                    "labor": {"row": 289, "business_source": "노무비"},
                    "manufacturing_expense": {"row": 296, "business_source": "제조경비"},
                },
                "current_manufacturing_cost_formula_relationships": {
                    "manufacturing_processing_total": {"row": 319},
                    "raw_material_total": {"row": 324},
                    "current_manufacturing_cost": {"row": 325},
                },
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
            "current_cost_component": "labor",
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
        "sga_accounts": [
            {
                "row": 1168, "section": "판매비", "account": "운반비",
                "classification": "transport", "baseline_amount": 10,
                "comparison_amount": 20, "delta": 10, "profit_effect": 0,
                "bridge_position": "판매효과",
            },
            {
                "row": 1169, "section": "판매비", "account": "관세",
                "classification": "tariff", "baseline_amount": 30,
                "comparison_amount": 45, "delta": 15, "profit_effect": 0,
                "bridge_position": "외부효과/관세",
            },
        ],
    }
    result["inventory_analysis"]["current_cost_basis_analysis"] = {
        "current_manufacturing_cost_effect": 40,
        "raw_material_effect": -200,
        "manufacturing_activity_effect": 4,
        "manufacturing_unit_effect": 6,
        "manufacturing_fixed_effect": 0,
        "manufacturing_effect": 10,
        "existing_current_cost_driver_subtotal": -190,
        "basis_gap": 230,
        "raw_material_basis_gap": 230,
        "manufacturing_basis_gap": 0,
        "status": "CHECK_SCOPE_GAP",
        "architecture_decision": "OPTION_C",
        "architecture_rationale": "Manufacturing direct tie; raw-material driver basis differs.",
        "component_details": [
            {"component_code": "raw_material_production_issue", "business_source": "원부재료비(생산출고)", "base": 100, "comparison": 70, "gap": 230, "validation_status": "CHECK_SCOPE_GAP", "reason": "Driver basis differs", "formula_basis": "unit cost x comparison sales", "source_coverage": "AGGREGATE_DRIVER_ONLY", "base_source_reference": "Data!E321", "comparison_source_reference": "Data!E321", "base_source_formula": "=E211+E699", "comparison_source_formula": "=E211+E699"},
            {"component_code": "raw_material_tariff_refund", "business_source": "원재료 관세환급액", "base": 0, "comparison": 0, "gap": 0, "validation_status": "PASS", "reason": "Excluded adjustment", "formula_basis": "excluded", "source_coverage": "FULL_DIRECT_SOURCE_EXCLUDED_FROM_DRIVER", "base_source_reference": "Data!E322", "comparison_source_reference": "Data!E322"},
            {"component_code": "paid_supply", "business_source": "유상사급", "base": 0, "comparison": 0, "gap": 0, "validation_status": "PASS", "reason": "No direct driver mapping", "formula_basis": "excluded", "source_coverage": "FULL_DIRECT_SOURCE_EXCLUDED_FROM_DRIVER", "base_source_reference": "Data!E323", "comparison_source_reference": "Data!E323"},
            {"component_code": "labor", "business_source": "노무비", "base": 100, "comparison": 90, "gap": 0, "validation_status": "PASS", "reason": "Direct tie", "formula_basis": "activity+unit+fixed", "source_coverage": "FULL", "base_source_reference": "Data!E289", "comparison_source_reference": "Data!E289"},
            {"component_code": "manufacturing_expense", "business_source": "제조경비", "base": 0, "comparison": 0, "gap": 0, "validation_status": "PASS", "reason": "Direct tie", "formula_basis": "activity+unit+fixed", "source_coverage": "FULL", "base_source_reference": "Data!E296", "comparison_source_reference": "Data!E296"},
        ],
        "aggregate_details": [
            {"component_code": "raw_material_total", "business_source": "원재료비 계", "gap": 230},
            {"component_code": "manufacturing_processing_total", "business_source": "제조 가공비 합계", "gap": 0},
            {"component_code": "current_manufacturing_cost", "business_source": "당기투입제조원가", "gap": 230},
        ],
        "manufacturing_driver_details": [
            {"business_source": "노무비", "base": 100, "comparison": 90, "activity_effect": 4, "unit_effect": 6, "fixed_effect": 0, "reason": "Direct tie"},
            {"business_source": "외주가공비", "base": 0, "comparison": 0, "activity_effect": 0, "unit_effect": 0, "fixed_effect": 0, "reason": "Direct tie"},
            {"business_source": "기타 제조경비", "base": 0, "comparison": 0, "activity_effect": 0, "unit_effect": 0, "fixed_effect": 0, "reason": "Direct tie"},
        ],
        "gap_classification": [
            {"classification": "formula_scope_difference", "business_source": "원부재료비", "amount": 230, "source_coverage": "AGGREGATE_DRIVER_ONLY", "reason": "Driver basis differs"},
            {"classification": "UNEXPLAINED", "business_source": "Unmapped remainder", "amount": 0, "source_coverage": "NOT_APPLICABLE", "reason": "No remainder"},
        ],
        "residual": -60,
        "residual_basis_gap_link": 230,
        "residual_remainder": -290,
        "plug_created": False,
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
    assert {
        "판매효과_근거", "원부재료_근거", "제조경비_근거",
        "재고원가반영시차_근거", "상품원가검증", "최종Bridge_검증",
    } <= set(workbook.sheetnames)
    assert workbook["판매효과_근거"]["O5"].value.startswith("=")
    assert workbook["판매효과_근거"]["AM5"].value == 30_000_000.0
    assert workbook["판매효과_근거"]["AN5"].value == 40_000_000.0
    assert workbook["판매효과_근거"]["AS5"].value == "=AM5-AO5*AQ5"
    assert workbook["판매효과_근거"]["BC5"].value == "45m/PCS"
    assert workbook["판매효과_근거"]["BD5"].value == "=BA5/45"
    assert workbook["판매효과_근거"]["BF5"].value == "=AU5+AW5+AY5+BD5"
    assert workbook["판매효과_근거"]["BJ5"].value == "=(BH5-BI5)*BG5"
    assert workbook["판매효과_근거"]["BK5"].value == -10_000_000.0
    assert workbook["판매효과_근거"]["BO5"].value.startswith("=IF(")
    assert "재계산 필요" in workbook["판매효과_근거"]["AJ5"].value
    assert workbook["원천셀_추적"].max_row > 4
    trace_cells = {
        cell.value
        for row in workbook["원천셀_추적"].iter_rows()
        for cell in row
        if isinstance(cell.value, str) and cell.value.startswith("E")
    }
    assert {"E9", "E205", "E211", "E289", "E296", "E319", "E321", "E322", "E323", "E324", "E325", "E1269", "E1280", "E684", "E699", "E345", "E347"} <= trace_cells
    assert all(
        not (isinstance(cell.value, str) and cell.value.startswith("="))
        for cell in workbook["원천셀_추적"]["J"]
    )
    assert workbook["README"]["B15"].value == "PASS"
    assert "44444444-4444-4444-8444-444444444444" in {
        cell.value for row in workbook["README"].iter_rows() for cell in row
    }
    material_text = " ".join(
        str(cell.value or "") for row in workbook["원부재료_근거"].iter_rows() for cell in row
    )
    assert "MCM SW400" not in material_text
    assert workbook["원부재료_근거"]["O5"].value.startswith("=IF(")
    manufacturing_sheet = workbook["제조경비_근거"]
    manufacturing_detail_row = next(
        row for row in range(1, manufacturing_sheet.max_row + 1)
        if manufacturing_sheet[f"B{row}"].value == "수도광열비"
    )
    assert manufacturing_sheet[f"AK{manufacturing_detail_row}"].value.startswith("=")
    assert manufacturing_sheet[f"H{manufacturing_detail_row}"].value == "Data row 347"
    assert manufacturing_sheet[f"AO{manufacturing_detail_row}"].value == "labor"
    basis_sheet = workbook["당기제조원가_기준차이"]
    assert basis_sheet["C5"].value == "=D25"
    assert "원부재료_근거" in basis_sheet["C6"].value
    assert basis_sheet["C12"].value == "=C5-C11"
    assert basis_sheet["D16"].value == "=B16-C16"
    assert basis_sheet["E16"].value == "=C6"
    assert basis_sheet["F16"].value == "=D16-E16"
    assert "SUMIF" in basis_sheet["E19"].value
    inventory_sheet = workbook["재고원가반영시차_근거"]
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
    assert inventory_sheet[f"I{first_rolling_row}"].value == "=0"
    assert "Data!C1269" in inventory_sheet[f"Q{first_rolling_row}"].value
    reconciliation_sheet = workbook["최종Bridge_검증"]
    inventory_bridge_row = next(
        row
        for row in range(5, reconciliation_sheet.max_row + 1)
        if reconciliation_sheet[f"A{row}"].value == "inventory_timing"
    )
    assert reconciliation_sheet[f"C{inventory_bridge_row}"].value == "='재고원가반영시차_근거'!D16"
    identity_row = next(
        row for row in range(1, reconciliation_sheet.max_row + 1)
        if reconciliation_sheet[f"B{row}"].value == "공식 효과 합계 + 잔여차이 = 영업이익 증감"
    )
    assert reconciliation_sheet[f"C{identity_row}"].value.startswith("=")
    assert reconciliation_sheet[f"F{identity_row}"].value.startswith("=IF(")
    assert workbook["README"]["B16"].value == "CHECK"
    assert workbook["판관비_검증"]["I5"].value == "판매효과"
    assert workbook["판관비_검증"]["I6"].value == "외부효과/관세"
    assert 'OR(I6="판매효과",I6="외부효과/관세")' in workbook["판관비_검증"]["G6"].value
    assert workbook["판관비_검증"]["H6"].value == 0.0
