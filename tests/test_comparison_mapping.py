from __future__ import annotations

import unittest
from pathlib import Path

from forecast.comparison import GenericComparisonEngine
from forecast.storage import ModelMeta


ROOT = Path(__file__).resolve().parents[1]
MAPPING = ROOT / "config" / "model_mapping.json"


class FakeWorkbook:
    def __init__(self, row_values: dict[int, float | str] | None = None):
        self.row_values = row_values or {}
        self.read_rows: list[int] = []

    def value(self, address: str):
        row = int("".join(character for character in address if character.isdigit()))
        self.read_rows.append(row)
        if row == 1246:
            raise AssertionError("legacy customs-refund row must not be read")
        return self.row_values.get(row, 0)


def model_meta() -> ModelMeta:
    return ModelMeta(
        id="model",
        name="model",
        model_type="forecast",
        year=2026,
        start_month=7,
        end_month=7,
        created_date="2026-08-06",
        version="v1",
        confirmed=True,
        file_name="model.xlsx",
        uploaded_at="2026-08-06T00:00:00+09:00",
    )


class ComparisonMappingTests(unittest.TestCase):
    def test_extract_uses_new_golden_model_rows(self):
        engine = GenericComparisonEngine(MAPPING)
        workbook = FakeWorkbook({
            1276: 100,
            1273: 10,
            1274: 20,
            1285: 30,
            1294: -5,
            1302: 40,
            1303: 50,
        })

        result = engine._extract(workbook, model_meta(), (7,))

        self.assertNotIn(1246, workbook.read_rows)
        self.assertEqual(result["cost_summary"]["raw_material"], 100)
        self.assertEqual(result["cost_summary"]["customs_refund"], -5)
        self.assertEqual(result["effect_bases"]["product_raw_material"], 70)
        self.assertEqual(result["effect_bases"]["semi_raw_material"], 30)
        self.assertEqual(result["effect_bases"]["disposal"], 10)
        self.assertEqual(result["effect_bases"]["other_standard_cogs"], 20)
        self.assertEqual(result["effect_bases"]["general_admin"], 50)

    def test_sales_group_rows_match_new_detail_section(self):
        mapping = GenericComparisonEngine(MAPPING).mapping
        self.assertEqual(
            {
                key: (
                    spec["quantity_row"],
                    spec["amount_row"],
                    spec["cogs_row"],
                )
                for key, spec in mapping["sales_groups"].items()
            },
            {
                "SW": (1593, 1594, 1595),
                "BW": (1632, 1633, 1634),
                "LC": (1668, 1669, 1670),
                "FS": (1720, 1721, 1722),
                "NEW_BUSINESS": (113, 114, 1734),
            },
        )

    def test_analysis_adapter_uses_confirmed_material_and_allocation_rows(self):
        adapter = GenericComparisonEngine(MAPPING).full_mapping["analysis_adapter"]
        material = adapter["material"]
        self.assertEqual(material["jpy_fx_row"], 9)
        self.assertEqual(
            material["front_process"],
            {
                "nonwoven_quantity_row": 205,
                "nonwoven_amount_row": 206,
                "nonwoven_unit_row": 207,
                "other_quantity_row": 208,
                "other_amount_row": 209,
                "other_unit_row": 210,
                "total_amount_row": 211,
            },
        )
        self.assertEqual(material["back_process"]["source_start_row"], 684)
        self.assertEqual(material["back_process"]["source_end_row"], 699)
        self.assertEqual(
            adapter["manufacturing"]["front_ratio_rows"],
            {"labor": 345, "outsourcing": 346, "other_variable": 347},
        )


if __name__ == "__main__":
    unittest.main()
