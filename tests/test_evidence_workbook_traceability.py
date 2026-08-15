from __future__ import annotations

from dataclasses import asdict
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import tempfile
import unittest

from openpyxl import load_workbook

from forecast.analysis_export import build_comparison_audit_workbook
from forecast.comparison import GenericComparisonEngine, PeriodOption

try:
    from tests.test_golden_analysis_adapter import _build_workbook, _meta
except ModuleNotFoundError:
    from test_golden_analysis_adapter import _build_workbook, _meta


ROOT = Path(__file__).resolve().parents[1]


def _row_with_value(ws, column: str, value: object) -> int:
    return next(
        row for row in range(1, ws.max_row + 1)
        if ws[f"{column}{row}"].value == value
    )


class EvidenceWorkbookTraceabilityTests(unittest.TestCase):
    def test_real_golden_adapter_trace_reaches_formula_workbook_without_source_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base_path = root / "base.xlsx"
            comparison_path = root / "comparison.xlsx"
            _build_workbook(base_path)
            _build_workbook(comparison_path, comparison=True)
            before = {
                base_path: sha256(base_path.read_bytes()).hexdigest(),
                comparison_path: sha256(comparison_path.read_bytes()).hexdigest(),
            }
            result = GenericComparisonEngine(ROOT / "config" / "model_mapping.json").compare(
                _meta("base"),
                base_path,
                _meta("comparison"),
                comparison_path,
                PeriodOption("M01", "1월", (1,), "월"),
                baseline_sales_fx=1_000,
                comparison_sales_fx=1_100,
            )
            payload = build_comparison_audit_workbook(
                result=asdict(result),
                sales_rows=result.sales_analysis["rows"],
                sales_totals=result.sales_analysis["totals"],
                baseline_fx=1_000,
                comparison_fx=1_100,
                baseline_path=base_path,
                comparison_path=comparison_path,
                mapping_path=ROOT / "config" / "model_mapping.json",
            )
            stored_payload = build_comparison_audit_workbook(
                result=asdict(result),
                sales_rows=result.sales_analysis["rows"],
                sales_totals=result.sales_analysis["totals"],
                baseline_fx=1_000,
                comparison_fx=1_100,
                mapping_path=ROOT / "config" / "model_mapping.json",
            )
            after = {
                base_path: sha256(base_path.read_bytes()).hexdigest(),
                comparison_path: sha256(comparison_path.read_bytes()).hexdigest(),
            }

        self.assertEqual(before, after)
        stored = load_workbook(BytesIO(stored_payload), data_only=False)
        stored_trace = stored["원천셀_추적"]
        raw_header = next(
            row for row in range(1, stored_trace.max_row + 1)
            if stored_trace[f"A{row}"].value == "Domain"
        )
        self.assertGreater(stored_trace.max_row, raw_header)
        self.assertIn("SALES", {
            stored_trace[f"A{row}"].value
            for row in range(raw_header + 1, stored_trace.max_row + 1)
        })
        self.assertTrue(all(
            not (isinstance(stored_trace[f"I{row}"].value, str) and stored_trace[f"I{row}"].value.startswith("="))
            for row in range(raw_header + 1, stored_trace.max_row + 1)
        ))
        workbook = load_workbook(BytesIO(payload), data_only=False)
        self.assertEqual(
            workbook.sheetnames[:6],
            [
                "README", "판매효과_근거", "원부재료_근거", "제조경비_근거",
                "재고원가반영시차_근거", "상품원가검증",
            ],
        )

        sales = workbook["판매효과_근거"]
        self.assertIn("Data!E", sales["G5"].value)
        self.assertIn(sales["B5"].value, {"PCS", "LENGTH"})
        self.assertTrue(sales["O5"].value.startswith("=IFERROR("))
        scope = workbook["Sales_COGS_Scope"]
        self.assertEqual(scope["A1"].value, "Sales/Product COGS ↔ P&L Manufactured COGS Source Scope")
        self.assertTrue(any(
            isinstance(cell.value, str) and cell.value.startswith("=")
            for row in scope.iter_rows()
            for cell in row
        ))
        quantity_row = _row_with_value(sales, "A", "sales_quantity")
        mix_row = _row_with_value(sales, "A", "sales_mix")
        price_row = _row_with_value(sales, "A", "sales_price")
        freight_row = _row_with_value(sales, "A", "freight_adjustment")
        self.assertIn("SUM(M", sales[f"B{quantity_row}"].value)
        self.assertIn("SUM(P", sales[f"B{mix_row}"].value)
        self.assertEqual(
            sales[f"B{price_row}"].value,
            f"=B{price_row - 2}+B{freight_row}",
        )
        self.assertEqual(sales[f"E{freight_row}"].value, "Price에 1회 포함")
        self.assertEqual(sales["BE5"].value, "DIRECT_AMOUNT_NO_DENOMINATOR")
        self.assertTrue(sales.column_dimensions["BE"].hidden)
        self.assertTrue(sales["BF5"].value.startswith("=IF("))
        self.assertIn("적용 불가", sales["BF5"].value)
        self.assertEqual(sales["BJ5"].value, "=BH5+BI5")
        self.assertEqual(sales["BK5"].value, "=BJ5")
        self.assertTrue(sales["BL5"].value.startswith("=IF("))
        self.assertEqual(sales["E4"].value, "원천 항목")
        self.assertEqual(sales["B4"].value, "수량 Pool")
        self.assertEqual(sales["AM4"].value, "기준 운반비(관세 포함)")
        self.assertEqual(sales["AN4"].value, "비교 운반비(관세 포함)")
        self.assertEqual(sales["AS4"].value, "기준 운반비(관세 제외)")
        self.assertEqual(sales["AT4"].value, "비교 운반비(관세 제외)")
        self.assertIn("배부 기준 원천이 없어", sales["AI2"].value)
        self.assertTrue(sales.column_dimensions["E"].hidden)
        self.assertGreaterEqual(float(sales.column_dimensions["B"].width), 18)
        self.assertGreaterEqual(float(sales.column_dimensions["C"].width), 18)
        self.assertLessEqual(max(
            dimension.width or 0
            for dimension in sales.column_dimensions.values()
            if not dimension.hidden
        ), 28)
        self.assertEqual(sales.page_setup.fitToWidth, 2)
        self.assertEqual(
            sales[f"B{_row_with_value(sales, 'A', '운반비 중복계상 없음')}"].value[:4],
            "=IF(",
        )

        material = workbook["원부재료_근거"]
        self.assertIn("Data!E", material["F5"].value)
        lc_row = _row_with_value(material, "B", "LC")
        self.assertEqual(material[f"C{lc_row}"].value, "PCS (4-inch)")
        self.assertTrue(material["O5"].value.startswith("=IF("))
        self.assertEqual(material["R5"].value, "SOURCE_MAPPED")
        self.assertEqual(material["AG5"].value, "=IFERROR(Z5/AB5,0)")
        self.assertEqual(material["AH5"].value, "=(AF5-AG5)*AC5")
        material_total_row = _row_with_value(material, "A", "material_total")
        jpy_row = _row_with_value(material, "A", "nonwoven_jpy")
        self.assertIn("SUM(O", material[f"B{material_total_row}"].value)
        self.assertIn("SUM(AJ", material[f"B{jpy_row}"].value)
        self.assertTrue(material[f"B{_row_with_value(material, 'A', 'JPY 원천 유효')}"].value.startswith("=IF("))
        self.assertTrue(material[f"B{_row_with_value(material, 'A', '판매수량 원천 유효')}"].value.startswith("=IF("))
        self.assertGreaterEqual(float(material.column_dimensions["B"].width), 18)
        self.assertGreaterEqual(float(material.column_dimensions["C"].width), 18)

        manufacturing = workbook["제조경비_근거"]
        reconciliation = result.manufacturing_analysis["production_reconciliation"]
        production_period = str(reconciliation[0]["month"])
        production_row = _row_with_value(manufacturing, "A", production_period)
        for scenario, front_column, back_column in (
            ("base", "B", "E"), ("comparison", "C", "F"),
        ):
            selected = [item for item in reconciliation if item["scenario"] == scenario and str(item["month"]) == production_period]
            self.assertAlmostEqual(
                manufacturing[f"{front_column}{production_row}"].value,
                sum(float(item.get("sap_length") or 0) for item in selected if item["product_group"] == "FS"),
            )
            self.assertAlmostEqual(
                manufacturing[f"{back_column}{production_row}"].value,
                sum(float(item.get("sap_qty") or 0) for item in selected if item["product_group"] in {"SW", "BW", "LC"}),
            )
        self.assertEqual(manufacturing[f"J{production_row}"].value, "=FALSE")
        self.assertIn("Front:", manufacturing[f"H{production_row}"].value)
        self.assertIn("Back:", manufacturing[f"H{production_row}"].value)
        self.assertIn("Front:", manufacturing[f"I{production_row}"].value)
        self.assertIn("Back:", manufacturing[f"I{production_row}"].value)
        detail_row = _row_with_value(manufacturing, "B", "수도광열비")
        self.assertEqual(manufacturing[f"I{detail_row}"].value, "LENGTH(m)")
        self.assertEqual(
            manufacturing[f"J{detail_row}"].value,
            "PCS (LC=4-inch 포함)",
        )
        self.assertTrue(manufacturing[f"O{detail_row}"].value.startswith("="))
        self.assertTrue(manufacturing[f"AC{detail_row}"].value.startswith("="))
        self.assertTrue(manufacturing[f"AG{detail_row}"].value.startswith("="))
        self.assertTrue(manufacturing[f"AI{detail_row}"].value.startswith("="))
        self.assertEqual(manufacturing["L4"].value, "구분")
        reconciliation_row = _row_with_value(manufacturing, "N", "SW")
        self.assertIn(manufacturing[f"L{reconciliation_row}"].value, {"base", "comparison"})
        self.assertIsInstance(manufacturing[f"O{reconciliation_row}"].value, (int, float))
        self.assertIsNone(manufacturing[f"P{reconciliation_row}"].value)
        self.assertIsNone(manufacturing[f"Q{reconciliation_row}"].value)
        # Engine fallback for a zero production denominator assigns Volume=0
        # and the allocated-cost delta to Unit; the workbook formulas mirror it.
        self.assertIn("OR(S", manufacturing[f"AA{detail_row}"].value)
        self.assertIn(",0,", manufacturing[f"AA{detail_row}"].value)
        self.assertIn(f"O{detail_row}-P{detail_row}", manufacturing[f"AE{detail_row}"].value)
        self.assertEqual(
            manufacturing[
                f"B{_row_with_value(manufacturing, 'A', '재고실현율 계산 반영 여부')}"
            ].value,
            "=FALSE",
        )
        self.assertTrue(manufacturing.column_dimensions["D"].hidden)
        self.assertEqual(manufacturing.page_setup.fitToWidth, 1)

        inventory = workbook["재고원가반영시차_근거"]
        self.assertEqual(inventory["A5"].value, "제품 매출원가")
        self.assertEqual(inventory["A12"].value, "중복 제거 전 재고·원가 반영시차")
        self.assertEqual(inventory["D12"].value, "=D10-D11")
        self.assertEqual(inventory["D12"].number_format, '#,##0;[Red](#,##0);-')
        self.assertEqual(inventory["D15"].value, "=D13+D14")
        self.assertEqual(inventory["D16"].value, "=D12-D15")
        self.assertTrue(inventory["F17"].value.startswith("=IF("))
        paid_supply_row = _row_with_value(inventory, "A", "CURRENT_COST_ROW_323_PAID_SUPPLY")
        self.assertEqual(inventory[f"B{paid_supply_row}"].value, "=FALSE")
        self.assertIn("계획 대응금액", inventory[f"C{paid_supply_row}"].value)
        audit = workbook["Evidence_Audit"]
        self.assertEqual(audit["B8"].value, 0)
        self.assertEqual(audit["C8"].value, "PASS")
        self.assertEqual(audit["B9"].value, '=IF(B8=0,"PASS","FAIL")')
        self.assertTrue(any(
            cell.value == "수량에 포함된 COGS 비용"
            for row in inventory.iter_rows()
            for cell in row
        ))
        self.assertEqual(scope["J4"].value, "Net Inventory Timing")
        self.assertEqual(scope["J5"].value, "Gross Inventory Timing (before deduction)")
        self.assertEqual(scope["K5"].value, "=K4+H7")
        self.assertTrue(scope["K6"].value)
        self.assertIn("Data!E325", inventory["G8"].value)
        self.assertEqual(workbook["상품원가검증"]["B9"].value[:4], "=IF(")
        sga = workbook["판관비_검증"]
        self.assertEqual(sga["L5"].value, "SOURCE_MAPPED")

        bridge = workbook["최종Bridge_검증"]
        self.assertEqual(bridge["B4"].value, "효과")
        self.assertEqual(bridge["C4"].value, "근거 수식")
        self.assertTrue(bridge.column_dimensions["A"].hidden)
        self.assertEqual(bridge["B16"].value, "공식 효과 합계")
        self.assertEqual(bridge["B19"].value, "공식 효과 합계 + 잔여차이 = 영업이익 증감")
        for code in (
            "sales_quantity", "sales_mix", "sales_price", "sales_fx", "tariff",
            "material_total", "manufacturing_realized", "inventory_timing",
            "sga_variable", "sga_fixed",
        ):
            row = _row_with_value(bridge, "A", code)
            self.assertTrue(bridge[f"C{row}"].value.startswith("='"))
            self.assertNotEqual(bridge[f"C{row}"].value, f"=D{row}")
        identity_row = _row_with_value(
            bridge,
            "B",
            "공식 효과 합계 + 잔여차이 = 영업이익 증감",
        )
        self.assertTrue(bridge[f"C{identity_row}"].value.startswith("="))
        self.assertTrue(bridge[f"F{identity_row}"].value.startswith("=IF("))
        self.assertEqual(
            bridge[f"B{_row_with_value(bridge, 'A', 'Current Cost Basis Gap 신규 Effect 아님')}"].value[:4],
            "=IF(",
        )
        inventory_bridge_row = _row_with_value(bridge, "A", "inventory_timing")
        self.assertEqual(
            bridge[f"C{inventory_bridge_row}"].value,
            "='재고원가반영시차_근거'!D16",
        )
        self.assertEqual(
            sum(
                1
                for row in range(1, bridge.max_row + 1)
                if bridge[f"A{row}"].value == "inventory_timing"
            ),
            1,
        )

        residual_rca = workbook["Residual_RCA"]
        self.assertEqual(residual_rca["F6"].value, "=B6-C6-D6-E6")
        self.assertEqual(residual_rca["F7"].value, "=B7-C7-D7-E7")
        self.assertEqual(residual_rca["F8"].value, "=F7-F6")
        self.assertTrue(residual_rca["G8"].value.startswith("='최종Bridge_검증'!"))
        sales_map_row = _row_with_value(residual_rca, "A", "sales_quantity")
        self.assertEqual(residual_rca[f"B{sales_map_row}"].value, "SALES_REVENUE")
        self.assertEqual(residual_rca[f"C{sales_map_row}"].value, "YES")
        mcm_map_row = _row_with_value(residual_rca, "A", "mcm_policy")
        self.assertEqual(residual_rca[f"C{mcm_map_row}"].value, "NO")
        self.assertEqual(residual_rca[f"E{mcm_map_row}"].value, "NO")
        sales_bucket_row = _row_with_value(residual_rca, "A", "SALES_REVENUE")
        self.assertEqual(residual_rca[f"D{sales_bucket_row}"].value, f"=C{sales_bucket_row}-B{sales_bucket_row}")
        self.assertTrue(residual_rca[f"F{sales_bucket_row}"].value.startswith("=SUMIFS("))
        basis_row = next(
            row for row in range(1, residual_rca.max_row + 1)
            if str(residual_rca[f"A{row}"].value or "").startswith(
                "current_cost_formula_scope_difference"
            )
        )
        self.assertEqual(
            residual_rca[f"D{basis_row}"].value,
            "FORMULA_BASIS_DIFFERENCE",
        )
        self.assertIn("Data!E321", residual_rca[f"H{basis_row}"].value)
        unexplained_row = _row_with_value(residual_rca, "D", "UNEXPLAINED")
        self.assertEqual(residual_rca[f"A{unexplained_row}"].value, "unexplained")
        classified_row = _row_with_value(residual_rca, "B", "Classified Total")
        existing_row = _row_with_value(residual_rca, "B", "Existing Residual")
        waterfall_row = _row_with_value(
            residual_rca, "B", "Σ Residual Components = Existing Residual"
        )
        self.assertTrue(residual_rca[f"C{classified_row}"].value.startswith("=SUM("))
        self.assertTrue(
            residual_rca[f"C{existing_row}"].value.startswith("='최종Bridge_검증'!")
        )
        self.assertTrue(residual_rca[f"C{waterfall_row}"].value.startswith("=IF("))
        self.assertTrue(
            residual_rca[
                f"B{_row_with_value(residual_rca, 'A', 'MCM 독립 Effect 아님')}"
            ].value.startswith("=IF(")
        )
        self.assertIsNotNone(_row_with_value(residual_rca, "A", "운반비"))

        overlap = workbook["Sales_COGS_Basis"]
        self.assertEqual(overlap["M10"].value, "=IFERROR(I10/E10,0)")
        self.assertEqual(overlap["N10"].value, "=IFERROR(K10/E10,0)")
        self.assertEqual(overlap["O10"].value, "=M10-N10")
        self.assertEqual(overlap["T10"].value, "=R10-S10")
        self.assertEqual(overlap["W10"].value, "=U10-V10")
        self.assertEqual(overlap["X10"].value, "=T10+W10")
        self.assertEqual(overlap["Y10"].value, "=-X10")
        self.assertEqual(overlap["H4"].value[:5], "=SUM(")
        self.assertEqual(overlap["H5"].value, "=-H4")
        self.assertEqual(overlap["K5"].value, "=IFERROR(ABS(H4)/ABS(K4),0)")
        self.assertEqual(overlap["K6"].value, "=K4-H4")
        self.assertTrue(overlap["H7"].value)
        self.assertFalse(any(
            overlap[f"D{row}"].value == "신사업"
            for row in range(10, overlap.max_row + 1)
        ))
        overlap_validation = _row_with_value(
            overlap, "A", "Revenue basis - GP basis = Embedded COGS"
        )
        self.assertTrue(overlap[f"B{overlap_validation}"].value.startswith("=IF("))
        option_a_row = next(
            row for row in range(1, overlap.max_row + 1)
            if overlap[f"B{row}"].value == "OPTION_A"
        )
        option_b_row = next(
            row for row in range(1, overlap.max_row + 1)
            if overlap[f"B{row}"].value == "OPTION_B"
        )
        self.assertTrue(overlap[f"F{option_a_row}"].value.startswith("=F"))
        self.assertTrue(overlap[f"C{option_b_row}"].value.startswith("=SUMIFS("))
        self.assertTrue(overlap[f"L{option_a_row}"].value.startswith("=IF("))
        cumulative_current_row = next(
            row for row in range(1, overlap.max_row + 1)
            if overlap[f"B{row}"].value == "CURRENT"
            and overlap[f"A{row}"].value == result.sales_cogs_basis_analysis["period"]
        )
        self.assertIsInstance(overlap[f"N{cumulative_current_row}"].value, (int, float))
        lc_scope_validation = _row_with_value(
            overlap, "A", "LC manufactured/total source mismatch disclosed"
        )
        self.assertTrue(overlap[f"B{lc_scope_validation}"].value.startswith("=IF("))

        scope_policy_row = _row_with_value(
            scope, "A", "Core overlap Production policy applied"
        )
        self.assertEqual(scope[f"B{scope_policy_row}"].value, "=IF(K6=TRUE,0,1)")

        errors = []
        for ws in workbook.worksheets:
            for row in ws.iter_rows():
                for cell in row:
                    value = cell.value
                    if isinstance(value, str) and value.startswith("="):
                        for token in (
                            "#REF!", "#DIV/0!", "#VALUE!", "#NAME?", "#N/A", "#NUM!",
                            "#NULL!", "#SPILL!", "#CALC!",
                        ):
                            if token in value.upper():
                                errors.append(f"{ws.title}!{cell.coordinate}:{token}")
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
