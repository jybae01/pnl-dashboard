import io

import pandas as pd
import pytest

from forecast_dashboard.storage import StorageError, validate_xlsx
from forecast_dashboard.workbooks import extract_series


def workbook_bytes() -> bytes:
    output = io.BytesIO()
    pd.DataFrame([["??", "??", "???", *range(1, 13)]]).to_excel(
        output, index=False, header=False, engine="openpyxl"
    )
    return output.getvalue()


def test_validate_xlsx_accepts_workbook():
    validate_xlsx(workbook_bytes())


def test_validate_xlsx_rejects_non_workbook():
    with pytest.raises(StorageError):
        validate_xlsx(b"not an xlsx")


def test_extract_series_supports_three_metadata_columns():
    frame = pd.DataFrame([["??", "??", "??????", *range(1, 13)]])
    values = extract_series("??????", frame)
    assert values.tolist() == list(range(1, 13))
