"""Golden Model workbook adapter used by the forecast dashboard.

The adapter keeps sheet names, header discovery and Golden Model projection out
of the Streamlit page.  It supports both populated ``STD_*`` tables and the
legacy ``Data`` sheet included in the approved Golden Model workbook.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd


MONTH_COUNT = 12


class WorkbookFormatError(ValueError):
    """Raised when a workbook cannot be converted without guessing."""


def _token(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    return re.sub(r"[\s_·ㆍ()\[\]{}:./-]+", "", str(value)).lower()


SHEET_ALIASES: dict[str, tuple[str, ...]] = {
    "data": ("Data", "DATA", "원본_Data", "원본데이터"),
    "sales": ("STD_판매", "표준_판매", "판매_STD"),
    "production": ("STD_생산", "표준_생산", "생산_STD"),
    "materials": ("STD_원부재료", "표준_원부재료", "원부재료_STD"),
    "manufacturing": ("STD_제조경비", "표준_제조경비", "제조경비_STD"),
    "sga": ("STD_판관비", "표준_판관비", "판관비_STD"),
}


@dataclass(frozen=True)
class WorkbookInspection:
    source_kind: str
    selected_sheets: tuple[str, ...]
    warnings: tuple[str, ...] = ()


class GoldenModelAdapter:
    """Convert workbook data to the frozen dashboard's legacy-shaped frame."""

    def read(self, payload: bytes, scenario_type: str | None = None) -> tuple[pd.DataFrame, WorkbookInspection]:
        excel = pd.ExcelFile(io.BytesIO(payload), engine="openpyxl")
        resolved = self._resolve_sheets(excel.sheet_names)

        standard = self._read_standard_tables(excel, resolved)
        if any(not frame.empty for frame in standard.values()):
            projection = self._project_standard(standard, scenario_type)
            return projection, WorkbookInspection("standard", tuple(resolved[k] for k in standard if k in resolved))

        data_sheet = resolved.get("data")
        if data_sheet is not None:
            frame = pd.read_excel(excel, sheet_name=data_sheet, header=None)
            if self._is_legacy_upload(frame):
                return frame, WorkbookInspection("legacy", (data_sheet,))
            projection, warnings = self._project_data(frame, scenario_type)
            return projection, WorkbookInspection("golden_data", (data_sheet,), tuple(warnings))

        first = pd.read_excel(excel, sheet_name=excel.sheet_names[0], header=None)
        if self._is_legacy_upload(first):
            return first, WorkbookInspection("legacy", (excel.sheet_names[0],))
        raise WorkbookFormatError("지원되는 Data 또는 STD_* 시트를 찾지 못했습니다.")

    @staticmethod
    def _resolve_sheets(sheet_names: Iterable[str]) -> dict[str, str]:
        by_token = {_token(name): name for name in sheet_names}
        resolved: dict[str, str] = {}
        for canonical, aliases in SHEET_ALIASES.items():
            for alias in aliases:
                if _token(alias) in by_token:
                    resolved[canonical] = by_token[_token(alias)]
                    break
        return resolved

    @staticmethod
    def _is_legacy_upload(frame: pd.DataFrame) -> bool:
        if frame.shape[1] < 15:
            return False
        labels = frame.iloc[:, 2:4].fillna("").astype(str)
        legacy_keys = ("제품매출입력", "SW수량입력", "영업이익입력")
        return any(labels.apply(lambda col: col.eq(key)).any(axis=None) for key in legacy_keys)

    @staticmethod
    def _read_standard_tables(excel: pd.ExcelFile, resolved: dict[str, str]) -> dict[str, pd.DataFrame]:
        tables: dict[str, pd.DataFrame] = {}
        for name in ("sales", "production", "materials", "manufacturing", "sga"):
            sheet = resolved.get(name)
            if sheet is None:
                tables[name] = pd.DataFrame()
                continue
            frame = pd.read_excel(excel, sheet_name=sheet, header=5)
            frame.columns = [str(column).strip() for column in frame.columns]
            frame = frame.dropna(how="all")
            if "scenario_id" in frame:
                frame = frame[frame["scenario_id"].notna()].copy()
            tables[name] = frame
        return tables

    def _project_standard(self, tables: dict[str, pd.DataFrame], scenario_type: str | None) -> pd.DataFrame:
        selected = {name: self._filter_scenario(frame, scenario_type) for name, frame in tables.items()}
        sales = selected["sales"]
        if sales.empty:
            raise WorkbookFormatError("선택한 시나리오의 STD_판매 데이터가 없습니다.")

        series: dict[str, np.ndarray] = {}
        groups = sales.get("product_group", pd.Series("", index=sales.index)).astype(str).str.upper()
        for group, key in (("SW", "SW수량입력"), ("BW", "BW수량입력"), ("LC", "LS수량입력"), ("FS", "FS수량입력")):
            subset = sales[groups.eq(group)]
            quantity_column = "sales_length" if group == "FS" and "sales_length" in subset else "sales_qty"
            series[key] = self._monthly(subset, quantity_column)
        for group, key in (("SW", "SW단가입력"), ("BW", "BW단가입력")):
            subset = sales[groups.eq(group)]
            amount = self._monthly(subset, "sales_amount_krw")
            quantity = self._monthly(subset, "sales_qty")
            series[key] = np.divide(amount, quantity, out=np.zeros(MONTH_COUNT), where=quantity != 0)

        series["제품매출입력"] = self._monthly(sales[groups.isin(["SW", "BW", "LC"])], "sales_amount_krw")
        series["반제품매출입력"] = self._monthly(sales[groups.eq("FS")], "sales_amount_krw")
        series["상품매출입력"] = self._monthly(sales[groups.isin(["신사업", "NEW_BIZ", "NEWBIZ"])], "sales_amount_krw")
        for key in ("기타매출입력", "판매장려금입력"):
            series[key] = np.zeros(MONTH_COUNT)

        materials = selected["materials"]
        manufacturing = selected["manufacturing"]
        names = manufacturing.get("account_name", pd.Series("", index=manufacturing.index)).astype(str)
        labor_mask = names.str.contains("급료|임금|상여|퇴직|노무", regex=True)
        outsource_mask = names.str.contains("외주가공비", regex=False)
        series["원부재료비입력"] = self._monthly(materials, "issue_amount")
        series["노무비입력"] = self._monthly(manufacturing[labor_mask], "manufacturing_amount")
        series["외주가공비입력"] = self._monthly(manufacturing[outsource_mask], "manufacturing_amount")
        series["기타경비입력"] = self._monthly(manufacturing[~labor_mask & ~outsource_mask], "manufacturing_amount")
        for key in ("반제품_원부재료비입력", "반제품_노무비입력", "반제품_외주가공비입력", "반제품_기타경비입력", "반제품매출원가입력", "상품매출원가입력", "기타매출원가입력", "표준원가차이입력", "재고평가손입력"):
            series[key] = np.zeros(MONTH_COUNT)

        sga = selected["sga"]
        sga_names = sga.get("account_name", pd.Series("", index=sga.index)).astype(str)
        account_map = {
            "일반관리비_인건비입력": "인건비", "일반관리비_감가상각비입력": "감가상각비",
            "일반관리비_경상개발비입력": "경상개발비", "일반관리비_수수료입력": "수수료",
            "판매비_운반비입력": "운반비", "판매비_브랜드사용료입력": "브랜드사용료",
            "판매비_견본비입력": "견본비", "판매비_대손상각입력": "대손상각", "판매비_잡비입력": "잡비",
        }
        allocated = np.zeros(MONTH_COUNT)
        for key, pattern in account_map.items():
            amount = self._monthly(sga[sga_names.str.contains(pattern, regex=False)], "sga_amount")
            series[key] = amount
            allocated += amount
        for key in ("판매비_수수료입력", "판매비_인건비입력", "판매비_기타입력"):
            series[key] = np.zeros(MONTH_COUNT)
        total_sga = self._monthly(sga, "sga_amount")
        series["일반관리비_기타입력"] = total_sga - allocated

        sales_total = sum((series[key] for key in ("제품매출입력", "반제품매출입력", "상품매출입력", "기타매출입력", "판매장려금입력")), np.zeros(MONTH_COUNT))
        cogs_total = sum((series[key] for key in ("원부재료비입력", "노무비입력", "외주가공비입력", "기타경비입력")), np.zeros(MONTH_COUNT))
        series["매출총이익입력"] = sales_total - cogs_total
        series["영업이익입력"] = series["매출총이익입력"] - total_sga
        series["조정영업이익입력"] = series["영업이익입력"].copy()
        return self._to_legacy_frame(series, money_is_krw=True)

    def _project_data(self, frame: pd.DataFrame, scenario_type: str | None) -> tuple[pd.DataFrame, list[str]]:
        anchor = self._find_anchor(frame, "★손익계산서")
        end = self._find_anchor(frame, "제품 매출원가 보정", start=anchor + 1, required=False) or min(len(frame), anchor + 100)
        block = frame.iloc[anchor:end]
        mask = self._scenario_mask(frame, scenario_type)
        warnings: list[str] = []

        def find_row(column: int, text: str, start: int = anchor, stop: int = end) -> int:
            target = _token(text)
            for idx in range(start, min(stop, len(frame))):
                if target in _token(frame.iat[idx, column]):
                    return idx
            raise WorkbookFormatError(f"Golden Model Data 블록에서 '{text}' 항목을 찾지 못했습니다.")

        def values(row: int, scale: float = 1.0) -> np.ndarray:
            result = pd.to_numeric(frame.iloc[row, 4:16], errors="coerce").fillna(0.0).to_numpy(dtype=float)
            if len(result) != MONTH_COUNT:
                raise WorkbookFormatError("Golden Model의 월 열을 12개 찾지 못했습니다.")
            return result * scale * mask

        rows: dict[str, int] = {}
        rows["제품매출입력"] = find_row(2, "1.제품 매출액")
        rows["반제품매출입력"] = find_row(2, "2.반제품 매출액")
        rows["상품매출입력"] = find_row(2, "3. 상품")
        rows["기타매출입력"] = find_row(2, "4. 기타 매출액")
        rows["판매장려금입력"] = find_row(2, "5. 판매장려금")
        rows["원부재료비입력"] = find_row(3, "원부재료", start=find_row(2, "1. 제품 매출원가"), stop=find_row(2, "2. 반제품 매출원가"))
        rows["노무비입력"] = find_row(3, "노무비", start=rows["원부재료비입력"] + 1, stop=find_row(2, "2. 반제품 매출원가"))
        rows["외주가공비입력"] = find_row(3, "외주가공비", start=rows["노무비입력"] + 1, stop=find_row(2, "2. 반제품 매출원가"))
        rows["기타경비입력"] = find_row(3, "기타경비", start=rows["외주가공비입력"] + 1, stop=find_row(2, "2. 반제품 매출원가"))
        semi_start = find_row(2, "2. 반제품 매출원가")
        semi_end = find_row(2, "3. 상품 매출원가")
        rows["반제품매출원가입력"] = semi_start
        for key, label in (("반제품_원부재료비입력", "원부재료"), ("반제품_노무비입력", "노무비"), ("반제품_외주가공비입력", "외주가공비"), ("반제품_기타경비입력", "기타경비")):
            rows[key] = find_row(3, label, start=semi_start, stop=semi_end)
        rows["상품매출원가입력"] = semi_end
        rows["기타매출원가입력"] = find_row(2, "4. 기타 매출원가", start=semi_end)
        rows["재고평가손입력"] = find_row(2, "5. 재고자산 평가손", start=semi_end)
        rows["매출총이익입력"] = find_row(2, "1. 매출 총이익")
        rows["영업이익입력"] = find_row(1, "Ⅴ. 영업이익")

        series = {key: values(row, 1000.0) for key, row in rows.items()}
        series["표준원가차이입력"] = np.zeros(MONTH_COUNT)
        series["조정영업이익입력"] = series["영업이익입력"].copy()

        # Product quantities and prices are resolved from the sales-management block.
        sales_anchor = self._find_anchor(frame, "★Type별 매출액", required=False)
        if sales_anchor is not None:
            sales_end = min(anchor, sales_anchor + 100)
            for group, qty_key, price_key in (("SW", "SW수량입력", "SW단가입력"), ("BW", "BW수량입력", "BW단가입력")):
                qty_row = find_row(2, group, start=sales_anchor, stop=sales_end)
                amount_row = qty_row + 1
                qty = values(qty_row)
                amount_krw = values(amount_row, 1000.0)
                series[qty_key] = qty
                series[price_key] = np.divide(amount_krw, qty, out=np.zeros(MONTH_COUNT), where=qty != 0)
        for key in ("SW수량입력", "BW수량입력", "SW단가입력", "BW단가입력"):
            series.setdefault(key, np.zeros(MONTH_COUNT))

        # P&L quantity rows are unambiguous within the statement block.
        product_sales_start = rows["제품매출입력"]
        semi_sales_start = rows["반제품매출입력"]
        series["LS수량입력"] = values(find_row(3, "LC", start=product_sales_start, stop=semi_sales_start))
        series["FS수량입력"] = values(find_row(3, "판매량(m)", start=semi_sales_start, stop=rows["상품매출입력"]))

        self._add_sga_projection(frame, series, mask)
        if not any(np.any(series[key]) for key in ("제품매출입력", "반제품매출입력", "매출총이익입력")):
            warnings.append("Data 시트의 주요 계산 셀에 저장된 값이 없습니다. Excel에서 수식 계산 후 저장한 파일인지 확인하세요.")
        return self._to_legacy_frame(series, money_is_krw=True), warnings

    def _add_sga_projection(self, frame: pd.DataFrame, series: dict[str, np.ndarray], mask: np.ndarray) -> None:
        anchor = self._find_anchor(frame, "★판매관리비 관리 명세서")
        sales_start = self._find_anchor(frame, "판매비", start=anchor + 1)
        admin_start = self._find_anchor(frame, "일반관리비", start=sales_start + 1)
        admin_end = self._find_anchor(frame, "판매관리비 계", start=admin_start + 1)

        def row_by_label(label: str, start: int, stop: int) -> int | None:
            target = _token(label)
            for idx in range(start, stop):
                if target == _token(frame.iat[idx, 2]):
                    return idx
            return None

        def amount(row: int | None) -> np.ndarray:
            if row is None:
                return np.zeros(MONTH_COUNT)
            return pd.to_numeric(frame.iloc[row, 4:16], errors="coerce").fillna(0.0).to_numpy(dtype=float) * 1000.0 * mask

        admin_map = {"일반관리비_인건비입력": "인건비", "일반관리비_감가상각비입력": "감가상각비", "일반관리비_경상개발비입력": "경상개발비", "일반관리비_수수료입력": "수수료"}
        admin_allocated = np.zeros(MONTH_COUNT)
        for key, label in admin_map.items():
            series[key] = amount(row_by_label(label, admin_start, admin_end))
            admin_allocated += series[key]
        admin_total = amount(self._find_anchor(frame, "일반관리비 계", start=admin_start + 1))
        series["일반관리비_기타입력"] = admin_total - admin_allocated

        sales_map = {"판매비_운반비입력": "운반비", "판매비_수수료입력": "수수료", "판매비_브랜드사용료입력": "브랜드사용료", "판매비_인건비입력": "인건비", "판매비_견본비입력": "견본비", "판매비_대손상각입력": "대손상각", "판매비_잡비입력": "잡비"}
        sales_allocated = np.zeros(MONTH_COUNT)
        for key, label in sales_map.items():
            series[key] = amount(row_by_label(label, sales_start, admin_start))
            sales_allocated += series[key]
        sales_total = amount(self._find_anchor(frame, "판매비 계", start=sales_start + 1))
        series["판매비_기타입력"] = sales_total - sales_allocated

    @staticmethod
    def _find_anchor(frame: pd.DataFrame, text: str, start: int = 0, required: bool = True) -> int | None:
        target = _token(text)
        for idx in range(start, len(frame)):
            if any(target in _token(value) for value in frame.iloc[idx, :4]):
                return idx
        if required:
            raise WorkbookFormatError(f"Golden Model Data 시트에서 '{text}' 블록을 찾지 못했습니다.")
        return None

    @staticmethod
    def _scenario_mask(frame: pd.DataFrame, scenario_type: str | None) -> np.ndarray:
        if scenario_type is None or frame.shape[0] < 3 or frame.shape[1] < 16:
            return np.ones(MONTH_COUNT)
        wanted = "actual" if _token(scenario_type) in {_token("actual"), _token("실적")} else "plan"
        aliases = {"actual": {_token("actual"), _token("실적")}, "plan": {_token("plan"), _token("계획"), _token("forecast"), _token("추정")}}
        headers = frame.iloc[2, 4:16]
        return np.array([1.0 if _token(value) in aliases[wanted] else 0.0 for value in headers], dtype=float)

    @staticmethod
    def _filter_scenario(frame: pd.DataFrame, scenario_type: str | None) -> pd.DataFrame:
        if frame.empty or scenario_type is None or "scenario_type" not in frame:
            return frame
        wanted = "actual" if _token(scenario_type) in {_token("actual"), _token("실적")} else "plan"
        actual = {_token("actual"), _token("실적")}
        plan = {_token("plan"), _token("계획"), _token("forecast"), _token("추정")}
        allowed = actual if wanted == "actual" else plan
        return frame[frame["scenario_type"].map(_token).isin(allowed)].copy()

    @staticmethod
    def _monthly(frame: pd.DataFrame, value_column: str) -> np.ndarray:
        result = np.zeros(MONTH_COUNT, dtype=float)
        if frame.empty or value_column not in frame or "year_month" not in frame:
            return result
        months = pd.to_datetime(frame["year_month"], errors="coerce")
        values = pd.to_numeric(frame[value_column], errors="coerce").fillna(0.0)
        grouped = values.groupby(months.dt.month).sum()
        for month, value in grouped.items():
            if pd.notna(month) and 1 <= int(month) <= MONTH_COUNT:
                result[int(month) - 1] = float(value)
        return result

    @staticmethod
    def _to_legacy_frame(series: dict[str, np.ndarray], money_is_krw: bool) -> pd.DataFrame:
        money_keys = {key for key in series if not any(token in key for token in ("수량", "단가"))}
        rows: list[list[object]] = []
        for key, values in series.items():
            numbers = np.asarray(values, dtype=float)
            if len(numbers) != MONTH_COUNT:
                raise WorkbookFormatError(f"{key}의 월별 값이 12개가 아닙니다.")
            if key in money_keys and not money_is_krw:
                numbers = numbers * 1000.0
            rows.append([None, None, key, None, *numbers.tolist()])
        return pd.DataFrame(rows)
