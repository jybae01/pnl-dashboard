from __future__ import annotations

import unittest
from pathlib import Path

from forecast.analysis import (
    ActivityRecord,
    AnalysisEngine,
    AnalysisScenario,
    DirectEffectRecord,
    ExpenseRecord,
    PnlRecord,
    ProductRecord,
    ScenarioMeta,
)
from forecast.analysis.configuration import AnalysisConfig
from forecast.analysis.manufacturing_effects import calculate_manufacturing_effects
from forecast.analysis.material_effects import calculate_material_effects
from forecast.analysis.normalizer import ForecastOutputNormalizer
from forecast.analysis.reconciliation import reconcile
from forecast.analysis.sales_effects import calculate_sales_effects
from forecast.analysis.sga_effects import calculate_sga_effects
from forecast.analysis.validation import validate_scenario


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "analysis_v1.json"


def scenario(scenario_id: str, **kwargs) -> AnalysisScenario:
    return AnalysisScenario(
        meta=ScenarioMeta(scenario_id, kwargs.pop("scenario_type", "PLAN"), "v1"),
        **kwargs,
    )


class SalesEffectsTest(unittest.TestCase):
    def test_volume_mix_price_transport_and_tariff_signs(self):
        config = AnalysisConfig.load(CONFIG)
        base = scenario(
            "base",
            products=[
                ProductRecord("2026-05", "SW", "SW", sales_qty=60, sales_amount=600, product_cogs=300),
                ProductRecord("2026-05", "BW", "BW", sales_qty=40, sales_amount=800, product_cogs=400),
            ],
            sga_expenses=[ExpenseRecord("2026-05", "판매비_운반비", 100, "sga")],
            activities=[ActivityRecord("2026-05", transport_activity=100, tariff_input=20)],
            pnl=[PnlRecord("2026-05", 1400, 700, 100)],
        )
        comp = scenario(
            "comp",
            products=[
                ProductRecord("2026-05", "SW", "SW", sales_qty=50, sales_amount=600, product_cogs=300),
                ProductRecord("2026-05", "BW", "BW", sales_qty=70, sales_amount=1540, product_cogs=700),
            ],
            sga_expenses=[ExpenseRecord("2026-05", "판매비_운반비", 150, "sga")],
            activities=[ActivityRecord("2026-05", transport_activity=120, tariff_input=30)],
            pnl=[PnlRecord("2026-05", 2140, 1000, 200)],
        )
        result = calculate_sales_effects(base, comp, config)
        self.assertAlmostEqual(result.quantity, 124.0)
        self.assertAlmostEqual(result.mix, 110.0)
        self.assertAlmostEqual(result.price, 216.0)
        self.assertAlmostEqual(result.tariff, -10.0)
        self.assertAlmostEqual(result.transport_quantity, -16.0)
        self.assertAlmostEqual(result.transport_unit, -24.0)
        self.assertAlmostEqual(result.price, result.displayed_price + result.transport_unit)

    def test_exact_symmetric_price_fx_split(self):
        config = AnalysisConfig.load(CONFIG)
        base = scenario(
            "base",
            products=[ProductRecord("2026-05", "SW", "SW", sales_qty=10, sales_amount=1000, sales_fx=10, sales_currency="USD")],
            pnl=[PnlRecord("2026-05", 1000, 0, 0)],
        )
        comp = scenario(
            "comp",
            products=[ProductRecord("2026-05", "SW", "SW", sales_qty=10, sales_amount=1320, sales_fx=12, sales_currency="USD")],
            pnl=[PnlRecord("2026-05", 1320, 0, 0)],
        )
        result = calculate_sales_effects(base, comp, config)
        self.assertAlmostEqual(result.price, 110.0)
        self.assertAlmostEqual(result.sales_fx, 210.0)
        self.assertAlmostEqual(result.price + result.sales_fx, 320.0)

    def test_reference_workbook_transport_and_tariff_split(self):
        """Reproduce 판매,원부재료/판관비 reference cells X14:X16."""
        config = AnalysisConfig.load(CONFIG)
        base = scenario(
            "base",
            sga_expenses=[ExpenseRecord("2026-05", "판매비_운반비", 553027408.5002899, "sga")],
            activities=[ActivityRecord(
                "2026-05", transport_activity=42308.85005846914,
                tariff_input=268511014.2498839,
            )],
            pnl=[PnlRecord("2026-05", 0, 0, 0)],
        )
        comp = scenario(
            "comp",
            sga_expenses=[ExpenseRecord("2026-05", "판매비_운반비", 409398115, "sga")],
            activities=[ActivityRecord(
                "2026-05", transport_activity=32412.367067809406,
                tariff_input=70294971,
            )],
            pnl=[PnlRecord("2026-05", 0, 0, 0)],
        )
        result = calculate_sales_effects(base, comp, config)
        self.assertAlmostEqual(result.transport_quantity, 66551363.42329753, places=4)
        self.assertAlmostEqual(result.transport_unit, -121138113.1728915, places=4)
        self.assertAlmostEqual(result.tariff, 198216043.2498839, places=4)


