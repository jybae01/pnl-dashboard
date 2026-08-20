from __future__ import annotations

from collections.abc import Iterable
from collections.abc import Mapping
import re
from typing import Any

from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter


ACCOUNTING_FORMAT = '#,##0;[Red](#,##0);-'
QUANTITY_FORMAT = '#,##0.00;[Red](#,##0.00);-'
UNIT_COST_FORMAT = '#,##0.00;[Red](#,##0.00);-'
PERCENT_FORMAT = '0.00%;[Red](0.00%);-'
FX_FORMAT = '#,##0.0000;[Red](#,##0.0000);-'


_KOREAN_LABELS = {
    "Base": "기준(계획)",
    "Comparison": "비교(실적/추정)",
    "Base Source Reference": "기준 원천 위치",
    "Comparison Source Reference": "비교 원천 위치",
    "Base Source": "기준 원천 위치",
    "Comparison Source": "비교 원천 위치",
    "Base Freight(incl Tariff)": "기준 운반비(관세 포함)",
    "Comparison Freight(incl Tariff)": "비교 운반비(관세 포함)",
    "Base Freight(ex Tariff)": "기준 운반비(관세 제외)",
    "Comparison Freight(ex Tariff)": "비교 운반비(관세 제외)",
    "Base Tariff 포함?": "기준 관세 포함 여부",
    "Comparison Tariff 포함?": "비교 관세 포함 여부",
    "Business Source": "원천 항목",
    "Canonical field": "Canonical 필드",
    "Canonical Field": "Canonical 필드",
    "Source Reference": "원천 위치",
    "Calculation Source": "계산 기준",
    "Validation": "정합성 확인",
    "Calculation Validation": "계산 정합성",
    "Trace Validation": "추적 정합성",
    "Source Status": "원천 상태",
    "Engine Output": "Engine 결과",
    "Engine Value": "Engine 결과",
    "Evidence Formula": "근거 수식",
    "Excel Formula": "Excel 수식",
    "Formula Result": "수식 결과",
    "Difference": "차이",
    "Detail Cell": "상세 근거 셀",
    "Policy": "정책",
    "Effect": "효과",
    "Pool": "수량 Pool",
    "Effect Code": "효과 코드",
    "Period": "기간",
    "Product Group": "제품군",
    "Unit": "단위",
    "Selected": "적용 여부",
    "Scenario": "구분",
    "Month": "월",
    "Quantity Formula": "수량효과 수식",
    "Quantity Engine": "수량효과 Engine",
    "Mix Formula": "믹스효과 수식",
    "Mix Engine": "믹스효과 Engine",
    "Mix Component": "믹스 구성요소",
    "Base Total": "기준 총수량",
    "Comparison Total": "비교 총수량",
    "Base Weighted GP/unit": "기준 가중 GP/단위",
    "Base Quantity": "기준 수량",
    "Comparison Quantity": "비교 수량",
    "Pool Base Quantity": "Pool 기준 수량",
    "Pool Comparison Quantity": "Pool 비교 수량",
    "Base Mix": "기준 믹스",
    "Comparison Mix": "비교 믹스",
    "Base Core Manufactured COGS": "기준 핵심 제조품 COGS",
    "Base Core COGS/unit": "기준 핵심 COGS/단위",
    "Embedded Quantity COGS Expense": "수량에 포함된 COGS 비용",
    "Embedded Mix COGS Expense": "믹스에 포함된 COGS 비용",
    "Quantity Overlap OP": "수량 중복분(OP 부호)",
    "Mix Overlap OP": "믹스 중복분(OP 부호)",
    "Total Overlap OP": "총 중복분(OP 부호)",
    "Engine Quantity": "수량 중복 Engine",
    "Engine Mix": "믹스 중복 Engine",
    "Engine Total": "합계 Engine",
    "Base Quantity Source": "기준 수량 원천",
    "Comparison Quantity Source": "비교 수량 원천",
    "Base Core COGS Source": "기준 핵심 COGS 원천",
    "Comparison Core COGS Source": "비교 핵심 COGS 원천",
    "Rolling 3M Period": "최근 3개월 기간",
    "Engine Net": "최종 시차 Engine",
    "Direction": "방향",
    "Direction 수식": "방향 수식",
    "Persistence": "최근 추세",
    "Coverage": "데이터 범위",
    "Confidence": "신뢰도",
    "Materiality": "중요도",
    "Explanation Metadata": "설명 메타데이터",
    "Value": "값",
    "Applied Rule / Notes": "적용 규칙 / 설명",
    "Product Group": "제품군",
    "Specification": "규격",
    "Base Opening Unit Cost": "기준 기초재고 원단위",
    "Comparison Opening Unit Cost": "비교 기초재고 원단위",
    "Delta Formula": "차이 수식",
    "Aligned": "방향 일치",
    "Base Finished Goods COGS": "기준 제품 매출원가",
    "Comparison Finished Goods COGS": "비교 제품 매출원가",
    "Finished Goods COGS": "제품 매출원가",
    "Semi-finished Goods COGS": "반제품 매출원가",
    "Manufactured COGS": "제조품 매출원가",
    "Current Manufacturing Cost": "당기투입제조원가",
    "Manufactured COGS Effect": "제조품 매출원가 효과",
    "Current Manufacturing Cost Effect": "당기투입제조원가 효과",
    "Gross Inventory Timing": "중복 제거 전 재고·원가 반영시차",
    "Core Quantity COGS Overlap": "판매수량에 포함된 제조원가 중복분",
    "Core Mix COGS Overlap": "판매믹스에 포함된 제조원가 중복분",
    "Total Core Manufactured COGS Overlap": "판매효과 포함 제조원가 중복분",
    "Net Inventory Timing Effect": "최종 재고·원가 반영시차",
    "Core overlap policy": "핵심 제조원가 중복 제거 정책",
    "Double-count Validation": "중복계상 확인",
    "Formula Result": "수식 결과",
    "effects_total": "공식 효과 합계",
    "residual": "잔여차이(Residual)",
    "OP_delta": "영업이익 증감",
    "effects_total + residual = OP_delta": "공식 효과 합계 + 잔여차이 = 영업이익 증감",
    "Product Mix 효과": "제품 믹스 효과",
    "제품 Mix 효과": "제품 믹스 효과",
    "Manufacturing subtotal / child double count": "제조경비 합계 / 하위효과 중복 없음",
    "Inventory realization multiplier used": "재고실현율 계산 반영 여부",
    "Freight double count": "운반비 중복계상 없음",
    "Tariff separate": "관세 별도 유지",
    "Freight equivalent-shipment denominator": "운반비 환산 판매수량 검증",
    "RM / RM FX double count": "원부재료 / 환율효과 중복 없음",
    "JPY Source valid": "JPY 원천 유효",
    "Sales quantity source valid": "판매수량 원천 유효",
    "Scope Validation": "범위 정합성",
    "Base/Comparison": "기준/비교",
    "Used Value": "사용 값",
    "Calculation": "계산 기준",
    "Source value (no residual/OP backsolve)": "원천값(Residual/OP 역산 없음)",
    "Core Sales COGS double count removed": "판매 COGS 중복 제거 완료",
    "Core overlap counted in Quantity/Mix": "판매 수량·믹스에 중복분 포함",
    "Core overlap separately additive = FALSE": "중복분 별도 합산 안 함",
    "Gross Inventory Timing additive = FALSE": "중복 제거 전 시차 별도 합산 안 함",
    "Adjustment unitized = FALSE": "조정항목 단위배부 안 함",
    "Merchandise included in overlap = FALSE": "상품 COGS 중복분 제외",
    "row323 separate Effect = FALSE": "row323 별도 효과 없음",
}

_HEADER_PHRASES = (
    ("Comparison Source Reference", "비교 원천 위치"),
    ("Base Source Reference", "기준 원천 위치"),
    ("Comparison Source", "비교 원천"),
    ("Base Source", "기준 원천"),
    ("Business Source", "원천 항목"),
    ("Canonical Field", "Canonical 필드"),
    ("Canonical field", "Canonical 필드"),
    ("Source Reference", "원천 위치"),
    ("Engine Output", "Engine 결과"),
    ("Engine Value", "Engine 결과"),
    ("Engine", "Engine 결과"),
    ("Evidence Formula", "근거 수식"),
    ("Excel Formula", "Excel 수식"),
    ("Calculation Validation", "계산 정합성"),
    ("Trace Validation", "추적 정합성"),
    ("Validation", "정합성"),
    ("Comparison", "비교"),
    ("Base", "기준"),
    ("incl", "관세 포함"),
    ("ex", "관세 제외"),
    ("Front-process", "전공정"),
    ("Back-process", "후공정"),
    ("Front", "전공정"),
    ("Back", "후공정"),
    ("Freight", "운반비"),
    ("Tariff", "관세"),
    ("Price", "판매단가"),
    ("FX", "환율"),
    ("GP/unit", "GP/단위"),
    ("COGS/unit", "COGS/단위"),
    ("/unit", "/단위"),
    ("Volume", "조업도"),
    ("Fixed", "고정비"),
    ("Qty", "수량"),
    ("Length", "길이"),
    ("Amount", "금액"),
    ("Raw Material", "원부재료"),
    ("denominator", "배부기준"),
    ("Component", "구성요소"),
    ("Adjustment", "조정"),
    ("Sales", "판매"),
    ("Total", "합계"),
    ("Rate", "비율"),
    ("Difference", "차이"),
    ("Status", "상태"),
    ("Reference", "근거"),
    ("Quantity", "수량"),
    ("Mix", "믹스"),
    ("Unit Cost", "원단위"),
    ("Business", "업무"),
    ("Calculation", "계산"),
    ("Source", "원천"),
    ("Formula", "수식"),
    ("Effect", "효과"),
    ("Period", "기간"),
    ("Product Group", "제품군"),
    ("Scenario", "구분"),
    ("Unit", "단위"),
    ("Policy", "정책"),
)


