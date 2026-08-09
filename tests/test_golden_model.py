from __future__ import annotations

import io
import unittest

import numpy as np
import pandas as pd

from forecast_dashboard.golden_model import GoldenModelAdapter
from forecast_dashboard.workbooks import safe_extract


class GoldenModelAdapterTests(unittest.TestCase):
    def _golden_payload(self) -> bytes:
        data = pd.DataFrame([[None] * 16 for _ in range(40)])
        data.iloc[1, 4:16] = [f"26년 {month}월" for month in range(1, 13)]
        data.iloc[2, 4:16] = ["실적"] * 6 + ["계획"] * 6
        rows = {
            4: ("★판매 관리", None), 5: ("SW", "수량"), 6: (None, "금액(천원)"), 7: ("BW", "수량"), 8: (None, "금액(천원)"),
            10: ("★판매관리비 관리 명세서", None), 11: ("판매비", None), 12: ("변동비", "운반비"), 13: (None, "판매비 계"),
            14: ("일반관리비", None), 15: ("고정비", "인건비"), 16: (None, "일반관리비 계"), 17: (None, "판매관리비 계"),
            20: ("★손익계산서", None), 21: (None, "1.제품 매출액"), 22: (None, "SW"), 23: (None, "BW"), 24: (None, "LC"),
            25: (None, "2.반제품 매출액"), 26: (None, "판매량(m)"), 27: (None, "3. 상품(LC/신사업)"), 28: (None, "4. 기타 매출액"), 29: (None, "5. 판매장려금"),
            30: (None, "1. 제품 매출원가"), 31: (None, "원부재료"), 32: (None, "노무비"), 33: (None, "외주가공비"), 34: (None, "기타경비"),
            35: (None, "2. 반제품 매출원가"), 36: (None, "원부재료"), 37: (None, "노무비"), 38: (None, "외주가공비"), 39: (None, "기타경비"),
        }
        for row, (c, d) in rows.items():
            data.iat[row, 2] = c
            data.iat[row, 3] = d
            data.iloc[row, 4:16] = np.arange(1, 13)
        # The compact fixture only verifies legacy detection elsewhere; Data
        # projection behavior is covered by the real-workbook integration test.
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            pd.DataFrame([["readme"]]).to_excel(writer, index=False, header=False, sheet_name="README_GoldenModel")
            data.to_excel(writer, index=False, header=False, sheet_name="Data")
            for name in ("STD_판매", "STD_생산", "STD_원부재료", "STD_제조경비", "STD_판관비"):
                pd.DataFrame([[None] * 4 for _ in range(6)]).to_excel(writer, index=False, header=False, sheet_name=name)
        return output.getvalue()

    def test_legacy_safe_extract_is_unchanged(self):
        frame = pd.DataFrame([[None, None, "제품매출입력", None, *([1_000_000] * 12)]])
        np.testing.assert_array_equal(safe_extract("제품매출입력", frame), np.ones(12))

    def test_sheet_aliases_are_normalized(self):
        adapter = GoldenModelAdapter()
        resolved = adapter._resolve_sheets(["표준_판매", "원본데이터"])
        self.assertEqual(resolved, {"data": "원본데이터", "sales": "표준_판매"})

    def test_scenario_mask_separates_actual_and_plan(self):
        frame = pd.DataFrame([[None] * 16 for _ in range(3)])
        frame.iloc[2, 4:16] = ["실적"] * 6 + ["계획"] * 6
        np.testing.assert_array_equal(GoldenModelAdapter._scenario_mask(frame, "Actual"), [1] * 6 + [0] * 6)
        np.testing.assert_array_equal(GoldenModelAdapter._scenario_mask(frame, "Plan"), [0] * 6 + [1] * 6)


if __name__ == "__main__":
    unittest.main()