class MaterialEffectsTest(unittest.TestCase):
    def test_total_jpy_and_excluding_jpy_reconcile(self):
        base = scenario(
            "base",
            products=[ProductRecord(
                "2026-05", "FS", "FS", unit_basis="LENGTH", sales_length=100,
                production_length=100, raw_material_cost=1000, nonwoven_cost=1000,
                nonwoven_sales_input_length=100, jpy_fx=10,
            )],
            pnl=[PnlRecord("2026-05", 0, 0, 0)],
        )
        comp = scenario(
            "comp",
            products=[ProductRecord(
                "2026-05", "FS", "FS", unit_basis="LENGTH", sales_length=80,
                production_length=80, raw_material_cost=880, nonwoven_cost=960,
                nonwoven_sales_input_length=80, jpy_fx=12,
            )],
            pnl=[PnlRecord("2026-05", 0, 0, 0)],
        )
        result = calculate_material_effects(base, comp)
        self.assertAlmostEqual(result.total, -80.0)
        self.assertAlmostEqual(result.nonwoven_jpy, -160.0)
        self.assertAlmostEqual(result.unit_excluding_jpy, 80.0)
        self.assertAlmostEqual(result.total, result.nonwoven_jpy + result.unit_excluding_jpy)

    def test_reference_workbook_material_v1_cells(self):
        """Reproduce 판매,원부재료 AJ40:AJ44 and AN46:AN49."""
        base_rows = [
            ProductRecord("2026-05", "FS", "FS", unit_basis="LENGTH", production_length=1910849.8109899776,
                          raw_material_cost=2833622108.646852, sales_length=174716.66666666666,
                          nonwoven_cost=716.0174165957569 * 1910849.8109899776, jpy_fx=9.45),
            ProductRecord("2026-05", "SW", "SW", production_qty=15255.2, raw_material_cost=1064196485.051189),
            ProductRecord("2026-05", "BW", "BW", production_qty=20099.945474898188, raw_material_cost=1228277690.5247855),
            ProductRecord("2026-05", "LC", "LC", production_qty=2672.333333333334, raw_material_cost=48584793.568657786),
        ]
        comp_rows = [
            ProductRecord("2026-05", "FS", "FS", unit_basis="LENGTH", production_length=1759191,
                          raw_material_cost=2918396410, sales_length=134500,
                          nonwoven_sales_input_length=1424544.8264266404, jpy_fx=9.4204),
            ProductRecord("2026-05", "SW", "SW", production_qty=9877, raw_material_cost=752512149.3327518, sales_qty=13928),
            ProductRecord("2026-05", "BW", "BW", production_qty=16432, raw_material_cost=1095111527.9246972, sales_qty=13135),
            ProductRecord("2026-05", "LC", "LC", production_qty=3089, raw_material_cost=43298254.74255069, sales_qty=2363),
        ]
        base = scenario("base", products=base_rows, pnl=[PnlRecord("2026-05", 0, 0, 0)])
        comp = scenario("comp", products=comp_rows, pnl=[PnlRecord("2026-05", 0, 0, 0)])
        result = calculate_material_effects(base, comp)
        self.assertAlmostEqual(result.total, -176099190.6594511, places=4)
        self.assertAlmostEqual(result.nonwoven_jpy, 3194917.209598621, places=4)
        self.assertAlmostEqual(result.unit_excluding_jpy, -179294107.86904973, places=4)