def _localize_user_labels(ws) -> int:
    changed = 0
    for row in ws.iter_rows():
        for cell in row:
            value = cell.value
            if not isinstance(value, str) or value.startswith("="):
                continue
            replacement = _KOREAN_LABELS.get(value)
            if replacement is not None and replacement != value:
                cell.value = replacement
                changed += 1
                continue
            if cell.fill.fill_type == "solid" and cell.fill.fgColor.rgb in {
                "001F4E78", "1F4E78", "FF1F4E78",
            }:
                replacement = value
                for source, target in _HEADER_PHRASES:
                    replacement = replacement.replace(source, target)
                if replacement != value:
                    cell.value = replacement
                    changed += 1
    return changed


def _set_widths(ws, widths: dict[str, float]) -> None:
    for column, width in widths.items():
        ws.column_dimensions[column].width = width


def _hide_columns(ws, columns: Iterable[str]) -> None:
    for column in columns:
        dimension = ws.column_dimensions[column]
        dimension.hidden = True
        dimension.outlineLevel = 1


def _format_rows(ws, bounds: Any, formats: dict[int, str]) -> None:
    if not bounds:
        return
    start, end = (int(bounds[0]), int(bounds[1]))
    if start > end:
        return
    for row in range(start, end + 1):
        for column, number_format in formats.items():
            ws.cell(row, column).number_format = number_format


def _finish_user_sheet(
    ws,
    *,
    title_rows: str = "1:4",
    landscape: bool = True,
    fit_width: int = 1,
    zoom: int = 90,
) -> None:
    ws.sheet_view.showGridLines = False
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_setup.orientation = "landscape" if landscape else "portrait"
    ws.page_setup.fitToWidth = fit_width
    ws.page_setup.fitToHeight = 0
    ws.print_title_rows = title_rows
    ws.sheet_view.zoomScale = zoom
    ws.sheet_properties.outlinePr.summaryRight = True
    for row in ws.iter_rows():
        for cell in row:
            if cell.value is None:
                continue
            cell.alignment = Alignment(
                horizontal=cell.alignment.horizontal,
                vertical="center" if cell.row <= 4 else "top",
                wrap_text=True,
            )
    ws.row_dimensions[1].height = 25
    ws.row_dimensions[2].height = max(float(ws.row_dimensions[2].height or 15), 36)


def _polish_sales(ws, cells: dict[str, Any]) -> None:
    ws["A2"] = (
        "제품군 내부 SKU를 먼저 합산하고 PCS/LENGTH Pool별 수량·믹스를 계산합니다. "
        "고객 운반비는 판매단가 효과에 한 번만 포함하며 관세는 분리합니다."
    )
    ws.merge_cells("A2:AG2")
    ws["AI2"] = (
        "월별 단일 고객배송 운반비 Pool을 SW·BW·LC 판매 PCS와 FS 판매길이÷45의 "
        "총 환산 판매수량으로 원단위화합니다. (기준 원단위-비교 원단위)×비교 총 환산 "
        "판매수량을 판매단가 효과에 한 번만 반영합니다."
    )
    ws.merge_cells("AI2:BO2")
    _set_widths(ws, {
        "A": 12, "B": 18, "C": 18, "D": 13, "E": 22, "F": 18,
        "G": 22, "H": 22, "I": 14, "J": 14, "K": 18, "L": 18,
        "M": 18, "N": 18, "O": 16, "P": 14, "Q": 14, "R": 12,
        "S": 12, "T": 16, "U": 12, "V": 16, "W": 12, "X": 12,
        "Y": 16, "Z": 16, "AA": 16, "AB": 16, "AC": 18, "AD": 18,
        "AE": 18, "AF": 18, "AG": 12, "AI": 11, "AJ": 22, "AK": 22,
        "AL": 22, "AM": 18, "AN": 18, "AO": 16, "AP": 16, "AQ": 12,
        "AR": 12, "AS": 18, "AT": 18, "AU": 18, "AV": 18, "AW": 18,
        "AX": 18, "AY": 18, "AZ": 18, "BA": 18, "BB": 18, "BC": 14,
        "BD": 18, "BE": 18, "BF": 20, "BG": 20, "BH": 18, "BI": 18,
        "BJ": 22, "BK": 18, "BL": 18, "BM": 18, "BN": 28, "BO": 12,
    })
    _hide_columns(ws, (
        "E", "F", "G", "H", "AD", "AF", "AG", "AK", "AL", "AM", "AN",
        "AQ", "AR", "BO",
    ))
    _format_rows(ws, cells.get("detail_range"), {
        9: QUANTITY_FORMAT, 10: QUANTITY_FORMAT, 11: ACCOUNTING_FORMAT,
        12: ACCOUNTING_FORMAT, 13: ACCOUNTING_FORMAT, 14: ACCOUNTING_FORMAT,
        15: UNIT_COST_FORMAT, 16: QUANTITY_FORMAT, 17: QUANTITY_FORMAT,
        18: PERCENT_FORMAT, 19: PERCENT_FORMAT, 20: UNIT_COST_FORMAT,
        21: PERCENT_FORMAT, 22: UNIT_COST_FORMAT, 23: FX_FORMAT, 24: FX_FORMAT,
        25: UNIT_COST_FORMAT, 26: UNIT_COST_FORMAT, 27: UNIT_COST_FORMAT,
        28: UNIT_COST_FORMAT, 29: ACCOUNTING_FORMAT, 30: ACCOUNTING_FORMAT,
        31: ACCOUNTING_FORMAT, 32: ACCOUNTING_FORMAT,
    })
    _format_rows(ws, cells.get("pool_range"), {
        10: QUANTITY_FORMAT, 11: QUANTITY_FORMAT, 12: UNIT_COST_FORMAT,
        13: ACCOUNTING_FORMAT, 14: ACCOUNTING_FORMAT, 15: UNIT_COST_FORMAT,
        16: ACCOUNTING_FORMAT, 17: ACCOUNTING_FORMAT,
    })
    _format_rows(ws, cells.get("freight_range"), {
        **{column: ACCOUNTING_FORMAT for column in range(39, 47)},
        **{column: QUANTITY_FORMAT for column in range(47, 60)},
        60: UNIT_COST_FORMAT, 61: UNIT_COST_FORMAT,
        62: ACCOUNTING_FORMAT, 63: ACCOUNTING_FORMAT,
        64: ACCOUNTING_FORMAT, 65: ACCOUNTING_FORMAT,
    })
    _format_rows(ws, cells.get("summary_range"), {2: ACCOUNTING_FORMAT, 3: ACCOUNTING_FORMAT})
    ws.freeze_panes = "A5"
    _finish_user_sheet(ws, fit_width=2, zoom=75)


def _polish_material(ws, cells: dict[str, Any]) -> None:
    ws["A2"] = (
        "왼쪽은 부직포 제외 원부재료, 오른쪽은 부직포·JPY 원천과 계산입니다. "
        "원천값만 직접 기록하고 원단위·가격효과·환율효과·합계는 Excel 수식으로 계산합니다."
    )
    ws.merge_cells("A2:AS2")
    _set_widths(ws, {
        "A": 12, "B": 18, "C": 18, "D": 22, "E": 18, "F": 22,
        "G": 22, "H": 18, "I": 18, "J": 15, "K": 15, "L": 15,
        "M": 16, "N": 16, "O": 18, "P": 18, "Q": 12, "R": 16,
        "T": 12, "U": 22, "V": 18, "W": 22, "X": 22, "Y": 18,
        "Z": 18, "AA": 15, "AB": 15, "AC": 15, "AD": 12, "AE": 12,
        "AF": 16, "AG": 16, "AH": 18, "AI": 16, "AJ": 18, "AK": 18,
        "AL": 18, "AM": 18, "AN": 12, "AO": 16,
    })
    _hide_columns(ws, (
        "E", "F", "G", "P", "Q", "R", "V", "W", "X", "AK", "AM", "AN", "AO",
    ))
    _format_rows(ws, cells.get("detail_range"), {
        8: ACCOUNTING_FORMAT, 9: ACCOUNTING_FORMAT, 10: QUANTITY_FORMAT,
        11: QUANTITY_FORMAT, 12: QUANTITY_FORMAT, 13: UNIT_COST_FORMAT,
        14: UNIT_COST_FORMAT, 15: ACCOUNTING_FORMAT, 16: ACCOUNTING_FORMAT,
    })
    _format_rows(ws, cells.get("nonwoven_range"), {
        25: ACCOUNTING_FORMAT, 26: ACCOUNTING_FORMAT, 27: QUANTITY_FORMAT,
        28: QUANTITY_FORMAT, 29: QUANTITY_FORMAT, 30: FX_FORMAT, 31: FX_FORMAT,
        32: UNIT_COST_FORMAT, 33: UNIT_COST_FORMAT,
        **{column: ACCOUNTING_FORMAT for column in range(34, 40)},
    })
    _format_rows(ws, cells.get("summary_range"), {2: ACCOUNTING_FORMAT, 3: ACCOUNTING_FORMAT})
    ws.freeze_panes = "A5"
    _finish_user_sheet(ws, fit_width=2, zoom=80)


