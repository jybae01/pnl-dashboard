from __future__ import annotations

import zipfile
from pathlib import Path

from forecast.workbook import GoldenWorkbook


def _diagnostic_workbook(path: Path) -> None:
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
    <row r="1">
      <c r="A1"><v>10</v></c>
      <c r="B1"><f>A1+A2</f><v>12</v></c>
      <c r="C1"><f>B1*2</f><v>24</v></c>
    </row>
    <row r="2">
      <c r="A2"><v>2</v></c>
      <c r="B2"><f>UNSUPPORTED(A1)</f><v>77</v></c>
      <c r="C2"><f>B2+1</f><v>78</v></c>
    </row>
    <row r="3"><c r="C3"><f>A1/0</f><v>55</v></c></row>
  </sheetData>
</worksheet>"""
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("xl/workbook.xml", workbook_xml)
        archive.writestr("xl/_rels/workbook.xml.rels", relationships_xml)
        archive.writestr("xl/worksheets/sheet1.xml", data_xml)


def test_fallback_diagnostics_preserve_existing_runtime_values(tmp_path):
    path = tmp_path / "diagnostics.xlsx"
    _diagnostic_workbook(path)
    workbook = GoldenWorkbook(path)

    assert workbook.value("B2") == 77
    assert workbook.recalculate() == {}
    diagnostics = workbook.formula_diagnostics(recalculate=False)

    assert workbook.value("B2") == 77
    assert diagnostics["workbook_formula_count"] == 5
    assert diagnostics["model_sheet_formula_count"] == 5
    assert diagnostics["evaluator_success_count"] == 3
    assert diagnostics["cached_match_count"] == 3
    assert diagnostics["cached_mismatch_count"] == 0
    assert diagnostics["cached_fallback_count"] == 2
    assert diagnostics["unevaluated_count"] == 0
    assert [item["address"] for item in diagnostics["fallbacks"]] == ["B2", "C3"]
    assert diagnostics["fallbacks"][0]["exception_type"] == "FormulaError"
    assert diagnostics["fallbacks"][1]["exception_type"] == "ZeroDivisionError"


def test_dependency_report_distinguishes_complete_and_incomplete_paths(tmp_path):
    path = tmp_path / "dependencies.xlsx"
    _diagnostic_workbook(path)
    workbook = GoldenWorkbook(path)
    workbook.formula_diagnostics()

    complete = workbook.dependency_report(["C1"], sources=["A1"])
    incomplete = workbook.dependency_report(["C2"], sources=["A1"])
    unlinked = workbook.dependency_report(["C1"], sources=["A3"])

    assert complete["formula_complete"] is True
    assert complete["cached_fallback_count"] == 0
    assert ["C1", "B1"] in complete["edges"]
    assert complete["source_paths"]["A1"] == ["C1", "B1", "A1"]
    assert incomplete["formula_complete"] is False
    assert incomplete["fallback_cells"] == ["B2"]
    assert incomplete["source_paths"]["A1"] == ["C2", "B2", "A1"]
    assert unlinked["formula_complete"] is False
    assert unlinked["unlinked_sources"] == ["A3"]


def test_formula_overwrite_invalidates_dependency_cache(tmp_path):
    path = tmp_path / "dependency-cache.xlsx"
    _diagnostic_workbook(path)
    workbook = GoldenWorkbook(path)

    assert workbook.formula_precedents("B1") == ("A1", "A2")
    workbook.set_input("B1", 12, "test", allow_formula=True)

    assert workbook.formula_precedents("B1") == ()
    report = workbook.dependency_report(["C1"], sources=["A1"])
    assert report["unlinked_sources"] == ["A1"]
