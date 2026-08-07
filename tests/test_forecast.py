from __future__ import annotations

import tempfile
import unittest
import zipfile
from datetime import date
from pathlib import Path
from xml.etree import ElementTree as ET

from forecast.comparison import GenericComparisonEngine, PeriodOption
from forecast.baseline import inspect_baseline_workbook
from forecast.engine import CostAdjustment, ForecastEngine, ForecastInput, SalesInput
from forecast.sales_comparison import calculate_sales_effect_rows, sales_effect_totals
from forecast.storage import BaselineStore, ModelMeta, ModelRegistry
from forecast.workbook import GoldenWorkbook

ROOT = Path(__file__).resolve().parents[1]


class GoldenModelTests(unittest.TestCase):
    def setUp(self):
        self.model = ROOT / "models" / "golden_model.xlsx"
        self.mapping = ROOT / "config" / "model_mapping.json"

    def test_formula_evaluator_matches_cached_key_outputs(self):
        wb = GoldenWorkbook(self.model)
        for addr in [
            "K1168", "K1194", "K1248", "K1268", "K1298", "K1302",
            "K1303", "K1306", "K936", "K211", "K699", "K1594", "K1595",
        ]:
            cached = float(wb.raw_value(addr) or 0)
            calculated = float(wb.value(addr) or 0)
            self.assertAlmostEqual(cached, calculated, delta=max(1.0, abs(cached)*1e-9), msg=addr)

    def test_forecast_produces_valid_workbook_and_protects_formulas(self):
        sales={key:SalesInput() for key in ["SW400","SW440","BW400","BW440","LC","FS_SW","FS_BW","FS_TW","UF_MBR","IX","OTHER"]}
        production={key:0 for key in ["SW400","SW440","BW400","BW440","LC","FS_SW","FS_BW","FS_TW"]}
        with tempfile.TemporaryDirectory() as directory:
            output=Path(directory)/"forecast.xlsx"
            result=ForecastEngine(self.model,self.mapping).run(ForecastInput(month=7,sales=sales,production=production),output)
            self.assertTrue(output.exists())
            self.assertTrue(zipfile.is_zipfile(output))
            self.assertTrue(next(item for item in result.validations if item["name"]=="수식 보호")["ok"])
            self.assertTrue(next(item for item in result.validations if item["name"]=="영업이익 정합성")["ok"])
            downloaded = GoldenWorkbook(output)
            self.assertEqual(downloaded.raw_value("K3"), "추정")
            self.assertEqual(downloaded.raw_value("L3"), "계획")
            with zipfile.ZipFile(output) as archive:
                namespace = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
                styles_xml = archive.read("xl/styles.xml")
                self.assertIn(b'xmlns:x16r2=', styles_xml)
                workbook_xml = ET.fromstring(archive.read("xl/workbook.xml"))
                sheets = workbook_xml.find("m:sheets", namespace)
                sheet_names = [item.attrib["name"] for item in sheets]
                self.assertEqual(sheet_names[sheet_names.index("Data") + 1], "입력반영내역")
                audit_sheet = ET.fromstring(archive.read("xl/worksheets/sheet2.xml"))
                locations = {
                    item.attrib.get("location")
                    for item in audit_sheet.findall(".//m:hyperlink", namespace)
                }
                self.assertIn("'Data'!K32", locations)
                self.assertIn("'Data'!K1289", locations)
                self.assertNotIn("'Data'!K1168", locations)
            second_output = Path(directory) / "forecast_2.xlsx"
            ForecastEngine(output, self.mapping).run(
                ForecastInput(month=8, sales=sales, production=production), second_output,
            )
            chained = GoldenWorkbook(second_output)
            self.assertEqual(chained.raw_value("K3"), "추정")
            self.assertEqual(chained.raw_value("L3"), "추정")
            self.assertEqual(chained.raw_value("M3"), "계획")
            with zipfile.ZipFile(second_output) as archive:
                audit_sheet = ET.fromstring(archive.read("xl/worksheets/sheet2.xml"))
                locations = {
                    item.attrib.get("location")
                    for item in audit_sheet.findall(".//m:hyperlink", namespace)
                }
                self.assertIn("'Data'!K32", locations)
                self.assertIn("'Data'!L32", locations)

    def test_actual_month_in_baseline_is_locked(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "locked.xlsx"
            with self.assertRaisesRegex(ValueError, "실적으로 확정"):
                ForecastEngine(self.model, self.mapping).run(
                ForecastInput(month=6), output,
                )

    def test_unchanged_direct_input_is_not_included_in_audit(self):
        workbook = GoldenWorkbook(self.model)
        original = workbook.value("K32")
        workbook.set_input("K32", original, "sales.SW400.quantity")
        self.assertEqual(workbook._direct_input_changes(), set())
        self.assertEqual(workbook._direct_input_logs(), [])

    def test_download_fallback_restores_audit_sheet_from_saved_input_log(self):
        with tempfile.TemporaryDirectory() as directory:
            legacy_output = Path(directory) / "legacy_output.xlsx"
            workbook = GoldenWorkbook(self.model)
            workbook.set_text("K3", "추정", "forecast.period_type")
            workbook.save(legacy_output)
            legacy = GoldenWorkbook(legacy_output)
            self.assertEqual(legacy.audit_entry_count(), 0)
            legacy.restore_audit_logs([{
                "cell": "K32",
                "old_value": 100,
                "new_value": 120,
                "source": "sales.SW400.quantity",
                "reason": "",
                "formula_overwritten": False,
            }])
            restored_output = Path(directory) / "restored_output.xlsx"
            legacy.save(restored_output)
            restored = GoldenWorkbook(restored_output)
            self.assertEqual(restored.audit_entry_count(), 1)

    def test_baseline_store_preserves_actual_cutoff_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            store = BaselineStore(directory)
            meta = store.activate(
                self.model.read_bytes(),
                name="6월 실적 기준",
                file_name="baseline.xlsx",
                year=2026,
                actual_through_month=6,
                version="V2",
            )
            loaded = store.load()
            self.assertTrue(store.workbook_file.exists())
            self.assertEqual(meta.actual_through_month, 6)
            self.assertEqual(loaded.actual_through_month, 6)
            self.assertEqual(loaded.version, "V2")
            actual_through, statuses = inspect_baseline_workbook(store.workbook_file)
            self.assertEqual(actual_through, 6)
            self.assertEqual(statuses[:6], ["실적"] * 6)

    def test_generic_comparison_reconciles_and_uses_comparison_minus_baseline(self):
        meta1 = ModelMeta("base", "기준", "계획", 2026, 1, 12, "2026-01-01", "V1", True, "base.xlsx", "2026-01-01T00:00:00+09:00")
        meta2 = ModelMeta("target", "비교", "추정", 2026, 1, 12, "2026-07-01", "V2", False, "target.xlsx", "2026-07-01T00:00:00+09:00")
        engine = GenericComparisonEngine(self.mapping)
        period = next(item for item in engine.available_periods(meta1, meta2) if item.key == "M07")
        sales={key:SalesInput() for key in ["SW400","SW440","BW400","BW440","LC","FS_SW","FS_BW","FS_TW","UF_MBR","IX","OTHER"]}
        production={key:0 for key in ["SW400","SW440","BW400","BW440","LC","FS_SW","FS_BW","FS_TW"]}
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "target.xlsx"
            forecast = ForecastEngine(self.model,self.mapping).run(ForecastInput(month=7,sales=sales,production=production),target)
            result = engine.compare(meta1, self.model, meta2, target, period)
            baseline_op = GoldenWorkbook(self.model).value("K1306")
            self.assertAlmostEqual(result.operating_profit_delta, forecast.operating_profit - baseline_op, delta=1.0)
            self.assertTrue(result.reconciled)
            self.assertAlmostEqual(result.residual, 0.0, delta=1.0)

    def test_comparison_accepts_arbitrary_common_start_end_range(self):
        baseline = ModelMeta("base", "기준", "계획", 2026, 1, 12, "2026-01-01", "V1", True,
            "base.xlsx", "2026-01-01T00:00:00+09:00")
        comparison = ModelMeta("target", "비교", "추정", 2026, 7, 12, "2026-07-01", "V1", True,
            "target.xlsx", "2026-07-01T00:00:00+09:00")
        period = PeriodOption("R2026_07_09", "7~9월", (7, 8, 9), "선택기간")
        result = GenericComparisonEngine(self.mapping).compare(
            baseline, self.model, comparison, self.model, period,
        )
        self.assertEqual(result.period["months"], (7, 8, 9))
        self.assertTrue(result.reconciled)

    def test_comparison_extracts_golden_model_sales_group_profitability(self):
        baseline = ModelMeta("base", "기준", "계획", 2026, 1, 12, "2026-01-01", "V1", True,
            "base.xlsx", "2026-01-01T00:00:00+09:00")
        comparison = ModelMeta("target", "비교", "추정", 2026, 1, 12, "2026-07-01", "V1", True,
            "target.xlsx", "2026-07-01T00:00:00+09:00")
        engine = GenericComparisonEngine(self.mapping)
        period = next(item for item in engine.available_periods(baseline, comparison) if item.key == "M07")
        result = engine.compare(baseline, self.model, comparison, self.model, period)
        self.assertEqual(
            [row["product_group"] for row in result.sales_groups],
            ["SW", "BW", "LC", "FS", "신사업"],
        )
        workbook = GoldenWorkbook(self.model)
        sw = result.sales_groups[0]
        self.assertAlmostEqual(sw["baseline_amount"], workbook.value("K1594"), delta=1.0)
        expected_margin = (workbook.value("K1594") - workbook.value("K1595")) / workbook.value("K1594")
        self.assertAlmostEqual(sw["baseline_gross_margin_rate"], expected_margin, delta=1e-12)

    def test_sales_fx_input_reallocates_price_effect_without_changing_total(self):
        rows = [{
            "product_group": "SW",
            "baseline_quantity": 100,
            "baseline_amount": 100_000,
            "baseline_gross_margin_rate": 0.4,
            "comparison_quantity": 110,
            "comparison_amount": 121_000,
            "comparison_gross_margin_rate": 0.35,
        }]
        same_fx = calculate_sales_effect_rows(rows, 10.0, 10.0)[0]
        changed_fx = calculate_sales_effect_rows(rows, 10.0, 11.0)[0]
        self.assertAlmostEqual(same_fx.quantity_effect, 4_000.0)
        self.assertAlmostEqual(same_fx.pure_price_effect, 11_000.0)
        self.assertAlmostEqual(same_fx.sales_fx_effect, 0.0)
        self.assertAlmostEqual(changed_fx.pure_price_effect, 0.0, delta=1e-9)
        self.assertAlmostEqual(changed_fx.sales_fx_effect, 11_000.0, delta=1e-9)
        self.assertAlmostEqual(same_fx.unit_value_effect, changed_fx.unit_value_effect, delta=1e-9)
        totals = sales_effect_totals([changed_fx])
        self.assertAlmostEqual(totals["total_sales_effect"], 15_000.0, delta=1e-9)

    def test_model_registry_preserves_metadata_without_type_restrictions(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = ModelRegistry(directory)
            content = self.model.read_bytes()
            for model_type in ["계획", "실적", "추정"]:
                registry.add(content, name=f"{model_type} 모형", model_type=model_type, year=2026,
                    start_month=1, end_month=12, created_date=date.today().isoformat(), version="V1",
                    confirmed=model_type != "추정", file_name="model.xlsx")
            models = registry.list()
            self.assertEqual({item.model_type for item in models}, {"계획", "실적", "추정"})
            engine = GenericComparisonEngine(self.mapping)
            self.assertTrue(engine.available_periods(models[0], models[1]))

    def test_web_tariff_is_separate_and_reconciles_profit(self):
        baseline = ModelMeta("base", "기준", "계획", 2026, 1, 12, "2026-01-01", "V1", True,
            "base.xlsx", "2026-01-01T00:00:00+09:00")
        comparison = ModelMeta("target", "비교", "실적", 2026, 1, 12, "2026-07-01", "V1", True,
            "target.xlsx", "2026-07-01T00:00:00+09:00", {"7": 1000000}, 0.10, 0.13)
        engine = GenericComparisonEngine(self.mapping)
        period = next(item for item in engine.available_periods(baseline, comparison) if item.key == "M07")
        result = engine.compare(baseline, self.model, comparison, self.model, period)
        self.assertAlmostEqual(result.operating_profit_delta, -13000.0, delta=0.01)
        tariff = next(item for item in result.cost_summary if item["code"] == "tariff")
        self.assertAlmostEqual(tariff["delta"], 13000.0, delta=0.01)
        self.assertTrue(result.reconciled)

    def test_saved_forecast_uses_internal_tariff_adjustment_without_data_management_input(self):
        baseline = ModelMeta("base", "기준", "계획", 2026, 1, 12, "2026-01-01", "V1", True,
            "base.xlsx", "2026-01-01T00:00:00+09:00")
        comparison = ModelMeta("target", "비교", "추정", 2026, 1, 12, "2026-07-01", "V1", True,
            "target.xlsx", "2026-07-01T00:00:00+09:00", tariff_adjustment_monthly={"7": 6500})
        engine = GenericComparisonEngine(self.mapping)
        period = next(item for item in engine.available_periods(baseline, comparison) if item.key == "M07")
        result = engine.compare(baseline, self.model, comparison, self.model, period)
        self.assertAlmostEqual(result.operating_profit_delta, -6500.0, delta=0.01)
        self.assertTrue(result.reconciled)

    def test_forecast_keeps_reference_costs_manual_and_applies_cogs_adjustments(self):
        sales = {key: SalesInput() for key in [
            "SW400", "SW440", "BW400", "BW440", "LC", "FS_SW", "FS_BW", "FS_TW",
            "UF_MBR", "IX", "OTHER",
        ]}
        sales["UF_MBR"] = SalesInput(quantity=10, amount=1_000_000)
        sales["IX"] = SalesInput(quantity=250, amount=2_000_000)
        production = {key: 1_000 for key in [
            "SW400", "SW440", "BW400", "BW440", "LC", "FS_SW", "FS_BW", "FS_TW",
        ]}
        request = ForecastInput(
            month=7,
            sales=sales,
            production=production,
            plan_na_sa_sales=500_000,
            na_sa_sales=1_000_000,
            tariff_applicable_rate=0.10,
            tariff_rate=0.13,
            disposal_adjustment=100_000,
            disposal_reason="폐기 테스트",
            obsolescence_adjustment=200_000,
            obsolescence_reason="평가손실 테스트",
        )
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "forecast.xlsx"
            result = ForecastEngine(self.model, self.mapping).run(request, output)
            workbook = GoldenWorkbook(output)
            baseline = GoldenWorkbook(self.model)
            self.assertAlmostEqual(result.detail["plan_na_sa_tariff"], 6_500.0, delta=0.01)
            self.assertAlmostEqual(result.detail["forecast_na_sa_tariff"], 13_000.0, delta=0.01)
            self.assertAlmostEqual(result.detail["na_sa_tariff_adjustment"], 6_500.0, delta=0.01)
            self.assertAlmostEqual(
                result.detail["new_business_goods_cogs_reference"], 2_550_000.0, delta=0.01,
            )
            self.assertAlmostEqual(float(workbook.value("K1289")), 0.0, delta=1.0)
            self.assertAlmostEqual(
                float(workbook.value("K1273")), float(baseline.value("K1273")) + 100_000, delta=1.0,
            )
            self.assertAlmostEqual(
                float(workbook.value("K1295")), float(baseline.value("K1295") or 0) + 200_000, delta=1.0,
            )
            self.assertAlmostEqual(
                result.sga, result.detail["model_sga_including_tariff_adjustment"], delta=1.0,
            )
            self.assertAlmostEqual(
                result.detail["selling_transport_after_adjustment"]
                - result.detail["selling_transport_before_adjustment"],
                0.0,
                delta=1.0,
            )
            self.assertAlmostEqual(
                float(workbook.value("K1168")), float(baseline.value("K1168")), delta=1.0,
            )
            self.assertAlmostEqual(
                float(workbook.value("K1194")), float(baseline.value("K1194")), delta=1.0,
            )
            expected_refund = (
                float(workbook.value("K211") or 0) + float(workbook.value("K699") or 0)
            ) * 0.013
            self.assertAlmostEqual(float(workbook.value("K1294")), -expected_refund, delta=1.0)
            with zipfile.ZipFile(output) as archive:
                namespace = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
                audit_bytes = archive.read("xl/worksheets/sheet2.xml")
                audit_sheet = ET.fromstring(audit_bytes)
                locations = {
                    item.attrib.get("location")
                    for item in audit_sheet.findall(".//m:hyperlink", namespace)
                }
                self.assertIn("'Data'!K1289", locations)
                self.assertIn("'Data'!K1294", locations)
                self.assertIn("'Data'!K1273", locations)
                self.assertIn("'Data'!K1295", locations)
                self.assertNotIn("'Data'!K1168", locations)
                self.assertNotIn("'Data'!K1194", locations)
                audit_text = audit_bytes.decode("utf-8")
                self.assertIn("원재료 관세 환급금", audit_text)
                self.assertIn("제품 폐기손실", audit_text)

    def test_reference_tariff_is_not_applied_until_sga_is_manually_changed(self):
        sales = {key: SalesInput() for key in [
            "SW400", "SW440", "BW400", "BW440", "LC", "FS_SW", "FS_BW", "FS_TW",
            "UF_MBR", "IX", "OTHER",
        ]}
        production = {key: 0 for key in [
            "SW400", "SW440", "BW400", "BW440", "LC", "FS_SW", "FS_BW", "FS_TW",
        ]}
        request = ForecastInput(
            month=7, sales=sales, production=production,
            plan_na_sa_sales=500_000, na_sa_sales=1_000_000,
            tariff_applicable_rate=0.10, tariff_rate=0.13,
            sga_adjustments=[
                CostAdjustment(
                    row=1168,
                    amount=6_500,
                    reason="계획 대비 미주지역 매출 변동으로 인한 관세 금액 반영 : 6,500원",
                )
            ],
        )
        baseline = ModelMeta("base", "기준", "계획", 2026, 1, 12, "2026-01-01", "V1", True,
            "base.xlsx", "2026-01-01T00:00:00+09:00")
        comparison = ModelMeta(
            "target", "비교", "추정", 2026, 1, 12, "2026-07-01", "V1", True,
            "target.xlsx", "2026-07-01T00:00:00+09:00",
        )
        engine = GenericComparisonEngine(self.mapping)
        period = next(item for item in engine.available_periods(baseline, comparison) if item.key == "M07")
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "target.xlsx"
            forecast = ForecastEngine(self.model, self.mapping).run(request, target)
            result = engine.compare(baseline, self.model, comparison, target, period)
            baseline_op = float(GoldenWorkbook(self.model).value("K1306") or 0)
            self.assertAlmostEqual(result.operating_profit_delta, forecast.operating_profit - baseline_op, delta=1.0)
            tariff = next(item for item in result.cost_summary if item["code"] == "tariff")
            self.assertAlmostEqual(tariff["comparison"], 0.0, delta=0.01)
            target_workbook = GoldenWorkbook(target)
            self.assertAlmostEqual(
                float(target_workbook.value("K1168")),
                float(GoldenWorkbook(self.model).value("K1168")) + 6_500,
                delta=1.0,
            )
            with zipfile.ZipFile(target) as archive:
                audit_text = archive.read("xl/worksheets/sheet2.xml").decode("utf-8")
                self.assertIn("판매비_", audit_text)
                self.assertIn("계획 대비 미주지역 매출 변동으로 인한 관세 금액 반영", audit_text)
            self.assertTrue(result.reconciled)

    def test_purchase_team_raw_material_total_is_allocated_to_front_and_back_process(self):
        sales = {key: SalesInput() for key in [
            "SW400", "SW440", "BW400", "BW440", "LC", "FS_SW", "FS_BW", "FS_TW",
            "UF_MBR", "IX", "OTHER",
        ]}
        production = {key: 1_000 for key in [
            "SW400", "SW440", "BW400", "BW440", "LC", "FS_SW", "FS_BW", "FS_TW",
        ]}
        purchase_team_total = 7_000_000_000
        request = ForecastInput(
            month=7,
            sales=sales,
            production=production,
            raw_material_basis="direct",
            raw_material_direct=purchase_team_total,
            refund_rate=0.013,
        )
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "purchase_team_forecast.xlsx"
            result = ForecastEngine(self.model, self.mapping).run(request, output)
            workbook = GoldenWorkbook(output)

            expected_front = purchase_team_total * result.detail["front_raw_material_ratio"]
            expected_back = purchase_team_total - expected_front
            self.assertAlmostEqual(float(workbook.value("K211")), expected_front, delta=1.0)
            self.assertAlmostEqual(float(workbook.value("K699")), expected_back, delta=1.0)
            self.assertAlmostEqual(
                float(workbook.value("K211")) + float(workbook.value("K699")),
                purchase_team_total,
                delta=1.0,
            )
            self.assertAlmostEqual(
                float(workbook.value("K1294")),
                -(purchase_team_total * 0.013),
                delta=1.0,
            )
            self.assertTrue(next(item for item in result.validations if item["name"] == "수식 보호")["ok"])
            self.assertTrue(
                next(
                    item for item in result.validations
                    if item["name"] == "구매팀 원재료 투입비 배부 정합성"
                )["ok"]
            )

            with zipfile.ZipFile(output) as archive:
                namespace = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
                audit_bytes = archive.read("xl/worksheets/sheet2.xml")
                audit_sheet = ET.fromstring(audit_bytes)
                locations = {
                    item.attrib.get("location")
                    for item in audit_sheet.findall(".//m:hyperlink", namespace)
                }
                audit_text = audit_bytes.decode("utf-8")
                self.assertIn("'Data'!K211", locations)
                self.assertIn("'Data'!K699", locations)
                self.assertIn("'Data'!K1294", locations)
                self.assertIn("구매팀 예상 투입비_전공정", audit_text)
                self.assertIn("구매팀 예상 투입비_후공정", audit_text)
                self.assertIn("추정 전공정 원재료비 비율", audit_text)
                self.assertIn("추정 후공정 원재료비 비율", audit_text)
                self.assertIn("원재료 관세 환급률 1.3%", audit_text)


if __name__ == "__main__": unittest.main()
