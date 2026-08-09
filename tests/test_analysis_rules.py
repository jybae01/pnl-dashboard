from __future__ import annotations

import unittest

import pandas as pd

from forecast_dashboard.analysis_rules import (
    classify_manufacturing_cost,
    classify_sga_cost,
    convert_jpy_to_krw,
    freight_price_effect_source,
    inventory_realization_rate,
    manufacturing_activity_bases,
    mcm_material_amount,
    outsourcing_analysis_quantity,
)


class AnalysisRuleTests(unittest.TestCase):
    def test_manufacturing_variable_accounts(self):
        self.assertEqual(classify_manufacturing_cost("수도광열비"), "variable")
        self.assertEqual(classify_manufacturing_cost("노무비"), "fixed")

    def test_sga_variable_accounts_and_freight_source(self):
        self.assertEqual(classify_sga_cost("브랜드사용료"), "variable")
        self.assertEqual(classify_sga_cost("판매운반비"), "fixed")
        self.assertEqual(freight_price_effect_source(120, 20), 100)

    def test_inventory_realization_is_not_capped(self):
        self.assertEqual(inventory_realization_rate(120, 100), 1.2)

    def test_jpy_rate_is_applied_without_divide_by_100(self):
        self.assertEqual(convert_jpy_to_krw(1000, 9.5), 9500)

    def test_mcm_stays_material_and_is_excluded_from_outsourcing_quantity(self):
        frame = pd.DataFrame({
            "sap_production_qty": [10, 20, 30],
            "mcm_flag": [False, True, False],
            "outsourcing_eligible_flag": [True, True, False],
        })
        self.assertEqual(outsourcing_analysis_quantity(frame), 10)
        self.assertEqual(mcm_material_amount(100, 25), 125)

    def test_sap_activity_bases(self):
        frame = pd.DataFrame({
            "product_group": ["FS", "SW", "BW", "LC"],
            "process_stage": ["front", "back", "back", "back"],
            "sap_production_length": [100, 0, 0, 0],
            "sap_production_qty": [0, 20, 30, 99],
            "mes_production_qty": [999, 999, 999, 999],
        })
        self.assertEqual(manufacturing_activity_bases(frame), (100, 50))


if __name__ == "__main__":
    unittest.main()
