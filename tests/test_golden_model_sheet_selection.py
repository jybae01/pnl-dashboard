from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

from forecast.workbook import GoldenWorkbook


class GoldenModelSheetSelectionTests(unittest.TestCase):
    def test_data_sheet_is_selected_when_readme_is_first(self):
        workbook_xml = """<?xml version="1.0" encoding="UTF-8"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
    <sheet name="README_GoldenModel" sheetId="1" r:id="rId1"/>
    <sheet name="Data" sheetId="2" r:id="rId2"/>
  </sheets>
</workbook>"""
        relationships_xml = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/>
</Relationships>"""
        readme_xml = """<?xml version="1.0" encoding="UTF-8"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>README</t></is></c></row></sheetData>
</worksheet>"""
        data_xml = """<?xml version="1.0" encoding="UTF-8"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData>
    <row r="1197"><c r="B1197" t="inlineStr"><is><t>일반관리비</t></is></c></row>
    <row r="1201"><c r="E1201"><v>151694913</v></c></row>
  </sheetData>
</worksheet>"""

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "golden.xlsx"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("xl/workbook.xml", workbook_xml)
                archive.writestr("xl/_rels/workbook.xml.rels", relationships_xml)
                archive.writestr("xl/worksheets/sheet1.xml", readme_xml)
                archive.writestr("xl/worksheets/sheet2.xml", data_xml)

            workbook = GoldenWorkbook(path)

        self.assertEqual(workbook.sheet_xml, "xl/worksheets/sheet2.xml")
        self.assertEqual(workbook.raw_value("B1197"), "일반관리비")
        self.assertEqual(workbook.raw_value("E1201"), 151694913.0)


if __name__ == "__main__":
    unittest.main()