def _polish_manufacturing(ws, cells: dict[str, Any]) -> None:
    ws["A2"] = (
        "상단 생산 기준 → 제조경비 전·후공정 배부 → 생산량 분모 → 원단위 → 조업도·원단위·고정비 효과 순서로 읽습니다. "
        "PCS와 LENGTH(m)는 합산하지 않으며 재고실현율은 효과 계산에 사용하지 않습니다."
    )
    ws.merge_cells("A2:AO2")
    _set_widths(ws, {
        "A": 12, "B": 18, "C": 18, "D": 13, "E": 18, "F": 18,
        "G": 13, "H": 26, "I": 26, "J": 14, "K": 18, "L": 18,
        "M": 12, "N": 12, "O": 18, "P": 18, "Q": 18, "R": 18,
        "S": 16, "T": 16, "U": 16, "V": 16, "W": 16, "X": 16,
        "Y": 16, "Z": 16, "AA": 18, "AB": 18, "AC": 18, "AD": 18,
        "AE": 18, "AF": 18, "AG": 18, "AH": 18, "AI": 18, "AJ": 18,
        "AK": 18, "AL": 18, "AM": 12, "AN": 13, "AO": 20,
    })
    _hide_columns(ws, ("D", "E", "F", "G", "H", "L", "M", "N", "O", "P", "Q", "R", "AD", "AH", "AJ", "AL", "AN", "AO"))
    _format_rows(ws, cells.get("production_summary_range"), {
        2: QUANTITY_FORMAT, 3: QUANTITY_FORMAT, 5: QUANTITY_FORMAT, 6: QUANTITY_FORMAT,
    })
    _format_rows(ws, cells.get("detail_range"), {
        11: ACCOUNTING_FORMAT, 12: ACCOUNTING_FORMAT, 13: PERCENT_FORMAT,
        14: PERCENT_FORMAT, 15: ACCOUNTING_FORMAT, 16: ACCOUNTING_FORMAT,
        17: ACCOUNTING_FORMAT, 18: ACCOUNTING_FORMAT,
        19: QUANTITY_FORMAT, 20: QUANTITY_FORMAT, 21: QUANTITY_FORMAT,
        22: QUANTITY_FORMAT, 23: UNIT_COST_FORMAT, 24: UNIT_COST_FORMAT,
        25: UNIT_COST_FORMAT, 26: UNIT_COST_FORMAT,
        **{column: ACCOUNTING_FORMAT for column in range(27, 39)},
        40: PERCENT_FORMAT,
    })
    _format_rows(ws, cells.get("summary_range"), {2: ACCOUNTING_FORMAT, 3: ACCOUNTING_FORMAT})
    ws.freeze_panes = f"A{cells['detail_range'][0]}"
    _finish_user_sheet(ws)


def _polish_inventory(ws, cells: dict[str, Any]) -> None:
    ws["A2"] = (
        "제조품 매출원가와 당기투입제조원가의 차이에서 판매 수량·믹스에 이미 포함된 핵심 제조원가 중복분을 차감해 "
        "최종 재고·원가 반영시차를 계산합니다. 최근 3개월 추세는 최종 시차 기준입니다."
    )
    ws.merge_cells("A2:G2")
    _set_widths(ws, {
        "A": 28, "B": 18, "C": 18, "D": 20, "E": 18, "F": 14,
        "G": 32, "H": 15, "I": 15, "J": 20, "K": 18, "L": 14,
        "M": 14, "N": 20, "O": 20, "P": 18, "Q": 18, "R": 18,
        "S": 18, "T": 18, "U": 18, "V": 14, "W": 22, "X": 24,
        "Y": 22, "Z": 24,
    })
    _hide_columns(ws, ("S", "T", "U", "V", "W", "X", "Y", "Z"))
    for row in range(5, 18):
        for column in (2, 3, 4, 5):
            ws.cell(row, column).number_format = ACCOUNTING_FORMAT
    _format_rows(ws, cells.get("core_detail_range"), {
        6: QUANTITY_FORMAT, 7: QUANTITY_FORMAT, 8: QUANTITY_FORMAT,
        9: QUANTITY_FORMAT, 10: ACCOUNTING_FORMAT, 11: UNIT_COST_FORMAT,
        12: PERCENT_FORMAT, 13: PERCENT_FORMAT,
        **{column: ACCOUNTING_FORMAT for column in range(14, 22)},
    })
    _format_rows(ws, cells.get("rolling_range"), {
        **{column: ACCOUNTING_FORMAT for column in range(2, 14)},
    })
    _format_rows(ws, cells.get("opening_range"), {
        4: UNIT_COST_FORMAT, 5: UNIT_COST_FORMAT, 6: UNIT_COST_FORMAT,
    })
    ws.freeze_panes = "A5"
    _finish_user_sheet(ws)


def _polish_bridge(ws, cells: dict[str, Any]) -> None:
    ws["A2"] = (
        "상세 근거 시트의 최종 수식 셀을 직접 참조해 공식 효과, Residual, OP 증감을 검증합니다. "
        "중복 제거 전 시차와 핵심 제조원가 중복분은 별도 합산하지 않습니다."
    )
    ws.merge_cells("A2:G2")
    _set_widths(ws, {"A": 18, "B": 28, "C": 20, "D": 18, "E": 18, "F": 14, "G": 24})
    _hide_columns(ws, ("A", "G"))
    _format_rows(ws, cells.get("effect_range"), {
        3: ACCOUNTING_FORMAT, 4: ACCOUNTING_FORMAT, 5: ACCOUNTING_FORMAT,
    })
    _format_rows(ws, cells.get("summary_range"), {
        3: ACCOUNTING_FORMAT, 4: ACCOUNTING_FORMAT,
    })
    ws.freeze_panes = "B5"
    _finish_user_sheet(ws, landscape=False)


def polish_evidence_workbook(
    workbook,
    *,
    sales_cells: dict[str, Any],
    material_cells: dict[str, Any],
    manufacturing_cells: dict[str, Any],
    inventory_cells: dict[str, Any],
    bridge_cells: dict[str, Any],
) -> dict[str, float | int]:
    """Apply presentation-only polish without moving or replacing calculations."""
    key_sheets = {
        "판매효과_근거": lambda ws: _polish_sales(ws, sales_cells),
        "원부재료_근거": lambda ws: _polish_material(ws, material_cells),
        "제조경비_근거": lambda ws: _polish_manufacturing(ws, manufacturing_cells),
        "재고원가반영시차_근거": lambda ws: _polish_inventory(ws, inventory_cells),
        "최종Bridge_검증": lambda ws: _polish_bridge(ws, bridge_cells),
    }
    changed = 0
    for sheet_name, formatter in key_sheets.items():
        ws = workbook[sheet_name]
        changed += _localize_user_labels(ws)
        formatter(ws)
    return {
        "localized_cells": changed,
        "visible_width_total": sum(
            float(ws.column_dimensions[get_column_letter(column)].width or 0)
            for sheet_name in key_sheets
            for ws in (workbook[sheet_name],)
            for column in range(1, ws.max_column + 1)
            if not ws.column_dimensions[get_column_letter(column)].hidden
        ),
    }


# ---------------------------------------------------------------------------
# Slice C user-facing evidence sheets
# ---------------------------------------------------------------------------
#
# These helpers deliberately live beside the legacy polish code.  The legacy
# writer owns formula-bearing audit sheets; this section only writes readable
# views of values already present in ComparisonResult traces.  In particular,
# no value below is derived from persistence metadata or by repeating an
# Analysis/Comparison business formula.

_USER_HEADER_FILL = PatternFill("solid", fgColor="1F4E78")
_USER_SECTION_FILL = PatternFill("solid", fgColor="D9EAF7")
_USER_TOTAL_FILL = PatternFill("solid", fgColor="E2F0D9")
_USER_WHITE_FONT = Font(color="FFFFFF", bold=True)
_USER_BOLD = Font(bold=True)
_USER_BORDER = Border(bottom=Side(style="thin", color="B7C9D6"))


def _user_get(value: Any, key: str, default: Any = None) -> Any:
    if value is None:
        return default
    if isinstance(value, Mapping):
        return value.get(key, default)
    return getattr(value, key, default)


def _user_list(value: Any) -> list[Any]:
    if value is None or isinstance(value, (str, bytes)):
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    try:
        return list(value)
    except TypeError:
        return []


def _user_period_key(value: Any, year: str | None = None) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    match = re.search(r"(\d{4})[-/](\d{1,2})", text)
    if match:
        return f"{int(match.group(1)):04d}-{int(match.group(2)):02d}"
    if re.fullmatch(r"\d{1,2}", text) and year:
        return f"{int(year):04d}-{int(text):02d}"
    return text


def _user_selected_months(result: Any) -> list[str]:
    period = _user_get(result, "period", {})
    label = str(_user_get(period, "label", "") or "")
    year_match = re.search(r"(\d{4})", label)
    year = year_match.group(1) if year_match else None
    if year is None:
        for side in ("baseline", "comparison"):
            side_year = _user_get(_user_get(result, side, {}), "year")
            if side_year is not None:
                year = str(side_year)
                break
    values: list[str] = []
    for month in _user_list(_user_get(period, "months", ())):
        key = _user_period_key(month, year)
        if key and key not in values:
            values.append(key)
    if values:
        return values

    # Stored legacy results occasionally omit PeriodOption.months.  Derive a
    # display-only fallback from existing trace periods, preserving trace
    # order and never inventing a value for a missing month.
    candidates: list[Any] = []
    sales = _user_get(result, "sales_analysis", {})
    candidates.extend(_user_list(_user_get(sales, "monthly_effects", ())))
    candidates.extend(_user_list(_user_get(sales, "freight_trace_rows", ())))
    candidates.extend(_user_list(_user_get(result, "sga_monthly_trace", ())))
    for item in candidates:
        key = _user_period_key(_user_get(item, "period", _user_get(item, "month")), year)
        if key and key not in values:
            values.append(key)
    return values


def _user_rows_for_month(rows: Iterable[Any], month: str) -> list[Any]:
    return [
        row for row in rows
        if _user_period_key(_user_get(row, "period", _user_get(row, "month"))) == month
    ]


def _user_source(item: Any, *keys: str) -> Any:
    for key in keys:
        value = _user_get(item, key)
        if value is not None and value != "":
            return value
    return None


def _user_sum(values: Iterable[Any]) -> Any:
    numbers = [
        value for value in values
        if isinstance(value, (int, float)) and not isinstance(value, bool)
    ]
    return sum(numbers) if numbers else None


def _user_effect_map(result: Any) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for item in _user_list(_user_get(result, "effects", ())):
        code = _user_get(item, "code")
        if code is not None:
            output[str(code)] = item
    return output


