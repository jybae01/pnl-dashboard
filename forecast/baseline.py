from __future__ import annotations

import zipfile
from pathlib import Path

from .engine import ForecastEngine
from .workbook import GoldenWorkbook


def inspect_baseline_workbook(path: str | Path) -> tuple[int, list[str]]:
    """Validate a forecast-compatible workbook and return its row-3 statuses."""
    path = Path(path)
    if not zipfile.is_zipfile(path):
        raise ValueError("유효한 xlsx 파일이 아닙니다.")
    workbook = GoldenWorkbook(path)
    required_cells = ["B1166", "B1244", "E1248", "E1306", "P1248", "P1306"]
    missing = [
        address for address in required_cells
        if address not in workbook.cells and address not in workbook.formulas
    ]
    if missing:
        raise ValueError(f"필수 모형 셀이 없습니다: {', '.join(missing)}")

    statuses = [
        str(workbook.raw_value(f"{ForecastEngine.column(month)}3") or "").strip()
        for month in range(1, 13)
    ]
    allowed = {"실적", "계획", "추정", ""}
    invalid = [
        f"{month}월={status}" for month, status in enumerate(statuses, 1)
        if status not in allowed
    ]
    if invalid:
        raise ValueError(f"3행의 월 구분값을 확인해 주세요: {', '.join(invalid)}")

    actual_months = [month for month, status in enumerate(statuses, 1) if status == "실적"]
    actual_through = max(actual_months, default=0)
    if actual_months != list(range(1, actual_through + 1)):
        raise ValueError("3행의 실적 월은 1월부터 중간 공백 없이 연속되어야 합니다.")
    return actual_through, statuses