class ManufacturingEffectsTest(unittest.TestCase):
    def test_activity_unit_fixed_and_realization(self):
        config = AnalysisConfig.load(CONFIG)
        base = scenario(
            "base",
            manufacturing_expenses=[
                ExpenseRecord("2026-05", "수도광열비", 1000, "manufacturing", 0.5, 0.5),
                ExpenseRecord("2026-05", "급료", 200, "manufacturing", 0.5, 0.5),
            ],
            activities=[ActivityRecord("2026-05", front_activity=100, back_activity=100, manufacturing_input_cost=100)],
            pnl=[PnlRecord("2026-05", 0, 100, 0)],
        )
        comp = scenario(
            "comp",
            manufacturing_expenses=[
                ExpenseRecord("2026-05", "수도광열비", 900, "manufacturing", 0.5, 0.5),
                ExpenseRecord("2026-05", "급료", 250, "manufacturing", 0.5, 0.5),
            ],
            activities=[ActivityRecord("2026-05", front_activity=80, back_activity=120, manufacturing_input_cost=100)],
            pnl=[PnlRecord("2026-05", 0, 80, 0)],
        )
        result = calculate_manufacturing_effects(base, comp, config)
        self.assertAlmostEqual(result.front_activity, 100.0)
        self.assertAlmostEqual(result.front_unit, -50.0)
        self.assertAlmostEqual(result.back_activity, -100.0)
        self.assertAlmostEqual(result.back_unit, 150.0)
        self.assertAlmostEqual(result.front_fixed + result.back_fixed, -50.0)
        self.assertAlmostEqual(result.occurrence_total, 50.0)
        self.assertAlmostEqual(result.realized_total, 40.0)

    def test_realization_rate_above_one_is_not_capped(self):
        config = AnalysisConfig.load(CONFIG)
        base = scenario(
            "base",
            manufacturing_expenses=[ExpenseRecord("2026-06", "급료", 100, "manufacturing", 1, 0)],
            activities=[ActivityRecord("2026-06")],
            pnl=[PnlRecord("2026-06", 0, 0, 0)],
        )
        comp = scenario(
            "comp",
            manufacturing_expenses=[ExpenseRecord("2026-06", "급료", 0, "manufacturing", 1, 0)],
            activities=[ActivityRecord("2026-06", manufacturing_input_cost=100)],
            pnl=[PnlRecord("2026-06", 0, 150, 0)],
        )
        result = calculate_manufacturing_effects(base, comp, config)
        self.assertAlmostEqual(result.occurrence_total, 100.0)
        self.assertAlmostEqual(result.realized_total, 150.0)

    def test_reference_workbook_variable_manufacturing_row(self):
        """Reproduce 제조경비 row 15 (수도광열비) effect columns Y:AF."""
        config = AnalysisConfig.load(CONFIG)
        base = scenario(
            "base",
            manufacturing_expenses=[ExpenseRecord(
                "2026-05", "수도광열비", 1173555354.6390276, "manufacturing", 0.43, 0.57,
            )],
            activities=[ActivityRecord("2026-05", front_activity=1910849.8109899776, back_activity=35757.2)],
            pnl=[PnlRecord("2026-05", 0, 0, 0)],
        )
        comp = scenario(
            "comp",
            manufacturing_expenses=[ExpenseRecord(
                "2026-05", "수도광열비", 1232707449, "manufacturing", 0.43, 0.57,
            )],
            activities=[ActivityRecord(
                "2026-05", front_activity=1716612, back_activity=27063,
                inventory_realization_rate=0.7660090097695618,
            )],
            pnl=[PnlRecord("2026-05", 0, 0, 0)],
        )
        result = calculate_manufacturing_effects(base, comp, config)
        self.assertAlmostEqual(result.front_activity, 51295498.68092394, places=4)
        self.assertAlmostEqual(result.front_unit, -76730899.25614204, places=4)
        self.assertAlmostEqual(result.back_activity, 162646438.46980467, places=4)
        self.assertAlmostEqual(result.back_unit, -196363132.255559, places=4)
        self.assertAlmostEqual(result.occurrence_total, -59152094.360972434, places=4)
        self.assertAlmostEqual(result.realized_total, -45311037.227244176, places=4)

    def test_sap_activity_is_used_and_mcm_is_excluded_from_outsourcing_denominator(self):
        config = AnalysisConfig.load(CONFIG)
        base = scenario(
            "base",
            products=[
                ProductRecord("2026-07", "SW_NORMAL", "SW", sap_production_qty=100,
                              mes_production_qty=500, outsourcing_eligible_flag=True),
                ProductRecord("2026-07", "SW_MCM", "SW", sap_production_qty=20,
                              mes_production_qty=200, mcm_flag=True, mcm_qty=20),
            ],
            manufacturing_expenses=[ExpenseRecord("2026-07", "외주가공비", 1000, "manufacturing", 0, 1)],
            activities=[ActivityRecord("2026-07", back_activity=999, inventory_realization_rate=1)],
            pnl=[PnlRecord("2026-07", 0, 0, 0)],
        )
        comp = scenario(
            "comp",
            products=[
                ProductRecord("2026-07", "SW_NORMAL", "SW", sap_production_qty=80,
                              mes_production_qty=800, outsourcing_eligible_flag=True),
                ProductRecord("2026-07", "SW_MCM", "SW", sap_production_qty=60,
                              mes_production_qty=600, mcm_flag=True, mcm_qty=60),
            ],
            manufacturing_expenses=[ExpenseRecord("2026-07", "외주가공비", 900, "manufacturing", 0, 1)],
            activities=[ActivityRecord("2026-07", back_activity=1, inventory_realization_rate=1)],
            pnl=[PnlRecord("2026-07", 0, 0, 0)],
        )
        result = calculate_manufacturing_effects(base, comp, config)
        detail = result.details[0]
        self.assertEqual(detail["base_back_activity"], 100)
        self.assertEqual(detail["comparison_back_activity"], 80)
        self.assertAlmostEqual(result.back_activity, 200.0)
        self.assertAlmostEqual(result.back_unit, -100.0)
        reconciliation = next(
            row for row in result.production_reconciliation
            if row["scenario"] == "comparison" and row["product_group"] == "SW"
        )
        self.assertEqual(reconciliation["qty_difference"], 1260)