def _user_effect_value(effect_map: Mapping[str, Any], code: str, fallback: Any = None) -> Any:
    item = effect_map.get(code)
    value = _user_get(item, "profit_effect")
    return fallback if value is None else value


def _user_number_format(header: Any) -> str | None:
    text = str(header or "").lower()
    if any(token in text for token in ("율", "비율", "rate", "%")):
        return PERCENT_FORMAT
    if "환율" in text or "fx" in text:
        return FX_FORMAT
    if any(token in text for token in ("수량", "pcs", "길이", "생산량", "output", "quantity")):
        return QUANTITY_FORMAT
    if any(token in text for token in ("원단위", "단가", "/pcs", "/m", "unit cost")):
        return UNIT_COST_FORMAT
    if any(token in text for token in ("금액", "매출", "cogs", "effect", "효과", "비용", "영업이익", "기준", "비교")):
        return ACCOUNTING_FORMAT
    return None


def _user_write_title(ws: Any, title: str, subtitle: str) -> int:
    ws["A1"] = title
    ws["A1"].font = Font(size=16, bold=True)
    ws["A2"] = subtitle
    ws["A2"].alignment = Alignment(wrap_text=True, vertical="top")
    ws["A3"] = None
    ws.row_dimensions[1].height = 26
    ws.row_dimensions[2].height = 38
    return 4


def _user_write_headers(ws: Any, row: int, headers: list[str]) -> None:
    for column, header in enumerate(headers, 1):
        cell = ws.cell(row, column, header)
        cell.fill = _USER_HEADER_FILL
        cell.font = _USER_WHITE_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = _USER_BORDER
    ws.auto_filter.ref = f"A{row}:{get_column_letter(len(headers))}{row}"
    ws.freeze_panes = f"A{row + 1}"
    ws.row_dimensions[row].height = 30


def _user_write_table(
    ws: Any,
    row: int,
    headers: list[str],
    values: Iterable[Iterable[Any]],
    *,
    total_rows: Iterable[int] = (),
) -> int:
    _user_write_headers(ws, row, headers)
    total_set = set(total_rows)
    current = row + 1
    for values_row in values:
        row_values = list(values_row)
        row_semantics = " ".join(
            str(value) for value in row_values[:2] if value not in (None, "")
        )
        row_number_format = _user_number_format(row_semantics)
        for column, value in enumerate(row_values, 1):
            cell = ws.cell(current, column, value)
            cell.alignment = Alignment(vertical="top", wrap_text=True)
            number_format = _user_number_format(headers[column - 1]) if column <= len(headers) else None
            if (
                column <= len(headers)
                and headers[column - 1] in {"기준", "비교", "값"}
                and row_number_format is not None
            ):
                number_format = row_number_format
            if number_format and isinstance(value, (int, float)) and not isinstance(value, bool):
                cell.number_format = number_format
            if current in total_set:
                cell.fill = _USER_TOTAL_FILL
                cell.font = _USER_BOLD
        current += 1
    return current


def _user_section(ws: Any, row: int, label: str, width: int) -> int:
    for column in range(1, max(width, 1) + 1):
        cell = ws.cell(row, column)
        cell.fill = _USER_SECTION_FILL
        cell.border = _USER_BORDER
        if column == 1:
            cell.value = label
            cell.font = _USER_BOLD
    return row + 1


def _user_finish_sheet(ws: Any, last_row: int, last_column: int, *, portrait: bool = False) -> None:
    if last_column > 1:
        ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=last_column)
    ws.row_dimensions[2].height = 42
    ws.sheet_view.showGridLines = False
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_setup.orientation = "portrait" if portrait else "landscape"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.print_title_rows = "1:4"
    ws.sheet_view.zoomScale = 90
    ws.freeze_panes = "B5" if last_column >= 8 else "A5"
    for row in ws.iter_rows(min_row=1, max_row=max(last_row, 1), min_col=1, max_col=max(last_column, 1)):
        for cell in row:
            if cell.value is not None:
                cell.alignment = Alignment(
                    horizontal=cell.alignment.horizontal,
                    vertical=cell.alignment.vertical or "top",
                    wrap_text=True,
                )
    for column in range(1, max(last_column, 1) + 1):
        letter = get_column_letter(column)
        max_length = 10
        for row in range(1, max(last_row, 1) + 1):
            value = ws.cell(row, column).value
            if value is not None:
                max_length = max(max_length, min(46, len(str(value)) + 2))
        ws.column_dimensions[letter].width = min(46, max_length)
    ws.print_area = f"A1:{get_column_letter(max(last_column, 1))}{max(last_row, 1)}"


def _user_create_sheet(workbook: Any, title: str) -> Any:
    if title in workbook.sheetnames:
        del workbook[title]
    return workbook.create_sheet(title)


def _user_pnl_value(result: Any, side: str, code: str) -> Any:
    for item in _user_list(_user_get(result, "pnl", ())):
        if str(_user_get(item, "code", "")) == code:
            return _user_get(item, side)
    side_pnl = _user_get(_user_get(result, side, {}), "pnl", {})
    if isinstance(side_pnl, Mapping):
        return side_pnl.get(code)
    return None


def _user_summary_sheet(workbook: Any, result: Any) -> Any:
    ws = _user_create_sheet(workbook, "분석요약")
    period = _user_get(result, "period", {})
    period_label = _user_get(period, "label")
    if period_label is None:
        months = _user_selected_months(result)
        period_label = " ~ ".join(months) if months else None
    header = _user_write_title(
        ws,
        "분석요약",
        "Engine / Comparison Result의 공식 Effect와 provenance를 사용자용으로 표시합니다. Evidence에서는 Business Formula를 재계산하지 않습니다.",
    )
    rows = [
        ["분석기간", period_label],
        ["기준 모형", _user_get(_user_get(result, "baseline", {}), "name")],
        ["비교 모형", _user_get(_user_get(result, "comparison", {}), "name")],
        ["기준 영업이익", _user_pnl_value(result, "baseline", "operating_profit")],
        ["비교 영업이익", _user_pnl_value(result, "comparison", "operating_profit")],
        ["영업이익 증감", _user_get(result, "operating_profit_delta")],
        ["공식 효과 합계", _user_get(result, "effects_total")],
        ["기타 요인", _user_get(result, "residual")],
    ]
    row = _user_write_table(ws, header, ["항목", "값"], rows)
    row += 1
    row = _user_section(ws, row, "효과 브리지", 5)

    sales = _user_get(result, "sales_analysis", {})
    sales_totals = _user_get(sales, "totals", {})
    effect_map = _user_effect_map(result)
    known = {
        "sales_quantity", "sales_mix", "sales_price", "sales_fx", "tariff",
        "material_total", "manufacturing_realized", "sga_variable", "sga_fixed",
        "inventory_timing",
    }
    bridge = [
        ("Quantity", _user_effect_value(effect_map, "sales_quantity", _user_get(sales_totals, "quantity_effect")), "판매수량 효과"),
        ("Mix", _user_effect_value(effect_map, "sales_mix", _user_get(sales_totals, "mix_effect")), "제품 Mix 효과"),
        ("Price", _user_effect_value(effect_map, "sales_price", _user_get(sales_totals, "sales_price_effect", _user_get(sales_totals, "pure_price_effect"))), "판매단가 효과(운반비는 하위 근거로 표시)"),
        ("Sales FX", _user_effect_value(effect_map, "sales_fx", _user_get(sales_totals, "sales_fx_effect")), "매출환율 효과"),
        ("Tariff", _user_effect_value(effect_map, "tariff", _user_get(sales_totals, "tariff_effect")), "최종 Analysis/Comparison 관세 Effect"),
        ("Raw Material", _user_effect_value(effect_map, "material_total", _user_get(_user_get(result, "material_analysis", {}), "total")), "원부재료 공식 Effect"),
        ("Manufacturing", _user_effect_value(effect_map, "manufacturing_realized"), "제조경비 공식 Effect"),
    ]
    sga_values = [
        _user_get(effect_map.get("sga_variable"), "profit_effect"),
        _user_get(effect_map.get("sga_fixed"), "profit_effect"),
    ]
    sga_value = _user_sum(sga_values)
    if sga_value is None:
        sga_value = _user_get(result, "sga")
    bridge.extend([
        ("SG&A", sga_value, "판관비 공식 Effect (고객배송 운반비는 판매효과에 반영)"),
        ("Inventory Timing", _user_effect_value(effect_map, "inventory_timing", _user_get(_user_get(result, "inventory_analysis", {}), "inventory_timing_effect")), "공식 Inventory Timing Effect"),
    ])
    for code, item in effect_map.items():
        if code not in known:
            bridge.append((str(_user_get(item, "factor", code)), _user_get(item, "profit_effect"), "현재 공식 Effect"))
    effect_rows = []
    for label, value, note in bridge:
        effect_rows.append([label, None, None, value, note])
    effects_total = _user_get(result, "effects_total")
    residual = _user_get(result, "residual")
    operating_profit_delta = _user_get(result, "operating_profit_delta")
    identity_status = None
    if all(
        isinstance(value, (int, float)) and not isinstance(value, bool)
        for value in (effects_total, residual, operating_profit_delta)
    ):
        tolerance = max(1.0, abs(float(operating_profit_delta)) * 1e-9)
        identity_status = (
            "PASS"
            if abs(float(effects_total) + float(residual) - float(operating_profit_delta))
            <= tolerance
            else "CHECK"
        )
    effect_rows.extend([
        ["공식 효과 합계", None, None, _user_get(result, "effects_total"), "Engine effects_total"],
        ["기타 요인", None, None, _user_get(result, "residual"), "Residual은 현재 정책상 기타 요인으로 표시"],
        ["영업이익 증감", None, None, _user_get(result, "operating_profit_delta"), "Comparison 영업이익 - Base 영업이익"],
        ["정합성", None, None, identity_status, "effects_total + 기타 요인 = 영업이익 증감"],
    ])
    row = _user_write_table(ws, row, ["효과", "기준", "비교", "Effect", "설명"], effect_rows)
    _user_finish_sheet(ws, row, 5)
    return ws


