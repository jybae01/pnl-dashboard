from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from forecast.comparison import GenericComparisonEngine, PeriodOption

try:
    from tests.test_golden_analysis_adapter import _build_workbook, _meta
except ModuleNotFoundError:
    from test_golden_analysis_adapter import _build_workbook, _meta


class ComparisonAnalysisBridgeTests(unittest.TestCase):
    """Exercise the real Golden Workbook -> V1 bridge path."""

    def test_adapter_effects_are_used_once_in_comparison_bridge(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base_path = root / "base.xlsx"
            comparison_path = root / "comparison.xlsx"
            _build_workbook(base_path)
            _build_workbook(comparison_path, comparison=True)

            result = GenericComparisonEngine("config/model_mapping.json").compare(
                _meta("base"),
                base_path,
                _meta("comparison"),
                comparison_path,
                PeriodOption("M01", "1월", (1,), "월"),
                baseline_sales_fx=1_000,
                comparison_sales_fx=1_100,
            )

        codes = [row["code"] for row in result.effects]
        self.assertIn("sales_mix", codes)
        self.assertIn("material_total", codes)
        self.assertIn("manufacturing_realized", codes)
        self.assertEqual(codes.count("tariff"), 1)
        self.assertAlmostEqual(
            sum(float(row["profit_effect"]) for row in result.effects),
            result.effects_total,
        )
        self.assertAlmostEqual(
            result.effects_total + result.residual,
            result.operating_profit_delta,
        )
        self.assertIn("mix_effect", result.sales_analysis["totals"])

    def test_direct_tariff_is_not_double_counted_in_sga_bridge(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base_path = root / "base.xlsx"
            comparison_path = root / "comparison.xlsx"
            _build_workbook(base_path)
            _build_workbook(comparison_path)
            base = _meta("base")
            comparison = _meta("comparison")
            base.tariff_adjustment_monthly = {"1": 0.0}
            comparison.tariff_adjustment_monthly = {"1": 100.0}

            result = GenericComparisonEngine("config/model_mapping.json").compare(
                base,
                base_path,
                comparison,
                comparison_path,
                PeriodOption("M01", "1월", (1,), "월"),
            )

        tariff_effects = [
            row for row in result.effects if row["code"] == "tariff"
        ]
        self.assertEqual(len(tariff_effects), 1)
        self.assertEqual(tariff_effects[0]["profit_effect"], -100.0)
        detail_tariffs = [
            row for row in result.sga_accounts if row["classification"] == "tariff"
        ]
        self.assertEqual(len(detail_tariffs), 1)
        self.assertEqual(detail_tariffs[0]["profit_effect"], -100.0)


if __name__ == "__main__":
    unittest.main()
