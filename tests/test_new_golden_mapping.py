from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAPPING = ROOT / "config" / "model_mapping.json"


class NewGoldenModelMappingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.mapping = json.loads(MAPPING.read_text(encoding="utf-8"))

    def test_new_golden_model_is_the_only_mapping(self):
        self.assertNotIn("schema_overrides", self.mapping)
        self.assertEqual(
            self.mapping["production"],
            {
                "FS_SW": 119,
                "FS_BW": 122,
                "FS_TW": 125,
                "SW400": 556,
                "SW440": 557,
                "BW400": 558,
                "BW440": 559,
                "LC": 560,
            },
        )
        self.assertEqual(
            self.mapping["mcm"],
            {"SW400": 568, "SW440": 569, "BW400": 570, "BW440": 571},
        )

    def test_sga_and_pnl_rows_match_new_workbook(self):
        self.assertEqual(self.mapping["sga_input_rows"][0], 1168)
        self.assertEqual(self.mapping["sga_input_rows"][-1], 1222)
        self.assertEqual(
            self.mapping["comparison"]["pnl_rows"],
            {
                "revenue": 1248,
                "cogs": 1268,
                "gross_profit": 1298,
                "selling_expense": 1302,
                "general_admin": 1303,
                "operating_profit": 1306,
            },
        )

    def test_protected_formula_exceptions_are_explicit(self):
        self.assertEqual(
            set(self.mapping["formula_input_exceptions"]),
            {"*63", "*69", "*75", "*114", "*211", "*699", "*1265", "*1289", "*1294"},
        )
        self.assertEqual(
            self.mapping["special_rows"]["raw_material_process_rows"],
            {"front_process": 211, "back_process": 699},
        )
        self.assertEqual(self.mapping["special_rows"]["lc_unit_cost"], 936)


if __name__ == "__main__":
    unittest.main()