def _user_freight_rows(items: Iterable[Any], months: Iterable[str] | None = None) -> list[list[Any]]:
    selected = set(months or ())
    output: list[list[Any]] = []
    fields = (
        ("고객배송 운반비", "base_freight_ex_tariff", "comparison_freight_ex_tariff", "KRW", "월별 단일 운반비 Pool 금액"),
        ("SW 판매수량", "base_sw_pcs", "comparison_sw_pcs", "PCS", "SW 원천 판매수량(PCS)"),
        ("BW 판매수량", "base_bw_pcs", "comparison_bw_pcs", "PCS", "BW 원천 판매수량(PCS)"),
        ("LC 판매수량", "base_lc_pcs", "comparison_lc_pcs", "PCS", "LC 원천 판매수량(PCS)"),
        ("FS 판매길이", "base_fs_length", "comparison_fs_length", "LENGTH(m)", "FS 원천수량은 LENGTH(m)로 유지"),
        ("FS 환산기준", None, None, "", "운반비 분석에서만 45m = 1 환산 PCS; 원천 수량은 변경하지 않음"),
        ("FS 환산 판매수량", "base_fs_converted_pcs", "comparison_fs_converted_pcs", "환산 PCS", "FS LENGTH ÷ 45m/PCS"),
        ("총 환산 판매수량", "base_equivalent_shipment_quantity", "comparison_equivalent_shipment_quantity", "환산 PCS", "SW + BW + LC + FS 환산 PCS"),
        ("운반비 원단위", "base_freight_unit_cost", "comparison_freight_unit_cost", "KRW/PCS", "Engine trace의 운반비 원단위"),
        ("운반비 Effect", "freight_effect", "freight_effect", "KRW", "(기준 운반비 원단위 - 비교 운반비 원단위) × 비교 총 환산 판매수량"),
    )
    for item in items:
        month = _user_period_key(_user_get(item, "period"))
        if selected and month not in selected:
            continue
        source = _user_source(item, "base_source_reference", "comparison_source_reference", "base_quantity_source_reference", "comparison_quantity_source_reference")
        for label, base_key, comparison_key, unit, formula in fields:
            if label == "FS 환산기준":
                base_value = _user_get(item, "freight_conversion_basis", "45m/PCS")
                comparison_value = base_value
            elif label == "운반비 Effect":
                base_value = None
                comparison_value = None
            else:
                base_value = _user_get(item, base_key) if base_key else None
                comparison_value = _user_get(item, comparison_key) if comparison_key else None
            output.append([
                month,
                label,
                base_value,
                comparison_value,
                unit,
                _user_get(item, "freight_effect") if label == "운반비 Effect" else None,
                formula,
                source,
            ])
    return output


def _user_tariff_rows(items: Iterable[Any], months: Iterable[str] | None = None) -> list[list[Any]]:
    selected = set(months or ())
    output: list[list[Any]] = []
    fields = (
        ("지역매출 기준값", "base_tariff_regional_sales", "comparison_tariff_regional_sales", "금액/비중"),
        ("적용 비율", "base_tariff_applicable_rate", "comparison_tariff_applicable_rate", "%"),
        ("관세율", "base_tariff_rate", "comparison_tariff_rate", "%"),
        ("유효 관세율", "base_tariff_effective_rate", "comparison_tariff_effective_rate", "%"),
        ("관세 Effect", "tariff_effect", "tariff_effect", "KRW"),
    )
    for item in items:
        month = _user_period_key(_user_get(item, "period"))
        if selected and month not in selected:
            continue
        source = _user_source(item, "base_source_reference", "comparison_source_reference")
        for label, base_key, comparison_key, unit in fields:
            is_effect = label == "관세 Effect"
            output.append([
                month,
                label,
                None if is_effect else _user_get(item, base_key),
                None if is_effect else _user_get(item, comparison_key),
                unit,
                _user_get(item, "tariff_effect") if label == "관세 Effect" else None,
                "최종 Analysis/Comparison trace의 관세 정책 및 결과를 표시(여기서 재계산하지 않음)",
                source,
            ])
    return output


def _user_new_business_rows(items: Iterable[Any], months: Iterable[str] | None = None) -> list[list[Any]]:
    selected = set(months or ())
    output: list[list[Any]] = []
    fields = (
        ("수량", "base_quantity", "comparison_quantity", "PCS", "수량이 0이어도 Revenue/COGS 기반 2요소 Effect를 사용"),
        ("기준 매출액", "base_revenue", "comparison_revenue", "KRW", "신사업 매출액 원천값"),
        ("기준 COGS", "base_cogs", "comparison_cogs", "KRW", "신사업 COGS 원천값"),
        ("기준 GP율", "base_gp_rate", "comparison_gp_rate", "%", "기준/비교 GP율 Engine trace"),
        ("매출증가 효과", "revenue_effect", "revenue_effect", "KRW", "(비교 매출액 - 기준 매출액) × 기준 GP율"),
        ("GP율 변화 효과", "gp_rate_effect", "gp_rate_effect", "KRW", "비교 매출액 × (비교 GP율 - 기준 GP율)"),
        ("Quantity 반영금액", "revenue_effect", "revenue_effect", "KRW", "Revenue Growth Effect를 Quantity child로 표시"),
        ("Price 반영금액", "gp_rate_effect", "gp_rate_effect", "KRW", "GP Rate Change Effect를 Price child로 표시"),
        ("Mix 정책", "mix_effect", "mix_effect", "KRW", "신사업 정책상 Mix = 0"),
        ("Sales FX 정책", "sales_fx_effect", "sales_fx_effect", "KRW", "신사업 정책상 Sales FX = 0"),
    )
    for item in items:
        month = _user_period_key(_user_get(item, "period"))
        if selected and month not in selected:
            continue
        source = _user_source(item, "base_source_reference", "comparison_source_reference")
        for label, base_key, comparison_key, unit, formula in fields:
            is_effect = label in {
                "매출증가 효과", "GP율 변화 효과", "Quantity 반영금액",
                "Price 반영금액", "Mix 정책", "Sales FX 정책",
            }
            base_value = None if is_effect else _user_get(item, base_key)
            comparison_value = None if is_effect else _user_get(item, comparison_key)
            output.append([
                month,
                label,
                base_value,
                comparison_value,
                unit,
                _user_get(item, "revenue_effect") if label in {"매출증가 효과", "Quantity 반영금액"}
                else _user_get(item, "gp_rate_effect") if label in {"GP율 변화 효과", "Price 반영금액"}
                else _user_get(item, base_key) if label in {"Mix 정책", "Sales FX 정책"}
                else None,
                formula,
                source,
            ])
    return output


def _user_sales_sheet(workbook: Any, result: Any, months: list[str]) -> Any:
    ws = _user_create_sheet(workbook, "판매효과")
    sales = _user_get(result, "sales_analysis", {})
    sales_totals = _user_get(sales, "totals", {})
    row = _user_write_title(
        ws,
        "판매효과",
        "Quantity / Mix / Price / Sales FX는 월별 Engine 결과를 표시합니다. 운반비와 신사업은 하위 근거이며 상위 합계에 다시 더하지 않습니다.",
    )
    summary_rows = [
        ["Quantity", _user_get(sales_totals, "quantity_effect"), "공식 판매수량 효과"],
        ["Mix", _user_get(sales_totals, "mix_effect"), "공식 제품 Mix 효과"],
        ["Price", _user_get(sales_totals, "sales_price_effect", _user_get(sales_totals, "pure_price_effect")), "운반비 포함 판매단가 상위 Effect"],
        ["Sales FX", _user_get(sales_totals, "sales_fx_effect"), "공식 매출환율 효과"],
        ["운반비", _user_get(sales_totals, "transport_effect"), "Price의 child/sub-detail; 별도 가산하지 않음"],
        ["신사업 매출증가", _user_get(sales_totals, "new_business_revenue_effect"), "Quantity의 child"],
        ["신사업 GP율 변화", _user_get(sales_totals, "new_business_gp_rate_effect"), "Price의 child"],
        ["Tariff", _user_get(sales_totals, "tariff_effect"), "별도 관세 Effect"],
    ]
    row = _user_write_table(ws, row, ["항목", "Effect", "설명"], summary_rows)
    row += 1
    row = _user_section(ws, row, "월별 판매효과", 10)
    monthly = _user_list(_user_get(sales, "monthly_effects", ()))
    monthly_rows: list[list[Any]] = []
    for month in months:
        matched = _user_rows_for_month(monthly, month)
        if not matched:
            matched = [{}]
        for item in matched:
            monthly_rows.append([
                month,
                _user_get(item, "quantity_effect"),
                _user_get(item, "mix_effect"),
                _user_get(item, "sales_price_effect", _user_get(item, "displayed_price_effect")),
                _user_get(item, "sales_fx_effect"),
                _user_get(item, "freight_effect"),
                _user_get(item, "new_business_revenue_effect"),
                _user_get(item, "new_business_gp_rate_effect"),
                _user_get(item, "tariff_effect"),
                _user_get(item, "total_sales_effect"),
            ])
    row = _user_write_table(
        ws,
        row,
        ["월", "Quantity 효과", "Mix 효과", "Price 효과", "Sales FX 효과", "운반비 child", "신사업 매출증가 child", "신사업 GP율 변화 child", "관세 효과", "월별 판매효과 합계"],
        monthly_rows,
    )
    row += 1
    row = _user_section(ws, row, "운반비 근거", 8)
    row = _user_write_table(
        ws,
        row,
        ["월", "항목", "기준", "비교", "단위", "Effect", "근거 Formula 설명", "Source reference"],
        _user_freight_rows(_user_list(_user_get(sales, "freight_trace_rows", ())), months),
    )
    row += 1
    row = _user_section(ws, row, "관세 근거", 8)
    row = _user_write_table(
        ws,
        row,
        ["월", "항목", "기준", "비교", "단위", "Effect", "근거 Formula 설명", "Source reference"],
        _user_tariff_rows(_user_list(_user_get(sales, "freight_trace_rows", ())), months),
    )
    row += 1
    row = _user_section(ws, row, "신사업 근거", 8)
    row = _user_write_table(
        ws,
        row,
        ["월", "항목", "기준", "비교", "단위", "Effect", "근거 Formula 설명", "Source reference"],
        _user_new_business_rows(_user_list(_user_get(sales, "new_business_trace_rows", ())), months),
    )
    _user_finish_sheet(ws, row, 10)
    return ws


