from pathlib import Path

from openpyxl import Workbook

from forecast.preflight import ExcelPreflightValidator, PreflightValidationError


ROOT = Path(__file__).resolve().parents[1]


def _workbook(path: Path, *, operating_profit_row: int = 1306) -> None:
    book = Workbook()
    sheet = book.active
    sheet.title = "Data"
    for column in range(5, 17):
        sheet.cell(3, column, "계획")
    sheet["E2"] = "2026년"
    sheet["B211"] = "전공정 원재료 합계"
    sheet["B699"] = "후공정 원재료 합계"
    sheet["B289"] = "★제조경비 명세서_입력"
    sheet["B320"] = "*제조원가 변동비/고정비 비율"
    sheet["B1167"] = "★판매관리비 관리 명세서"
    sheet["B1247"] = "★손익계산서"
    sheet.cell(operating_profit_row, 2, "영업이익")
    book.save(path)


def test_anchor_and_hierarchical_block_preflight_passes(tmp_path):
    path = tmp_path / "valid.xlsx"
    _workbook(path)
    mapping = __import__("json").loads(
        (ROOT / "config/model_mapping.json").read_text(encoding="utf-8")
    )

    report = ExcelPreflightValidator(mapping).require(path, expected_year=2026)

    assert report.passed
    assert report.anchors["front_raw_material_total"] == 211
    assert report.anchors["sga_stop"] == 1247


def test_shifted_required_anchor_blocks_calculation(tmp_path):
    path = tmp_path / "shifted.xlsx"
    _workbook(path, operating_profit_row=1315)
    mapping = __import__("json").loads(
        (ROOT / "config/model_mapping.json").read_text(encoding="utf-8")
    )

    try:
        ExcelPreflightValidator(mapping).require(path, expected_year=2026)
    except PreflightValidationError as exc:
        assert any(issue.code == "anchor_missing" for issue in exc.report.issues)
    else:
        raise AssertionError("shifted anchor must block calculation")
