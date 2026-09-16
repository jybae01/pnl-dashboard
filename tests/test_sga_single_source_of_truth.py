from dataclasses import asdict
from pathlib import Path
import unittest

from forecast.analysis.configuration import AnalysisConfig
from forecast.analysis.schema import AnalysisScenario, ExpenseRecord, ScenarioMeta
from forecast.analysis.sga_effects import calculate_sga_effects
from forecast.bff.analysis_presentation import (
    build_analysis_presentation,
    _validate_cost_effects,
)
from forecast.bff.errors import ApiErrorCode, BffError
from forecast.comparison import GenericComparisonEngine
from forecast.provenance import ResultProvenance

CONFIG_PATH = Path("config/model_mapping.json")


class SgaSingleSourceOfTruthTest(unittest.TestCase):
    def setUp(self):
        self.engine = GenericComparisonEngine(CONFIG_PATH)
        self.config = self.engine.analysis_config

    def test_sga_accounts_derived_from_authoritative_details(self):
        # Scenario with selling transport, selling variable, and general admin fixed
        base_records = [
            ExpenseRecord(
                year_month="2026-08",
                account="판매비_운반비",
                amount=100.0,
                category="sga",
                source_section="판매비",
                source_row=1168,
                business_source="판매비 / 운반비",
            ),
            ExpenseRecord(
                year_month="2026-08",
                account="포장비",
                amount=80.0,
                category="sga",
                source_section="판매비",
                source_row=1170,
                business_source="판매비 / 포장비",
            ),
            ExpenseRecord(
                year_month="2026-08",
                account="급여",
                amount=500.0,
                category="sga",
                source_section="일반관리비",
                source_row=1200,
                business_source="일반관리비 / 급여",
            ),
        ]
        comp_records = [
            ExpenseRecord(
                year_month="2026-08",
                account="판매비_운반비",
                amount=150.0,
                category="sga",
                source_section="판매비",
                source_row=1168,
                business_source="판매비 / 운반비",
            ),
            ExpenseRecord(
                year_month="2026-08",
                account="포장비",
                amount=120.0,
                category="sga",
                source_section="판매비",
                source_row=1170,
                business_source="판매비 / 포장비",
            ),
            ExpenseRecord(
                year_month="2026-08",
                account="급여",
                amount=450.0,
                category="sga",
                source_section="일반관리비",
                source_row=1200,
                business_source="일반관리비 / 급여",
            ),
        ]
        base_scen = AnalysisScenario(
            meta=ScenarioMeta("base", "ACTUAL", "1.0"),
            sga_expenses=base_records,
        )
        comp_scen = AnalysisScenario(
            meta=ScenarioMeta("comp", "FORECAST", "1.0"),
            sga_expenses=comp_records,
        )

        sga_calc = calculate_sga_effects(base_scen, comp_scen, self.config)
        self.assertAlmostEqual(sga_calc.variable, -40.0)  # 포장비: 80 - 120 = -40
        self.assertAlmostEqual(sga_calc.fixed, 50.0)       # 급여: 500 - 450 = 50

        # Derive sga_accounts via engine
        accounts = self.engine._sga_account_rows(
            [], [], {"tariff": 0.0}, {"tariff": 5.0},
            sga_details=sga_calc.details,
        )

        # 3 accounts + 1 web tariff = 4 rows
        self.assertEqual(len(accounts), 4)

        # Fixed SG&A check
        fixed_accounts = [r for r in accounts if r["classification"] == "fixed"]
        self.assertEqual(len(fixed_accounts), 1)
        self.assertEqual(fixed_accounts[0]["account"], "급여")
        self.assertEqual(fixed_accounts[0]["section"], "일반관리비")
        self.assertEqual(fixed_accounts[0]["row"], 1200)
        self.assertEqual(fixed_accounts[0]["profit_effect"], 50.0)
        self.assertEqual(fixed_accounts[0]["bridge_position"], "고정 판관비")
        self.assertAlmostEqual(
            sum(r["profit_effect"] for r in fixed_accounts),
            sga_calc.fixed,
        )

        # Variable SG&A check
        var_accounts = [r for r in accounts if r["classification"] == "variable"]
        self.assertEqual(len(var_accounts), 1)
        self.assertEqual(var_accounts[0]["account"], "포장비")
        self.assertEqual(var_accounts[0]["section"], "판매비")
        self.assertEqual(var_accounts[0]["row"], 1170)
        self.assertEqual(var_accounts[0]["profit_effect"], -40.0)
        self.assertEqual(var_accounts[0]["bridge_position"], "변동 판관비")
        self.assertAlmostEqual(
            sum(r["profit_effect"] for r in var_accounts),
            sga_calc.variable,
        )

        # Transport check
        trans_accounts = [r for r in accounts if r["classification"] == "transport"]
        self.assertEqual(len(trans_accounts), 1)
        self.assertEqual(trans_accounts[0]["profit_effect"], 0.0)
        self.assertEqual(trans_accounts[0]["bridge_position"], "변동 판관비")

        # Web tariff check
        tariff_accounts = [r for r in accounts if r["classification"] == "tariff"]
        self.assertEqual(len(tariff_accounts), 1)
        self.assertEqual(tariff_accounts[0]["account"], "관세(직접입력)")
        self.assertEqual(tariff_accounts[0]["profit_effect"], -5.0)

    def test_cost_effects_validation_detects_sga_drift(self):
        transport_effect = 25.0
        sga_accounts = [
            {"row": 1, "account": "운반비", "classification": "transport", "profit_effect": 0.0},
            {"row": 2, "account": "변동비계정", "classification": "variable", "profit_effect": -10.0},
            {"row": 3, "account": "고정비계정", "classification": "fixed", "profit_effect": 100.0},
        ]
        amounts = {
            "material_total": 0.0,
            "manufacturing_realized": 0.0,
            "inventory_timing": 0.0,
            "sga_variable": 15.0,  # -10.0 + 25.0 = 15.0
            "sga_fixed": 100.0,
        }
        material = {"total": 0.0}
        inventory = {
            "source_validation_status": "PASS",
            "scope_validation_status": "PASS",
            "manufactured_cogs_effect": 0.0,
            "current_manufacturing_cost_effect": 0.0,
            "inventory_timing_effect": 0.0,
        }
        mfg_accounts = (
            {"account": "수도광열비", "final_profit_effect": 0.0},
            {"account": "소모품비", "final_profit_effect": 0.0},
            {"account": "외주가공비", "final_profit_effect": 0.0},
            {"account": "원자재운반비", "final_profit_effect": 0.0},
        )

        # Valid presentation cost effects pass
        _validate_cost_effects(
            amounts, material, inventory, mfg_accounts, tuple(sga_accounts),
            transport_effect=transport_effect,
        )

        # Fixed SG&A drift triggers INPUT_INTEGRITY_MISMATCH
        drifted_fixed = [dict(r) for r in sga_accounts]
        drifted_fixed[2]["profit_effect"] = 99.0
        with self.assertRaises(BffError) as ctx:
            _validate_cost_effects(
                amounts, material, inventory, mfg_accounts, tuple(drifted_fixed),
                transport_effect=transport_effect,
            )
        self.assertEqual(ctx.exception.code, ApiErrorCode.INPUT_INTEGRITY_MISMATCH)

        # Variable SG&A drift triggers INPUT_INTEGRITY_MISMATCH
        drifted_var = [dict(r) for r in sga_accounts]
        drifted_var[1]["profit_effect"] = -9.0
        with self.assertRaises(BffError) as ctx:
            _validate_cost_effects(
                amounts, material, inventory, mfg_accounts, tuple(drifted_var),
                transport_effect=transport_effect,
            )
        self.assertEqual(ctx.exception.code, ApiErrorCode.INPUT_INTEGRITY_MISMATCH)

        # Transport non-zero profit_effect triggers INPUT_INTEGRITY_MISMATCH
        drifted_transport = [dict(r) for r in sga_accounts]
        drifted_transport[0]["profit_effect"] = 1.0
        with self.assertRaises(BffError) as ctx:
            _validate_cost_effects(
                amounts, material, inventory, mfg_accounts, tuple(drifted_transport),
                transport_effect=transport_effect,
            )
        self.assertEqual(ctx.exception.code, ApiErrorCode.INPUT_INTEGRITY_MISMATCH)


if __name__ == "__main__":
    unittest.main()