def _user_merchandise_sheet(workbook: Any, result: Any, months: list[str]) -> Any:
    ws = _user_create_sheet(workbook, "상품원가산출")
    scope = _user_get(result, "sales_cogs_scope_analysis", {})
    source_rows = _user_list(_user_get(scope, "source_rows", ()))
    row = _user_write_title(
        ws,
        "상품원가산출",
        "Comparison Result가 제공한 월별 Source만 표시합니다. Forecast 직접지정 상세가 Result에 없으면 값을 만들지 않고 미제공으로 표시합니다.",
    )
    rows: list[list[Any]] = []
    for item in source_rows:
        month = _user_period_key(_user_get(item, "period"))
        if months and month not in set(months):
            continue
        basis = (
            "Comparison Result 월별 상품원가 Source"
            if _user_get(item, "base_merchandise_cogs") is not None
            or _user_get(item, "comparison_merchandise_cogs") is not None
            else None
        )
        rows.append([
            month,
            _user_get(item, "product_group"),
            _user_get(item, "base_sales_product_cogs"),
            _user_get(item, "comparison_sales_product_cogs"),
            basis,
            _user_get(item, "base_merchandise_cogs"),
            _user_get(item, "comparison_merchandise_cogs"),
            _user_get(item, "base_sales_adjustment"),
            _user_get(item, "comparison_sales_adjustment"),
            _user_get(item, "merchandise_cogs_effect"),
            "Source 상품원가 값만 표시; Forecast 직접지정 상세 없음" if not any(
                _user_get(item, key) is not None
                for key in ("base_forecast_revenue", "comparison_forecast_revenue", "base_manual_override", "comparison_manual_override", "base_forecast_merchandise_cogs", "comparison_forecast_merchandise_cogs")
            ) else "Source row에 존재하는 authoritative 값만 표시",
            _user_source(item, "base_source_reference", "comparison_source_reference"),
        ])
    row = _user_write_table(
        ws,
        row,
        ["월", "제품군", "Sales Product COGS(기준)", "Sales Product COGS(비교)", "적용 상품원가 기준", "Source 상품원가(기준)", "Source 상품원가(비교)", "Sales COGS 범위조정(기준)", "Sales COGS 범위조정(비교)", "상품원가 Effect", "적용 의미", "Source reference"],
        rows,
    )
    row += 1
    row = _user_section(ws, row, "표시 정책", 3)
    row = _user_write_table(
        ws,
        row,
        ["항목", "내용", "근거"],
        [["Forecast 직접지정 상세", "Source trace에 authoritative 월별 상세가 없으면 표시하지 않음", "가짜 기본값/직접지정 값을 생성하지 않음"],
         ["직접 지정 최종 상품원가", "Source trace에 값이 있을 때만 원 의미 그대로 표시", "delta 또는 조정액으로 재해석하지 않음"]],
    )
    _user_finish_sheet(ws, row, 12)
    return ws


def _user_material_sheet(workbook: Any, result: Any, months: list[str]) -> Any:
    ws = _user_create_sheet(workbook, "원재료")
    material = _user_get(result, "material_analysis", {})
    row = _user_write_title(
        ws,
        "원재료",
        "원부재료 Engine trace를 월별·제품군별로 표시합니다. 부직포는 순수 가격효과와 JPY 환율효과를 분리해 표시합니다.",
    )
    row = _user_section(ws, row, "원부재료 월별 근거", 10)
    trace_rows = []
    for item in _user_list(_user_get(material, "trace_rows", ())):
        month = _user_period_key(_user_get(item, "period"))
        if months and month not in set(months):
            continue
        trace_rows.append([
            month,
            _user_get(item, "product_group"),
            _user_get(item, "base_cost"),
            _user_get(item, "comparison_cost"),
            _user_get(item, "base_unit_cost"),
            _user_get(item, "comparison_unit_cost"),
            _user_get(item, "comparison_sales"),
            _user_get(item, "total_effect"),
            "(기준 원단위 - 비교 원단위) × 비교 사용 수량",
            _user_source(item, "base_source_reference", "comparison_source_reference"),
        ])
    row = _user_write_table(
        ws,
        row,
        ["월", "제품군/구분", "기준 금액", "비교 금액", "기준 원단위", "비교 원단위", "사용 수량", "Effect", "근거 Formula 설명", "Source reference"],
        trace_rows,
    )
    row += 1
    row = _user_section(ws, row, "부직포 / JPY 월별 근거", 13)
    nonwoven_rows = []
    for item in _user_list(_user_get(material, "nonwoven_trace_rows", ())):
        month = _user_period_key(_user_get(item, "period"))
        if months and month not in set(months):
            continue
        nonwoven_rows.append([
            month,
            _user_get(item, "base_cost"),
            _user_get(item, "comparison_cost"),
            _user_get(item, "base_output"),
            _user_get(item, "comparison_output"),
            _user_get(item, "comparison_input_length"),
            _user_get(item, "base_unit_cost"),
            _user_get(item, "comparison_unit_cost"),
            _user_get(item, "base_jpy_fx"),
            _user_get(item, "comparison_jpy_fx"),
            _user_get(item, "nonwoven_price_ex_fx"),
            _user_get(item, "nonwoven_jpy"),
            _user_get(item, "nonwoven_total"),
            "부직포 총효과 = 순수 가격효과 + JPY 환율효과",
            _user_source(item, "base_source_reference", "comparison_source_reference"),
        ])
    row = _user_write_table(
        ws,
        row,
        ["월", "기준 금액", "비교 금액", "기준 생산길이", "비교 생산길이", "비교 투입길이", "기준 원단위", "비교 원단위", "기준 JPY 환율", "비교 JPY 환율", "순수 가격효과", "JPY 환율효과", "부직포 총효과", "근거 Formula 설명", "Source reference"],
        nonwoven_rows,
    )
    row += 1
    row = _user_section(ws, row, "기간 공식 Effect", 4)
    row = _user_write_table(
        ws,
        row,
        ["항목", "Effect", "설명", "Source"],
        [["원부재료 총효과", _user_get(material, "total"), "Engine 공식 기간 Effect", "Source Detail / RAW_MATERIAL"],
         ["부직포 순수 가격효과", _user_get(material, "nonwoven_price_ex_fx"), "Engine trace 합계", "Source Detail / NONWOVEN"],
         ["부직포 JPY 환율효과", _user_get(material, "nonwoven_jpy"), "Engine trace 합계", "Source Detail / NONWOVEN"]],
    )
    _user_finish_sheet(ws, row, 15)
    return ws


def _user_manufacturing_sheet(workbook: Any, result: Any, months: list[str]) -> Any:
    ws = _user_create_sheet(workbook, "제조경비")
    manufacturing = _user_get(result, "manufacturing_analysis", {})
    selected = set(months)
    row = _user_write_title(
        ws,
        "제조경비",
        "전공정·후공정별 제조경비 trace를 표시합니다. PCS와 LENGTH(m)는 서로 합산하지 않으며 realization multiplier는 재도입하지 않습니다.",
    )
    row = _user_section(ws, row, "월별 생산량 참조", 6)
    production = _user_list(_user_get(manufacturing, "production_reconciliation", ()))
    manufacturing_trace = _user_list(_user_get(manufacturing, "trace_rows", ()))
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for item in production:
        month = _user_period_key(_user_get(item, "month"))
        if selected and month not in selected:
            continue
        group = str(_user_get(item, "product_group", ""))
        key = (month, group)
        grouped.setdefault(key, {})[str(_user_get(item, "scenario", ""))] = item
    production_rows = []
    for (month, group), sides in grouped.items():
        base = sides.get("base", {})
        comparison = sides.get("comparison", {})
        unit = "LENGTH(m)" if group == "FS" else "PCS"
        quantity_key = "sap_length" if group == "FS" else "sap_qty"
        month_trace = next(
            (
                item for item in manufacturing_trace
                if _user_period_key(_user_get(item, "month")) == month
            ),
            {},
        )
        source_prefix = "front" if group == "FS" else "back"
        production_rows.append([
            month,
            group,
            unit,
            _user_get(base, quantity_key),
            _user_get(comparison, quantity_key),
            _user_get(month_trace, f"base_{source_prefix}_activity_source"),
            _user_get(month_trace, f"comparison_{source_prefix}_activity_source"),
        ])
    row = _user_write_table(
        ws,
        row,
        ["월", "제품군", "단위", "기준 생산량", "비교 생산량", "기준 Source", "비교 Source"],
        production_rows,
    )
    row += 1
    row = _user_section(ws, row, "전공정 / 후공정 Effect", 10)
    detail_rows = []
    for item in _user_list(_user_get(manufacturing, "trace_rows", ())):
        month = _user_period_key(_user_get(item, "month"))
        if selected and month not in selected:
            continue
        for process, prefix in (("전공정", "front"), ("후공정", "back")):
            detail_rows.append([
                month,
                process,
                _user_get(item, "account"),
                _user_get(item, f"base_{prefix}_allocated", _user_get(item, "baseline_amount")),
                _user_get(item, f"comparison_{prefix}_allocated", _user_get(item, "comparison_amount")),
                _user_get(item, f"base_{prefix}_activity"),
                _user_get(item, f"comparison_{prefix}_activity"),
                _user_get(item, f"{prefix}_activity"),
                _user_get(item, f"{prefix}_unit"),
                _user_get(item, f"{prefix}_fixed"),
                None,
                _user_get(item, "calculation_status"),
                _user_source(item, "base_amount_source", "comparison_amount_source"),
            ])
        detail_rows.append([
            month,
            "계정 합계",
            _user_get(item, "account"),
            _user_get(item, "baseline_amount"),
            _user_get(item, "comparison_amount"),
            None,
            None,
            None,
            None,
            None,
            _user_get(item, "occurrence_effect"),
            "공정별 상세 Effect를 중복 가산하지 않고 계정 합계에 1회 표시",
            _user_source(item, "base_amount_source", "comparison_amount_source"),
        ])
    row = _user_write_table(
        ws,
        row,
        ["월", "공정", "계정", "기준 금액", "비교 금액", "기준 생산량", "비교 생산량", "조업도 효과", "원단위 효과", "고정비 효과", "Effect", "설명", "Source reference"],
        detail_rows,
    )
    row += 1
    row = _user_section(ws, row, "기간 공식 Effect", 3)
    row = _user_write_table(
        ws,
        row,
        ["항목", "Effect", "설명"],
        [["제조경비 발생효과", _user_get(manufacturing, "occurrence_effect", _user_get(manufacturing, "occurrence_total")), "Engine manufacturing_analysis occurrence Effect"],
         ["제조경비 반영효과", _user_get(manufacturing, "final_effect", _user_get(manufacturing, "realized_total")), "Engine authoritative result(실현율은 참고지표)"]],
    )
    _user_finish_sheet(ws, row, 13)
    return ws


