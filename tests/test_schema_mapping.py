from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from forecast.engine import ForecastEngine


class SchemaMappingTests(unittest.TestCase):
    def test_detected_workbook_uses_schema_override(self):
        workbook_xml = """<?xml version="1.0" encoding="UTF-8"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets><sheet name="Data" sheetId="1" r:id="rId1"/></sheets>
</workbook>"""
        relationships_xml = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
</Relationships>"""
        data_xml = """<?xml version="1.0" encoding="UTF-8"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData>
    <row r="568"><c r="C568" t="inlineStr"><is><t>MCM 매입 수량</t></is></c></row>
    <row r="1166"><c r="B1166" t="inlineStr"><is><t>★판매관리비 관리 명세서</t></is></c></row>
    <row r="1244"><c r="B1244" t="inlineStr"><is><t>★손익계산서</t></is></c></row>
  </sheetData>
</worksheet>"""
        mapping = {
            "production": {"FS_SW": 119, "SW400": 547},
            "comparison": {"pnl_rows": {"revenue": 1201}},
            "formula_input_exceptions": ["*63"],
            "schema_overrides": [{
                "name": "golden_model_standard_v1",
                "detect_cells": {
                    "B1166": "★판매관리비 관리 명세서",
                    "B1244": "★손익계산서",
                    "C568": "MCM 매입 수량",
                },
                "mapping": {
                    "production": {"SW400": 556},
                    "comparison": {"pnl_rows": {"revenue": 1248}},
                    "formula_input_exceptions": ["*63", "*1265"],
                },
            }],
        }

        with tempfile.TemporaryDirectory() as directory:
            workbook_path = Path(directory) / "golden.xlsx"
            mapping_path = Path(directory) / "mapping.json"
            with zipfile.ZipFile(workbook_path, "w") as archive:
                archive.writestr("xl/workbook.xml", workbook_xml)
                archive.writestr("xl/_rels/workbook.xml.rels", relationships_xml)
                archive.writestr("xl/worksheets/sheet1.xml", data_xml)
            mapping_path.write_text(json.dumps(mapping, ensure_ascii=False), encoding="utf-8")

            engine = ForecastEngine(workbook_path, mapping_path)

        self.assertEqual(engine.schema_name, "golden_model_standard_v1")
        self.assertEqual(engine.mapping["production"], {"FS_SW": 119, "SW400": 556})
        self.assertEqual(engine.mapping["comparison"]["pnl_rows"]["revenue"], 1248)
        self.assertEqual(engine.mapping["formula_input_exceptions"], ["*63", "*1265"])
        self.assertNotIn("schema_overrides", engine.mapping)


if __name__ == "__main__":
    unittest.main()