class McmMaterialIntegrationTest(unittest.TestCase):
    @staticmethod
    def _mcm_scenarios():
        base = scenario(
            "base",
            products=[
                ProductRecord("2026-07", "SW_NORMAL", "SW", sales_qty=100,
                              sap_production_qty=100, raw_material_cost=1000),
                ProductRecord("2026-07", "SW_MCM", "SW", sap_production_qty=20,
                              raw_material_cost=200, mcm_flag=True, mcm_qty=20,
                              mcm_issue_amount=200),
            ],
            manufacturing_expenses=[ExpenseRecord("2026-07", "외주가공비", 1000, "manufacturing", 0, 1)],
            activities=[ActivityRecord("2026-07", inventory_realization_rate=1)],
            pnl=[PnlRecord("2026-07", 0, 0, 0)],
        )
        comp = scenario(
            "comp",
            products=[
                ProductRecord("2026-07", "SW_NORMAL", "SW", sales_qty=100,
                              sap_production_qty=80, raw_material_cost=800),
                ProductRecord("2026-07", "SW_MCM", "SW", sap_production_qty=60,
                              raw_material_cost=900, mcm_flag=True, mcm_qty=60,
                              mcm_issue_amount=900),
            ],
            manufacturing_expenses=[ExpenseRecord("2026-07", "외주가공비", 800, "manufacturing", 0, 1)],
            activities=[ActivityRecord("2026-07", inventory_realization_rate=1)],
            pnl=[PnlRecord("2026-07", 0, 0, 0)],
        )
        return base, comp

    def test_mcm_is_full_material_detail_and_reconciles_without_bridge_duplication(self):
        base, comp = self._mcm_scenarios()
        result = calculate_material_effects(base, comp)
        # Total raw material includes the complete MCM issue amounts: 200 and 900.
        self.assertAlmostEqual(result.total, (10.0 - (1700 / 140)) * 100)
        self.assertAlmostEqual(result.mcm_paid_supply, (10.0 - 15.0) * 100)
        self.assertAlmostEqual(
            result.total,
            result.nonwoven_jpy + result.mcm_paid_supply + result.other_unit_mix,
        )
        self.assertAlmostEqual(result.detail_reconciliation_difference, 0.0)

        engine = AnalysisEngine(CONFIG)
        preliminary = engine.compare(base, comp)
        comp.pnl = [PnlRecord("2026-07", 0, 0, preliminary.reconciliation.effects_total)]
        final = engine.compare(base, comp)
        self.assertNotIn("mcm", {row["code"] for row in final.effects})
        self.assertTrue(final.reconciliation.reconciled)
        self.assertIn("MCM(유상사급)", final.narrative)