def _user_sga_sheet(workbook: Any, result: Any, months: list[str]) -> Any:
    ws = _user_create_sheet(workbook, "판관비")
    trace_rows = _user_list(_user_get(result, "sga_monthly_trace", ()))
    selected = set(months)
    row = _user_write_title(
        ws,
        "판관비",
        "판관비 월별 provenance를 보존한 사용자 표입니다. 고객배송 운반비는 판매효과에서 반영하고 판관비 Effect는 0으로 표시합니다.",
    )
    rows: list[list[Any]] = []
    for item in trace_rows:
        month = _user_period_key(_user_get(item, "period", _user_get(item, "month")))
        if selected and month not in selected:
            continue
        classification = str(_user_get(item, "classification", "") or "")
        is_transport = classification == "transport" or _user_get(item, "bridge_position") == "판매효과"
        note = "판매단가 효과에서 반영" if is_transport else _user_get(item, "bridge_position")
        rows.append([
            month,
            "판매" if str(_user_get(item, "section", "")) == "판매비" else "일반",
            _user_get(item, "display_account", _user_get(item, "account")),
            _user_get(item, "base_amount", _user_get(item, "baseline_amount")),
            _user_get(item, "comparison_amount"),
            _user_get(item, "profit_effect"),
            note,
            _user_source(item, "base_source_reference", "comparison_source_reference", "source_reference"),
        ])
    if not rows:
        # Keep the user sheet useful for a legacy aggregate-only result while
        # making the missing monthly provenance explicit.
        for item in _user_list(_user_get(result, "sga_accounts", ())):
            rows.append([
                None,
                "판매" if str(_user_get(item, "section", "")) == "판매비" else "일반",
                _user_get(item, "account"),
                _user_get(item, "baseline_amount"),
                _user_get(item, "comparison_amount"),
                _user_get(item, "profit_effect"),
                "월별 provenance 미제공(aggregate compatibility 값)",
                None,
            ])
    row = _user_write_table(
        ws,
        row,
        ["월", "구분", "계정", "기준", "비교", "Effect", "비고", "Source reference"],
        rows,
    )
    row += 1
    row = _user_section(ws, row, "판관비 기간 합계", 4)
    effect_map = _user_effect_map(result)
    variable = _user_effect_value(effect_map, "sga_variable", _user_get(result, "sga_variable"))
    fixed = _user_effect_value(effect_map, "sga_fixed", _user_get(result, "sga_fixed"))
    row = _user_write_table(
        ws,
        row,
        ["항목", "Effect", "설명", "Source"],
        [["변동 판관비", variable, "Engine 공식 Effect", "Source Detail / SGA"],
         ["고정 판관비", fixed, "Engine 공식 Effect", "Source Detail / SGA"]],
    )
    _user_finish_sheet(ws, row, 8)
    return ws


def _user_inventory_sheet(workbook: Any, result: Any, months: list[str]) -> Any:
    ws = _user_create_sheet(workbook, "Inventory Timing")
    inventory = _user_get(result, "inventory_analysis", {})
    details = _user_list(_user_get(inventory, "selected_monthly_details", ()))
    if not details:
        details = _user_list(_user_get(inventory, "monthly_details", ()))
    selected = set(months)
    row = _user_write_title(
        ws,
        "Inventory Timing",
        "공식 Inventory Timing Effect와 월별 Source를 표시합니다. Rolling 3M은 보조 설명이며 공식 additive Effect와 분리합니다.",
    )
    row = _user_section(ws, row, "월별 공식 근거", 10)
    detail_rows = []
    for item in details:
        month = _user_period_key(_user_get(item, "period"))
        if selected and month not in selected:
            continue
        detail_rows.append([
            month,
            _user_get(item, "base_manufactured_cogs"),
            _user_get(item, "comparison_manufactured_cogs"),
            _user_get(item, "manufactured_cogs_effect"),
            _user_get(item, "base_current_manufacturing_cost"),
            _user_get(item, "comparison_current_manufacturing_cost"),
            _user_get(item, "current_manufacturing_cost_effect"),
            _user_get(item, "gross_inventory_timing_effect"),
            _user_get(item, "core_manufactured_cogs_overlap_effect"),
            _user_get(item, "inventory_timing_effect"),
            _user_get(item, "source_reference"),
        ])
    row = _user_write_table(
        ws,
        row,
        ["월", "기준 Manufactured COGS", "비교 Manufactured COGS", "Manufactured COGS Effect", "기준 Current Manufacturing Cost", "비교 Current Manufacturing Cost", "Current Cost Effect", "Gross Inventory Timing", "Core overlap", "공식 Inventory Timing Effect", "Source reference"],
        detail_rows,
    )
    row += 1
    row = _user_section(ws, row, "기간 공식 Effect", 4)
    row = _user_write_table(
        ws,
        row,
        ["항목", "Effect", "설명", "Source"],
        [["Manufactured COGS", _user_get(inventory, "manufactured_cogs_effect"), "Engine trace", "Source Detail / INVENTORY_TIMING"],
         ["Current Manufacturing Cost", _user_get(inventory, "current_manufacturing_cost_effect"), "Engine trace", "Source Detail / INVENTORY_TIMING"],
         ["공식 Inventory Timing", _user_get(inventory, "inventory_timing_effect"), "Gross - authoritative core overlap; Engine 결과 표시", "Source Detail / INVENTORY_TIMING"]],
    )
    row += 1
    row = _user_section(ws, row, "보조 설명", 3)
    row = _user_write_table(
        ws,
        row,
        ["항목", "내용", "구분"],
        [["Rolling 3M", _user_get(inventory, "persistence"), "보조 설명(공식 Effect 아님)"],
         ["Primary / Confidence", f"{_user_get(inventory, 'primary')} / {_user_get(inventory, 'confidence')}", "보조 provenance"]],
    )
    _user_finish_sheet(ws, row, 11)
    return ws


def _user_common_detail_rows(
    label: str,
    base: Any = None,
    comparison: Any = None,
    formula: Any = None,
    effect: Any = None,
    source: Any = None,
) -> list[Any]:
    return [label, base, comparison, formula, effect, source]


