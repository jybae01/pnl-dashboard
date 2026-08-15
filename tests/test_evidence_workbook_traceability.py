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
            after = {
                base_path: sha256(base_path.read_bytes()).hexdigest(),
                comparison_path: sha256(comparison_path.read_bytes()).hexdigest(),
            }

        self.assertEqual(before, after)
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
        self.assertEqual(
            sales[f"B{_row_with_value(sales, 'A', 'Freight double count')}"].value[:4],
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

        manufacturing = workbook["제조경비_근거"]
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
        self.assertEqual(manufacturing["L4"].value, "Scenario")
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
                f"B{_row_with_value(manufacturing, 'A', 'Inventory realization multiplier used')}"
            ].value,
            "=FALSE",
        )

        inventory = workbook["재고원가반영시차_근거"]
        self.assertEqual(inventory["D12"].value, "=D10-D11")
        self.assertIn("Data!E325", inventory["G8"].value)
        self.assertEqual(workbook["상품원가검증"]["B9"].value[:4], "=IF(")
        sga = workbook["판관비_검증"]
        self.assertEqual(sga["L5"].value, "SOURCE_MAPPED")

        bridge = workbook["최종Bridge_검증"]
        for code in (
            "sales_quantity", "sales_mix", "sales_price", "sales_fx", "tariff",
            "material_total", "manufacturing_realized", "inventory_timing",
            "sga_variable", "sga_fixed",
        ):
            row = _row_with_value(bridge, "A", code)
            self.assertTrue(bridge[f"C{row}"].value.startswith("='"))
            self.assertNotEqual(bridge[f"C{row}"].value, f"=D{row}")
        identity_row = _row_with_value(bridge, "B", "effects_total + residual = OP_delta")
        self.assertTrue(bridge[f"C{identity_row}"].value.startswith("="))
        self.assertTrue(bridge[f"F{identity_row}"].value.startswith("=IF("))
        self.assertEqual(
            bridge[f"B{_row_with_value(bridge, 'A', 'Current Cost Basis Gap 신규 Effect 아님')}"].value[:4],
            "=IF(",
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