class SgaAndEngineTest(unittest.TestCase):
    def test_sga_excludes_transport_and_separates_variable_accounts(self):
        config = AnalysisConfig.load(CONFIG)
        base = scenario("base", sga_expenses=[
            ExpenseRecord("2026-05", "브랜드사용료", 100, "sga"),
            ExpenseRecord("2026-05", "포장비", 20, "sga"),
            ExpenseRecord("2026-05", "급여", 300, "sga"),
            ExpenseRecord("2026-05", "판매비_운반비", 100, "sga"),
        ], pnl=[PnlRecord("2026-05", 0, 0, 0)])
        comp = scenario("comp", sga_expenses=[
            ExpenseRecord("2026-05", "브랜드사용료", 120, "sga"),
            ExpenseRecord("2026-05", "포장비", 10, "sga"),
            ExpenseRecord("2026-05", "급여", 250, "sga"),
            ExpenseRecord("2026-05", "판매비_운반비", 150, "sga"),
        ], pnl=[PnlRecord("2026-05", 0, 0, 0)])
        result = calculate_sga_effects(base, comp, config)
        self.assertAlmostEqual(result.variable, -10.0)
        self.assertAlmostEqual(result.fixed, 50.0)

    def test_direct_effect_reconciles_and_common_schema_contains_metadata(self):
        engine = AnalysisEngine(CONFIG)
        base = scenario(
            "base",
            pnl=[PnlRecord("2026-05", 0, 0, 0)],
            direct_effects=[DirectEffectRecord("2026-05", "disposal", "제품 폐기손실", 100)],
        )
        comp = scenario(
            "comp",
            scenario_type="ACTUAL",
            pnl=[PnlRecord("2026-05", 0, 0, 30)],
            direct_effects=[DirectEffectRecord("2026-05", "disposal", "제품 폐기손실", 70)],
        )
        result = engine.compare(base, comp)
        self.assertTrue(result.reconciliation.reconciled)
        self.assertAlmostEqual(result.reconciliation.residual, 0.0)
        tables = comp.to_common_tables()
        self.assertEqual(tables["pnl"][0]["scenario_id"], "comp")
        self.assertEqual(tables["pnl"][0]["scenario_type"], "ACTUAL")
        sample = scenario(
            "schema",
            manufacturing_expenses=[ExpenseRecord("2026-05", "수도광열비", 100, "manufacturing", 0.4, 0.6)],
            sga_expenses=[ExpenseRecord("2026-05", "포장비", 20, "sga")],
        ).to_common_tables()
        self.assertEqual(sample["manufacturing_expenses"][0]["manufacturing_expense_account"], "수도광열비")
        self.assertEqual(sample["manufacturing_expenses"][0]["allocation_ratios"]["back"], 0.6)
        self.assertEqual(sample["sga_expenses"][0]["sga_account"], "포장비")

    def test_normalizer_and_reconciliation_residual(self):
        normalized = ForecastOutputNormalizer.normalize({
            "meta": {"scenario_id": "f1", "scenario_type": "FORECAST", "version": "v2"},
            "pnl": [{"year_month": "2026-07", "revenue": 100, "cogs": 70, "operating_profit": 20}],
        })
        self.assertEqual(normalized.months, ("2026-07",))
        check = reconcile(20, [{"profit_effect": 17.5}], absolute_tolerance=1)
        self.assertFalse(check.reconciled)
        self.assertAlmostEqual(check.residual, 2.5)

    def test_allocation_ratio_validation_is_configuration_driven(self):
        config = AnalysisConfig.load(CONFIG)
        item = scenario(
            "bad",
            manufacturing_expenses=[ExpenseRecord("2026-07", "급료", 100, "manufacturing", 0.4, 0.4)],
            pnl=[PnlRecord("2026-07", 0, 0, 0)],
        )
        issues = validate_scenario(item, config)
        self.assertTrue(any("100%가 아님" in issue for issue in issues))


if __name__ == "__main__":
    unittest.main()