def _user_month_detail_sheet(workbook: Any, result: Any, month: str) -> Any:
    title = f"{month} 상세"
    ws = _user_create_sheet(workbook, title)
    sales = _user_get(result, "sales_analysis", {})
    material = _user_get(result, "material_analysis", {})
    manufacturing = _user_get(result, "manufacturing_analysis", {})
    inventory = _user_get(result, "inventory_analysis", {})
    scope = _user_get(result, "sales_cogs_scope_analysis", {})
    sga_rows = _user_rows_for_month(_user_list(_user_get(result, "sga_monthly_trace", ())), month)
    sales_monthly = _user_rows_for_month(_user_list(_user_get(sales, "monthly_effects", ())), month)
    freight = _user_rows_for_month(_user_list(_user_get(sales, "freight_trace_rows", ())), month)
    new_business = _user_rows_for_month(_user_list(_user_get(sales, "new_business_trace_rows", ())), month)
    raw_material = _user_rows_for_month(_user_list(_user_get(material, "trace_rows", ())), month)
    nonwoven = _user_rows_for_month(_user_list(_user_get(material, "nonwoven_trace_rows", ())), month)
    manufacturing_rows = _user_rows_for_month(_user_list(_user_get(manufacturing, "trace_rows", ())), month)
    inventory_rows = _user_rows_for_month(
        _user_list(_user_get(inventory, "selected_monthly_details", ()))
        or _user_list(_user_get(inventory, "monthly_details", ())),
        month,
    )
    merchandise = _user_rows_for_month(_user_list(_user_get(scope, "source_rows", ())), month)
    row = _user_write_title(
        ws,
        title,
        "해당 월의 authoritative Engine / Comparison trace를 한 화면에 모았습니다. 값이 없는 항목은 추정하지 않고 비워 둡니다.",
    )
    headers = ["항목", "기준", "비교", "근거 Formula 설명", "Effect", "Source reference"]

    def write_section(section_label: str, values: list[list[Any]]) -> None:
        nonlocal row
        row = _user_section(ws, row, section_label, len(headers))
        if not values:
            values = [_user_common_detail_rows(
                f"{section_label} authoritative trace 없음",
                formula="해당 월 Source/Engine trace 미제공; 값 추정 없음",
            )]
        row = _user_write_table(ws, row, headers, values)
        row += 1

    sales_values = []
    for item in sales_monthly:
        sales_values.append(_user_common_detail_rows(
            "Quantity / Mix / Price / Sales FX",
            formula="월별 sales_analysis.monthly_effects Engine 결과",
            effect=_user_get(item, "total_sales_effect"),
            source="Source Detail / SALES",
        ))
    write_section("판매효과", sales_values)

    freight_values = []
    for item in freight:
        freight_values.extend([
            _user_common_detail_rows("고객배송 운반비", _user_get(item, "base_freight_ex_tariff"), _user_get(item, "comparison_freight_ex_tariff"), "월별 단일 freight pool 금액", source=_user_source(item, "base_source_reference", "comparison_source_reference")),
            _user_common_detail_rows("SW 판매수량(PCS)", _user_get(item, "base_sw_pcs"), _user_get(item, "comparison_sw_pcs"), "SW 원천수량 PCS", source=_user_source(item, "base_quantity_source_reference", "comparison_quantity_source_reference")),
            _user_common_detail_rows("BW 판매수량(PCS)", _user_get(item, "base_bw_pcs"), _user_get(item, "comparison_bw_pcs"), "BW 원천수량 PCS", source=_user_source(item, "base_quantity_source_reference", "comparison_quantity_source_reference")),
            _user_common_detail_rows("LC 판매수량(PCS)", _user_get(item, "base_lc_pcs"), _user_get(item, "comparison_lc_pcs"), "LC 원천수량 PCS", source=_user_source(item, "base_quantity_source_reference", "comparison_quantity_source_reference")),
            _user_common_detail_rows("FS 판매길이(LENGTH m)", _user_get(item, "base_fs_length"), _user_get(item, "comparison_fs_length"), "FS 원천수량 LENGTH(m) 유지", source=_user_source(item, "base_quantity_source_reference", "comparison_quantity_source_reference")),
            _user_common_detail_rows("FS /45 환산 PCS", _user_get(item, "base_fs_converted_pcs"), _user_get(item, "comparison_fs_converted_pcs"), "운반비 분석에서만 45m = 1 환산 PCS", source=_user_source(item, "base_quantity_source_reference", "comparison_quantity_source_reference")),
            _user_common_detail_rows("총 환산 판매수량", _user_get(item, "base_equivalent_shipment_quantity"), _user_get(item, "comparison_equivalent_shipment_quantity"), "SW + BW + LC + FS 환산 PCS", source=_user_source(item, "base_quantity_source_reference", "comparison_quantity_source_reference")),
            _user_common_detail_rows("운반비 원단위", _user_get(item, "base_freight_unit_cost"), _user_get(item, "comparison_freight_unit_cost"), "Engine trace 원단위", source=_user_source(item, "base_source_reference", "comparison_source_reference")),
            _user_common_detail_rows("운반비 Effect", formula="(기준 운반비 원단위 - 비교 운반비 원단위) × 비교 총 환산 판매수량", effect=_user_get(item, "freight_effect"), source=_user_source(item, "base_source_reference", "comparison_source_reference")),
        ])
    write_section("운반비", freight_values)

    tariff_values = []
    for item in freight:
        tariff_values.extend([
            _user_common_detail_rows("지역매출 적용 정책", _user_get(item, "base_tariff_regional_sales"), _user_get(item, "comparison_tariff_regional_sales"), "최종 tariff trace의 지역매출 정책", source=_user_source(item, "base_source_reference", "comparison_source_reference")),
            _user_common_detail_rows("적용비율", _user_get(item, "base_tariff_applicable_rate"), _user_get(item, "comparison_tariff_applicable_rate"), "upstream trace의 85% 적용 비율", source=_user_source(item, "base_source_reference", "comparison_source_reference")),
            _user_common_detail_rows("관세율", _user_get(item, "base_tariff_rate"), _user_get(item, "comparison_tariff_rate"), "upstream trace의 10% 관세율", source=_user_source(item, "base_source_reference", "comparison_source_reference")),
            _user_common_detail_rows("유효 관세율", _user_get(item, "base_tariff_effective_rate"), _user_get(item, "comparison_tariff_effective_rate"), "upstream trace 결과; Evidence에서 재계산하지 않음", source=_user_source(item, "base_source_reference", "comparison_source_reference")),
            _user_common_detail_rows("관세 Effect", formula="최종 Analysis/Comparison result", effect=_user_get(item, "tariff_effect"), source=_user_source(item, "base_source_reference", "comparison_source_reference")),
        ])
    write_section("관세", tariff_values)

    material_values = []
    for item in raw_material:
        material_values.append(_user_common_detail_rows(
            str(_user_get(item, "product_group", "원재료")),
            _user_get(item, "base_cost"),
            _user_get(item, "comparison_cost"),
            "(기준 원단위 - 비교 원단위) × 비교 사용 수량",
            _user_get(item, "total_effect"),
            _user_source(item, "base_source_reference", "comparison_source_reference"),
        ))
    for item in nonwoven:
        material_values.append(_user_common_detail_rows(
            "부직포(JPY 포함)",
            _user_get(item, "base_cost"),
            _user_get(item, "comparison_cost"),
            "부직포 총효과 = 순수 가격효과 + JPY 환율효과",
            _user_get(item, "nonwoven_total"),
            _user_source(item, "base_source_reference", "comparison_source_reference"),
        ))
    write_section("원재료", material_values)

    manufacturing_values = []
    for item in manufacturing_rows:
        manufacturing_values.append(_user_common_detail_rows(
            str(_user_get(item, "account", "제조경비")),
            _user_get(item, "baseline_amount"),
            _user_get(item, "comparison_amount"),
            "전공정/후공정 조업도·원단위·고정비 trace",
            _user_get(item, "final_profit_effect", _user_get(item, "occurrence_effect")),
            _user_source(item, "base_amount_source", "comparison_amount_source"),
        ))
    write_section("제조경비", manufacturing_values)

    sga_values = []
    for item in sga_rows:
        sga_values.append(_user_common_detail_rows(
            str(_user_get(item, "display_account", _user_get(item, "account", "판관비"))),
            _user_get(item, "base_amount", _user_get(item, "baseline_amount")),
            _user_get(item, "comparison_amount"),
            "고객배송 운반비는 판매효과에서 반영" if _user_get(item, "classification") == "transport" else "월별 판관비 Engine trace",
            _user_get(item, "profit_effect"),
            _user_source(item, "base_source_reference", "comparison_source_reference"),
        ))
    write_section("판관비", sga_values)

    inventory_values = []
    for item in inventory_rows:
        inventory_values.append(_user_common_detail_rows(
            "Inventory Timing",
            _user_get(item, "base_manufactured_cogs"),
            _user_get(item, "comparison_manufactured_cogs"),
            "Gross/overlap을 포함한 공식 Inventory Timing trace",
            _user_get(item, "inventory_timing_effect"),
            _user_get(item, "source_reference"),
        ))
    write_section("Inventory Timing", inventory_values)

    merchandise_values = []
    for item in merchandise:
        merchandise_values.append(_user_common_detail_rows(
            str(_user_get(item, "product_group", "상품원가")),
            _user_get(item, "base_merchandise_cogs"),
            _user_get(item, "comparison_merchandise_cogs"),
            "sales_cogs_scope_analysis.source_rows 값만 표시; override 추정 없음",
            _user_get(item, "merchandise_cogs_effect"),
            _user_source(item, "base_source_reference", "comparison_source_reference"),
        ))
    write_section("상품원가", merchandise_values)

    new_values = []
    for item in new_business:
        new_values.extend([
            _user_common_detail_rows("신사업 매출 / COGS", _user_get(item, "base_revenue"), _user_get(item, "comparison_revenue"), "신사업 Revenue/COGS Engine trace", None, _user_source(item, "base_source_reference", "comparison_source_reference")),
            _user_common_detail_rows("매출증가 효과 (Quantity child)", None, None, "(비교 매출액 - 기준 매출액) × 기준 GP율", _user_get(item, "revenue_effect"), _user_source(item, "base_source_reference", "comparison_source_reference")),
            _user_common_detail_rows("GP율 변화 효과 (Price child)", _user_get(item, "base_gp_rate"), _user_get(item, "comparison_gp_rate"), "비교 매출액 × (비교 GP율 - 기준 GP율)", _user_get(item, "gp_rate_effect"), _user_source(item, "base_source_reference", "comparison_source_reference")),
            _user_common_detail_rows("Mix / Sales FX 정책", None, None, "Mix = 0, Sales FX = 0", _user_get(item, "mix_effect"), _user_source(item, "base_source_reference", "comparison_source_reference")),
        ])
    write_section("신사업", new_values)
    _user_finish_sheet(ws, row, 6)
    return ws


def add_user_evidence_sheets(workbook: Any, result: Any) -> list[str]:
    """Create the ordered, user-facing Slice C Evidence sheets.

    The function is intentionally presentation-only.  It reads authoritative
    result/trace fields and writes explanation text; it never calculates a
    business Effect or fabricates a missing monthly value.  ``Source Detail``
    is owned by the exporter and is therefore not created here.
    """
    months = _user_selected_months(result)
    names = [
        "분석요약",
        "판매효과",
        "상품원가산출",
        "원재료",
        "제조경비",
        "판관비",
        "Inventory Timing",
        *[f"{month} 상세" for month in months],
    ]
    _user_summary_sheet(workbook, result)
    _user_sales_sheet(workbook, result, months)
    _user_merchandise_sheet(workbook, result, months)
    _user_material_sheet(workbook, result, months)
    _user_manufacturing_sheet(workbook, result, months)
    _user_sga_sheet(workbook, result, months)
    _user_inventory_sheet(workbook, result, months)
    for month in months:
        _user_month_detail_sheet(workbook, result, month)

    # The exporter may already have created compatibility sheets.  Keep those
    # sheets intact but make the user sheets the workbook front matter.
    ordered = [workbook[name] for name in names if name in workbook.sheetnames]
    remainder = [sheet for sheet in workbook.worksheets if sheet not in ordered]
    workbook._sheets = ordered + remainder
    return names
