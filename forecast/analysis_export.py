from __future__ import annotations

import json
import re
from dataclasses import asdict, is_dataclass
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any, Iterable

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .workbook import GoldenWorkbook
from .evidence_traceability import (
    write_final_bridge,
    write_manufacturing_evidence,
    write_material_evidence,
    write_merchandise_link,
    write_residual_rca,
    write_sales_cogs_basis,
    write_sales_cogs_scope,
    write_sales_evidence,
    write_sga_evidence,
)


MIME_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
MONTH_COLUMNS = {month: chr(ord("E") + month - 1) for month in range(1, 13)}

_HEADER_FILL = PatternFill("solid", fgColor="1F4E78")
_SUBHEADER_FILL = PatternFill("solid", fgColor="D9EAF7")
_INPUT_FILL = PatternFill("solid", fgColor="FFF2CC")
_FORMULA_FILL = PatternFill("solid", fgColor="E2F0D9")
_CHECK_FILL = PatternFill("solid", fgColor="EDEDED")
_WHITE_FONT = Font(color="FFFFFF", bold=True)
_BOLD = Font(bold=True)


def _record_dict(item: Any) -> dict[str, Any]:
    if is_dataclass(item):
        return asdict(item)
    return dict(item)


def _number(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _write_title(ws, title: str, subtitle: str | None = None) -> int:
    ws["A1"] = title
    ws["A1"].font = Font(size=16, bold=True)
    if subtitle:
        ws["A2"] = subtitle
        ws["A2"].alignment = Alignment(wrap_text=True, vertical="top")
        return 4
    return 3


def _write_headers(ws, row: int, headers: list[str]) -> None:
    for col, header in enumerate(headers, 1):
        cell = ws.cell(row, col, header)
        cell.fill = _HEADER_FILL
        cell.font = _WHITE_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.auto_filter.ref = f"A{row}:{get_column_letter(len(headers))}{row}"
    ws.freeze_panes = f"A{row + 1}"


def _style_data_sheet(ws, header_row: int, money_columns: Iterable[int] = (), percent_columns: Iterable[int] = ()) -> None:
    money_set, percent_set = set(money_columns), set(percent_columns)
    for row in ws.iter_rows(min_row=header_row + 1):
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)
            if cell.column in money_set and isinstance(cell.value, (int, float)):
                cell.number_format = '#,##0'
            if cell.column in percent_set and isinstance(cell.value, (int, float)):
                cell.number_format = '0.00%'
    widths: dict[int, int] = {}
    for row in ws.iter_rows():
        for cell in row:
            text = "" if cell.value is None else str(cell.value)
            widths[cell.column] = min(52, max(widths.get(cell.column, 0), len(text) + 2))
    for index, width in widths.items():
        ws.column_dimensions[get_column_letter(index)].width = max(10, width)


def _formula_check(formula_cell: str, engine_cell: str, tolerance: float = 1.0) -> str:
    return f'=IF(ABS({formula_cell}-{engine_cell})<={tolerance},"PASS","CHECK")'


def _bridge_identity_passes(result: dict[str, Any]) -> bool:
    operating_profit_delta = _number(result.get("operating_profit_delta"))
    bridge_total = _number(result.get("effects_total")) + _number(result.get("residual"))
    tolerance = max(1.0, abs(operating_profit_delta) * 1e-9)
    return abs(bridge_total - operating_profit_delta) <= tolerance


def _validate_formula_integrity(workbook: Workbook) -> None:
    """Fail generation on explicit formula errors or broken sheet references."""
    error_tokens = (
        "#REF!", "#DIV/0!", "#VALUE!", "#NAME?", "#N/A", "#NUM!", "#NULL!",
        "#SPILL!", "#CALC!",
    )
    broken: list[str] = []
    for ws in workbook.worksheets:
        for row in ws.iter_rows():
            for cell in row:
                value = cell.value
                if not (isinstance(value, str) and value.startswith("=")):
                    continue
                upper = value.upper()
                if any(token in upper for token in error_tokens):
                    broken.append(f"{ws.title}!{cell.coordinate}: {value}")
                for sheet_name in re.findall(r"'([^']+)'!", value):
                    if sheet_name not in workbook.sheetnames:
                        broken.append(
                            f"{ws.title}!{cell.coordinate}: missing sheet {sheet_name}"
                        )
    for defined_name in workbook.defined_names.values():
        try:
            destinations = list(defined_name.destinations)
        except (AttributeError, TypeError, ValueError):
            continue
        for sheet_name, _coordinate in destinations:
            if sheet_name not in workbook.sheetnames:
                broken.append(f"defined name {defined_name.name}: missing sheet {sheet_name}")
    if broken:
        raise ValueError("Evidence Workbook formula integrity failure: " + "; ".join(broken))


def _write_readme(ws, result: dict[str, Any], baseline_fx: float, comparison_fx: float) -> None:
    _write_title(ws, "손익분석 검증 엑셀", "웹 손익분석에서 사용한 입력값, 원천 셀, 계산식과 결과를 추적하기 위한 파일입니다.")
    base = result.get("baseline", {})
    comp = result.get("comparison", {})
    period = result.get("period", {})
    rows = [
        ("생성일시", datetime.now().astimezone().isoformat(timespec="seconds")),
        ("기준 모형", f"{base.get('name', '')} / {base.get('model_type', '')} / {base.get('version', '')}"),
        ("비교 모형", f"{comp.get('name', '')} / {comp.get('model_type', '')} / {comp.get('version', '')}"),
        ("분석기간", period.get("label", "")),
        ("증감 정의", "비교 모형 - 기준 모형"),
        ("효과 부호", "손익 개선 + / 손익 악화 -"),
        ("기준 매출환율", baseline_fx),
        ("비교 매출환율", comparison_fx),
        ("영업이익 증감", result.get("operating_profit_delta", 0)),
        ("세부 효과 합계", result.get("effects_total", 0)),
        ("잔여차이", result.get("residual", 0)),
        ("브리지 항등식", "PASS" if _bridge_identity_passes(result) else "CHECK"),
        ("잔차 허용오차 정합성", "PASS" if result.get("reconciled") else "CHECK"),
        (
            "Residual RCA",
            (result.get("residual_analysis") or {}).get(
                "status", "TRACE_UNAVAILABLE_LEGACY"
            ),
        ),
        (
            "Sales/COGS Basis Overlap",
            (result.get("sales_cogs_basis_analysis") or {}).get(
                "verdict", "TRACE_UNAVAILABLE_LEGACY"
            ),
        ),
        (
            "Sales/P&L COGS Scope",
            (result.get("sales_cogs_scope_analysis") or {}).get(
                "option_readiness", "TRACE_UNAVAILABLE_LEGACY"
            ),
        ),
    ]
    evidence = result.get("evidence_provenance", {})
    if isinstance(evidence, dict):
        rows.extend(
            (
                f"Provenance: {key}",
                json.dumps(value, ensure_ascii=False, sort_keys=True)
                if isinstance(value, (dict, list)) else value,
            )
            for key, value in evidence.items()
        )
    start = 4
    for index, (label, value) in enumerate(rows, start):
        ws.cell(index, 1, label).font = _BOLD
        ws.cell(index, 1).fill = _SUBHEADER_FILL
        ws.cell(index, 2, value)
    note_row = start + len(rows) + 2
    ws.cell(note_row, 1, "사용 방법").font = _BOLD
    ws.cell(note_row + 1, 1, "1. 각 검증 시트의 ‘엔진값’은 웹 화면 계산에 사용된 값입니다.")
    ws.cell(note_row + 2, 1, "2. 녹색 셀은 엑셀 수식으로 동일 계산을 재현한 값입니다.")
    ws.cell(note_row + 3, 1, "3. CHECK가 발생하면 원천 셀, 매핑 규칙, 환율 입력 또는 코드 계산을 확인합니다.")
    ws.cell(note_row + 4, 1, "4. 원천셀_추적 시트의 수식은 업로드 모형에 저장된 원본 수식이며, 값은 웹 엔진이 읽은 계산값입니다.")
    ws.cell(note_row + 5, 1, "5. MCM과 수율/사용량은 독립 손익효과로 표시하지 않습니다.")
    ws.cell(note_row + 6, 1, "6. Residual_RCA 시트는 Direct P&L과 기존 Effect의 차이를 분해하며 신규 Effect나 plug를 만들지 않습니다.")
    ws.cell(note_row + 7, 1, "7. Slice 5D부터 Quantity/Mix는 유지하고 authoritative Core Manufactured COGS overlap만 Gross Inventory Timing에서 차감해 Net Inventory Timing을 Production 적용합니다.")
    ws.cell(note_row + 8, 1, "8. Sales_COGS_Scope 시트는 LC 제조/상품, Sales/P&L 조정, New Business denominator와 SKU Source coverage를 분석하고 Slice 5D Core-only Production 적용 상태를 검증합니다.")
    ws.column_dimensions["A"].width = 28
    ws.column_dimensions["B"].width = 72


def _write_pnl_and_reconciliation(ws, result: dict[str, Any]) -> None:
    header_row = _write_title(ws, "손익계산서 및 정합성", "기준·비교 손익과 손익 브리지의 정합성을 엑셀 수식으로 재확인합니다.")
    headers = ["구분", "코드", "항목", "기준 엔진값", "비교 엔진값", "증감 엔진값", "증감 엑셀수식", "검증"]
    _write_headers(ws, header_row, headers)
    row_no = header_row + 1
    for item in result.get("pnl", []):
        ws.append([
            "손익계산서", item.get("code"), item.get("item"), _number(item.get("baseline")),
            _number(item.get("comparison")), _number(item.get("delta")), None, None,
        ])
        ws.cell(row_no, 7, f"=E{row_no}-D{row_no}").fill = _FORMULA_FILL
        ws.cell(row_no, 8, _formula_check(f"G{row_no}", f"F{row_no}")).fill = _CHECK_FILL
        row_no += 1

    ws.append([])
    row_no += 1
    effect_start = row_no
    for item in result.get("effects", []):
        ws.append([
            "손익 브리지", item.get("code"), item.get("factor") or item.get("label"),
            _number(item.get("baseline")), _number(item.get("comparison")),
            _number(item.get("profit_effect")), None, None,
        ])
        if item.get("code") == "inventory_timing":
            formula = "='재고시차_검증'!D12"
        elif item.get("baseline") is None or item.get("comparison") is None:
            # Detailed evidence sheets reproduce these calculations. This bridge
            # row links their engine result without synthetic source amounts.
            formula = f"=F{row_no}"
        elif item.get("code") == "revenue":
            formula = f"=E{row_no}-D{row_no}"
        else:
            formula = f"=D{row_no}-E{row_no}"
        ws.cell(row_no, 7, formula).fill = _FORMULA_FILL
        ws.cell(row_no, 8, _formula_check(f"G{row_no}", f"F{row_no}")).fill = _CHECK_FILL
        row_no += 1
    effect_end = row_no - 1

    ws.append([])
    row_no += 1
    ws.cell(row_no, 3, "영업이익 증감 엔진값").font = _BOLD
    ws.cell(row_no, 6, _number(result.get("operating_profit_delta")))
    op_row = row_no
    row_no += 1
    ws.cell(row_no, 3, "세부 효과 합계 엔진값").font = _BOLD
    ws.cell(row_no, 6, _number(result.get("effects_total")))
    ws.cell(row_no, 7, f"=SUM(G{effect_start}:G{effect_end})").fill = _FORMULA_FILL
    ws.cell(row_no, 8, _formula_check(f"G{row_no}", f"F{row_no}")).fill = _CHECK_FILL
    total_row = row_no
    row_no += 1
    ws.cell(row_no, 3, "잔여차이 엔진값").font = _BOLD
    ws.cell(row_no, 6, _number(result.get("residual")))
    ws.cell(row_no, 7, f"=F{op_row}-G{total_row}").fill = _FORMULA_FILL
    ws.cell(row_no, 8, _formula_check(f"G{row_no}", f"F{row_no}")).fill = _CHECK_FILL
    row_no += 1
    ws.cell(row_no, 3, "브리지 항등식").font = _BOLD
    ws.cell(
        row_no,
        8,
        f'=IF(ABS(F{op_row}-(G{total_row}+F{row_no-1}))<=MAX(1,ABS(F{op_row})*1E-9),"PASS","CHECK")',
    ).fill = _CHECK_FILL
    row_no += 1
    ws.cell(row_no, 3, "잔차 허용오차 정합성").font = _BOLD
    ws.cell(
        row_no,
        8,
        f'=IF(ABS(F{row_no-2})<=MAX(1,ABS(F{op_row})*1E-9),"PASS","CHECK")',
    ).fill = _CHECK_FILL
    _style_data_sheet(ws, header_row, money_columns=(4, 5, 6, 7))


def _write_sales(ws, sales_rows: Iterable[Any], sales_totals: dict[str, float], baseline_fx: float, comparison_fx: float) -> None:
    header_row = _write_title(ws, "판매효과 검증", "웹 화면과 동일한 수량·단가·환율 효과 산식을 셀 수식으로 재현합니다.")
    headers = [
        "제품군", "기준수량", "기준매출액", "기준단가 수식", "기준단가 엔진", "기준GP율",
        "비교수량", "비교매출액", "비교단가 수식", "비교단가 엔진", "비교GP율",
        "기준FX", "비교FX", "수량·Mix효과 수식", "수량·Mix효과 엔진", "기준외화단가 수식",
        "비교외화단가 수식", "판매단가효과 수식", "판매단가효과 엔진", "환율효과 수식",
        "환율효과 엔진", "판매효과합계 수식", "판매효과합계 엔진", "검증",
        "기준 관세제외 고객배송 운반비", "비교 관세제외 고객배송 운반비",
        "고객배송 운반비 효과 수식",
    ]
    _write_headers(ws, header_row, headers)
    row_no = header_row + 1
    first_data_row = row_no
    for source in sales_rows:
        item = _record_dict(source)
        ws.append([
            item.get("product_group", ""), _number(item.get("baseline_quantity")), _number(item.get("baseline_amount")),
            None, _number(item.get("baseline_unit_price")), _number(item.get("baseline_gross_margin_rate")),
            _number(item.get("comparison_quantity")), _number(item.get("comparison_amount")), None,
            _number(item.get("comparison_unit_price")), _number(item.get("comparison_gross_margin_rate")),
            baseline_fx, comparison_fx, None, _number(item.get("quantity_effect")), None, None, None,
            _number(item.get("pure_price_effect")), None, _number(item.get("sales_fx_effect")), None,
            _number(item.get("total_sales_effect")), None,
        ])
        formulas = {
            4: f"=IFERROR(C{row_no}/B{row_no},0)",
            9: f"=IFERROR(H{row_no}/G{row_no},0)",
            14: f"=(G{row_no}-B{row_no})*D{row_no}*F{row_no}",
            16: f"=IFERROR(D{row_no}/L{row_no},0)",
            17: f"=IFERROR(I{row_no}/M{row_no},0)",
            18: f"=G{row_no}*(Q{row_no}-P{row_no})*(L{row_no}+M{row_no})/2",
            20: f"=G{row_no}*(M{row_no}-L{row_no})*(P{row_no}+Q{row_no})/2",
            22: f"=N{row_no}+R{row_no}+T{row_no}",
            24: f'=IF(MAX(ABS(D{row_no}-E{row_no}),ABS(I{row_no}-J{row_no}),ABS(N{row_no}-O{row_no}),ABS(R{row_no}-S{row_no}),ABS(T{row_no}-U{row_no}),ABS(V{row_no}-W{row_no}))<=1,"PASS","CHECK")',
        }
        for col, formula in formulas.items():
            ws.cell(row_no, col, formula)
            ws.cell(row_no, col).fill = _FORMULA_FILL if col != 24 else _CHECK_FILL
        row_no += 1
    transport_effect = _number(sales_totals.get("transport_effect"))
    baseline_transport = _number(sales_totals.get("baseline_transport_ex_tariff"))
    comparison_transport = _number(sales_totals.get("comparison_transport_ex_tariff"))
    ws.cell(row_no, 1, "고객배송 운반비 효과")
    ws.cell(row_no, 18, f"=AA{row_no}").fill = _FORMULA_FILL
    ws.cell(row_no, 19, transport_effect)
    ws.cell(row_no, 22, f"=R{row_no}").fill = _FORMULA_FILL
    ws.cell(row_no, 23, transport_effect)
    ws.cell(row_no, 25, baseline_transport)
    ws.cell(row_no, 26, comparison_transport)
    ws.cell(row_no, 27, f"=Y{row_no}-Z{row_no}").fill = _FORMULA_FILL
    ws.cell(
        row_no,
        24,
        f'=IF(MAX(ABS(AA{row_no}-S{row_no}),ABS(V{row_no}-W{row_no}))<=1,"PASS","CHECK")',
    ).fill = _CHECK_FILL
    row_no += 1
    last_data_row = row_no - 1
    ws.cell(row_no, 1, "합계").font = _BOLD
    for col in (14, 18, 20, 22):
        ws.cell(row_no, col, f"=SUM({get_column_letter(col)}{first_data_row}:{get_column_letter(col)}{last_data_row})").fill = _FORMULA_FILL
    ws.cell(
        row_no,
        15,
        _number(sales_totals.get("quantity_effect"))
        + _number(sales_totals.get("mix_effect")),
    )
    ws.cell(
        row_no,
        19,
        _number(
            sales_totals.get(
                "sales_price_effect", sales_totals.get("pure_price_effect")
            )
        ),
    )
    ws.cell(row_no, 21, _number(sales_totals.get("sales_fx_effect")))
    ws.cell(row_no, 23, _number(sales_totals.get("total_sales_effect")))
    ws.cell(row_no, 24, f'=IF(MAX(ABS(N{row_no}-O{row_no}),ABS(R{row_no}-S{row_no}),ABS(T{row_no}-U{row_no}),ABS(V{row_no}-W{row_no}))<=1,"PASS","CHECK")').fill = _CHECK_FILL
    _style_data_sheet(
        ws,
        header_row,
        money_columns=(3, 4, 5, 8, 9, 10, 14, 15, 18, 19, 20, 21, 22, 23, 25, 26, 27),
        percent_columns=(6, 11),
    )


def _write_simple_delta_sheet(ws, title: str, subtitle: str, sections: list[tuple[str, list[dict[str, Any]]]]) -> None:
    header_row = _write_title(ws, title, subtitle)
    headers = ["구분", "코드", "항목", "기준 엔진값", "비교 엔진값", "증감 엔진값", "증감 엑셀수식", "검증", "비고"]
    _write_headers(ws, header_row, headers)
    row_no = header_row + 1
    for section, rows in sections:
        for item in rows:
            label = item.get("item") or item.get("factor") or item.get("label") or item.get("code")
            ws.append([
                section, item.get("code", ""), label, _number(item.get("baseline")),
                _number(item.get("comparison")), _number(item.get("delta")), None, None, item.get("note", ""),
            ])
            ws.cell(row_no, 7, f"=E{row_no}-D{row_no}").fill = _FORMULA_FILL
            ws.cell(row_no, 8, _formula_check(f"G{row_no}", f"F{row_no}")).fill = _CHECK_FILL
            row_no += 1
    _style_data_sheet(ws, header_row, money_columns=(4, 5, 6, 7))


def _write_material_detail(ws, result: dict[str, Any]) -> None:
    header_row = _write_title(
        ws,
        "원부재료 효과 검증",
        "엔진 Result의 제품군별 3요소를 그대로 기록합니다. 원천은 JPY 9행, 전공정 205~210행, 후공정 684~699행입니다.",
    )
    headers = [
        "제품군", "기준 원단위", "비교 원단위", "원단위 증감",
        "부직포 단가효과(환율 제외)", "부직포 엔화효과",
        "부직포 제외 원재료 효과", "원부재료 효과 합계", "3요소 엑셀합계", "검증", "계산상태",
    ]
    _write_headers(ws, header_row, headers)
    for item in (result.get("material_analysis") or {}).get("product_groups", []):
        row_no = ws.max_row + 1
        ws.append([
            item.get("product_group"), item.get("baseline_unit_cost"),
            item.get("comparison_unit_cost"), item.get("unit_cost_delta"),
            item.get("nonwoven_price_ex_fx"), item.get("nonwoven_jpy"),
            item.get("materials_ex_nonwoven"), item.get("total"), None, None,
            item.get("calculation_status"),
        ])
        ws.cell(row_no, 9, f"=SUM(E{row_no}:G{row_no})").fill = _FORMULA_FILL
        ws.cell(row_no, 10, _formula_check(f"I{row_no}", f"H{row_no}")).fill = _CHECK_FILL
    _style_data_sheet(ws, header_row, money_columns=(5, 6, 7, 8, 9))


def _write_manufacturing_detail(ws, result: dict[str, Any]) -> None:
    header_row = _write_title(
        ws,
        "생산·제조경비 효과 검증",
        "Golden Model 제조경비 계정과 기준 전공정 배부율로 산출하며, 재고실현율은 참고지표이고 최종 Effect multiplier로 사용하지 않습니다.",
    )
    headers = [
        "원천 행", "계정과목", "구분", "배부율 원천 행", "기준 전공정 배부율",
        "기준 금액", "비교 금액", "증감", "조업도 효과", "원단위 효과",
        "고정비 효과", "발생효과", "재고실현율(참고)", "최종 손익효과", "발생효과 엑셀합계", "검증", "계산상태",
    ]
    headers.append("당기제조원가 구성")
    _write_headers(ws, header_row, headers)
    for item in result.get("manufacturing_accounts", []):
        row_no = ws.max_row + 1
        ratios = item.get("baseline_front_ratios") or []
        ratio_display = ratios[0] if len(ratios) == 1 else ", ".join(str(value) for value in ratios)
        ws.append([
            item.get("row"), item.get("account"), item.get("classification"),
            item.get("allocation_ratio_row"), ratio_display,
            item.get("baseline_amount"), item.get("comparison_amount"), item.get("delta"),
            item.get("activity_effect"), item.get("unit_effect"), item.get("fixed_effect"),
            item.get("occurrence_effect"), item.get("inventory_realization_rate"),
            item.get("final_profit_effect"), None, None, item.get("calculation_status"),
            item.get("current_cost_component"),
        ])
        ws.cell(row_no, 15, f"=SUM(I{row_no}:K{row_no})").fill = _FORMULA_FILL
        ws.cell(row_no, 16, _formula_check(f"O{row_no}", f"L{row_no}")).fill = _CHECK_FILL
    _style_data_sheet(
        ws, header_row,
        money_columns=(6, 7, 8, 9, 10, 11, 12, 14, 15),
        percent_columns=(5, 13),
    )


def _write_inventory_timing(ws, result: dict[str, Any]) -> dict[str, str]:
    inventory = result.get("inventory_analysis") or {}
    _write_title(
        ws,
        "재고·원가 반영시차 검증",
        "Gross Inventory Timing에서 Sales Quantity/Mix에 이미 포함된 Core Manufactured COGS overlap만 차감하여 Net Inventory Timing을 산출합니다.",
    )
    _write_headers(
        ws,
        4,
        ["공식 계산", "Base", "Comparison", "Excel Formula", "Engine Value", "Validation", "Source Reference"],
    )
    source_details = list(inventory.get("source_details") or [])

    def refs(side: str, canonical: str) -> str:
        return ", ".join(
            str(row.get("source_reference") or "")
            for row in source_details
            if row.get("side") == side and row.get("canonical_field") == canonical
        )

    # The aggregate fields do not retain the two COGS components separately;
    # recover them from the canonical source detail rows for transparent input cells.
    def source_total(side: str, canonical: str) -> float:
        return sum(
            _number(row.get("value"))
            for row in source_details
            if row.get("side") == side and row.get("canonical_field") == canonical
        )

    ws.append([
        "Finished Goods COGS",
        source_total("BASE", "finished_goods_cogs"),
        source_total("COMPARISON", "finished_goods_cogs"),
        None, None, inventory.get("source_validation_status"),
        f"Base: {refs('BASE', 'finished_goods_cogs')} / Comparison: {refs('COMPARISON', 'finished_goods_cogs')}",
    ])
    ws.append([
        "Semi-finished Goods COGS",
        source_total("BASE", "semi_finished_goods_cogs"),
        source_total("COMPARISON", "semi_finished_goods_cogs"),
        None, None, inventory.get("source_validation_status"),
        f"Base: {refs('BASE', 'semi_finished_goods_cogs')} / Comparison: {refs('COMPARISON', 'semi_finished_goods_cogs')}",
    ])
    ws.append(["Manufactured COGS", None, None, "B7 = B5+B6; C7 = C5+C6", None, None, "제품+반제품만 포함"])
    ws["B7"] = "=B5+B6"; ws["C7"] = "=C5+C6"
    ws["B7"].fill = _FORMULA_FILL; ws["C7"].fill = _FORMULA_FILL
    ws.append([
        "Current Manufacturing Cost",
        source_total("BASE", "current_manufacturing_cost"),
        source_total("COMPARISON", "current_manufacturing_cost"),
        None, None, inventory.get("source_validation_status"),
        f"Base: {refs('BASE', 'current_manufacturing_cost')} / Comparison: {refs('COMPARISON', 'current_manufacturing_cost')}",
    ])
    ws.append([])
    ws.append([
        "Manufactured COGS Effect", None, None, "=B7-C7",
        _number(inventory.get("manufactured_cogs_effect")), None,
        "Base Manufactured COGS - Comparison Manufactured COGS",
    ])
    ws["D10"] = "=B7-C7"; ws["D10"].fill = _FORMULA_FILL
    ws["F10"] = _formula_check("D10", "E10"); ws["F10"].fill = _CHECK_FILL
    ws.append([
        "Current Manufacturing Cost Effect", None, None, "=B8-C8",
        _number(inventory.get("current_manufacturing_cost_effect")), None,
        "Base Current Manufacturing Cost - Comparison Current Manufacturing Cost",
    ])
    ws["D11"] = "=B8-C8"; ws["D11"].fill = _FORMULA_FILL
    ws["F11"] = _formula_check("D11", "E11"); ws["F11"].fill = _CHECK_FILL
    summary_rows = (
        (12, "Gross Inventory Timing", "=D10-D11", "gross_inventory_timing_effect", "Manufactured COGS Effect - Current Manufacturing Cost Effect"),
        (13, "Core Quantity COGS Overlap", None, "core_cogs_quantity_overlap_effect", "Sales Quantity에 내재된 core manufactured COGS, OP sign"),
        (14, "Core Mix COGS Overlap", None, "core_cogs_mix_overlap_effect", "Sales Mix에 내재된 core manufactured COGS, OP sign"),
        (15, "Total Core Manufactured COGS Overlap", "=D13+D14", "core_manufactured_cogs_overlap_effect", "Quantity + Mix; non-additive deduction"),
        (16, "Net Inventory Timing Effect", "=D12-D15", "inventory_timing_effect", "공식 additive Effect = Gross - Core overlap"),
    )
    for row_no, label, formula, field, note in summary_rows:
        ws.cell(row_no, 1, label)
        if formula:
            ws.cell(row_no, 4, formula).fill = _FORMULA_FILL
        ws.cell(row_no, 5, _number(inventory.get(field)))
        ws.cell(row_no, 6, _formula_check(f"D{row_no}", f"E{row_no}")).fill = _CHECK_FILL
        ws.cell(row_no, 7, note)
    ws["A17"] = "Core overlap policy"
    ws["E17"] = inventory.get("core_overlap_policy_status")
    ws["F17"] = (
        "PASS" if inventory.get("core_overlap_policy_status") == "APPLIED_CORE_ONLY"
        and inventory.get("core_overlap_source_validation_status") == "PASS"
        and inventory.get("core_overlap_pool_validation_status") == "PASS"
        else "FAIL"
    )
    ws["G17"] = "Adjustments, merchandise, Other COGS, P&L adjustments, row323 excluded"

    row_no = 20
    _write_headers(
        ws, row_no,
        ["Business Source", "Canonical Field", "Base/Comparison", "Period", "Unit", "Source Reference", "Used Value", "Calculation", "Validation"],
    )
    for source in source_details:
        ws.append([
            source.get("business_source"), source.get("canonical_field"),
            source.get("side"), source.get("period"), source.get("unit"),
            source.get("source_reference"), source.get("value"),
            "Source value (no residual/OP backsolve)", source.get("validation_status"),
        ])

    core_header = ws.max_row + 3
    _write_headers(
        ws,
        core_header,
        [
            "Period", "Selected", "Pool", "Product Group", "Unit",
            "Base Quantity", "Comparison Quantity", "Pool Base Quantity",
            "Pool Comparison Quantity", "Base Core Manufactured COGS",
            "Base Core COGS/unit", "Base Mix", "Comparison Mix",
            "Embedded Quantity COGS Expense", "Embedded Mix COGS Expense",
            "Quantity Overlap OP", "Mix Overlap OP", "Total Overlap OP",
            "Engine Quantity", "Engine Mix", "Engine Total", "Validation",
            "Base Quantity Source", "Base Core COGS Source",
            "Comparison Quantity Source", "Comparison Core COGS Source",
        ],
    )
    core_start = core_header + 1
    core_details = list(inventory.get("core_overlap_details") or [])
    for item in core_details:
        current = ws.max_row + 1
        ws.append([
            item.get("period"), "YES" if item.get("selected") else "NO",
            item.get("pool"), item.get("product_group"), item.get("unit"),
            item.get("base_quantity"), item.get("comparison_quantity"),
            item.get("pool_base_quantity"), item.get("pool_comparison_quantity"),
            item.get("base_core_manufactured_cogs"), None, None, None, None,
            None, None, None, None,
            item.get("quantity_overlap_effect"), item.get("mix_overlap_effect"),
            item.get("total_overlap_effect"), None,
            item.get("base_quantity_source_reference"),
            item.get("base_core_cogs_source_reference"),
            item.get("comparison_quantity_source_reference"),
            item.get("comparison_core_cogs_source_reference"),
        ])
        ws.cell(current, 11, f"=J{current}/F{current}").fill = _FORMULA_FILL
        ws.cell(current, 12, f"=F{current}/H{current}").fill = _FORMULA_FILL
        ws.cell(current, 13, f"=IF(I{current}=0,0,G{current}/I{current})").fill = _FORMULA_FILL
        ws.cell(current, 14, f"=(I{current}-H{current})*L{current}*K{current}").fill = _FORMULA_FILL
        ws.cell(current, 15, f"=I{current}*(M{current}-L{current})*K{current}").fill = _FORMULA_FILL
        ws.cell(current, 16, f"=-N{current}").fill = _FORMULA_FILL
        ws.cell(current, 17, f"=-O{current}").fill = _FORMULA_FILL
        ws.cell(current, 18, f"=P{current}+Q{current}").fill = _FORMULA_FILL
        ws.cell(
            current,
            22,
            f'=IF(MAX(ABS(P{current}-S{current}),ABS(Q{current}-T{current}),ABS(R{current}-U{current}))<=1,"PASS","FAIL")',
        ).fill = _CHECK_FILL
    core_end = max(core_start, ws.max_row)
    ws["D13"] = f'=SUMIFS(P{core_start}:P{core_end},B{core_start}:B{core_end},"YES")'
    ws["D14"] = f'=SUMIFS(Q{core_start}:Q{core_end},B{core_start}:B{core_end},"YES")'
    ws["D13"].fill = _FORMULA_FILL
    ws["D14"].fill = _FORMULA_FILL

    row_no = ws.max_row + 3
    _write_headers(
        ws,
        row_no,
        [
            "Rolling 3M Period", "Gross Inventory Timing", "Quantity Overlap",
            "Mix Overlap", "Total Core Overlap", "Net Inventory Timing",
            "Direction", "Persistence", "Source Reference",
        ],
    )
    rolling = list(inventory.get("monthly_details") or [])
    for item in rolling:
        ws.append([
            item.get("period"), item.get("gross_inventory_timing_effect"),
            item.get("core_cogs_quantity_overlap_effect"),
            item.get("core_cogs_mix_overlap_effect"),
            item.get("core_manufactured_cogs_overlap_effect"),
            item.get("inventory_timing_effect"), item.get("direction"),
            inventory.get("persistence"),
            item.get("source_reference"),
        ])

    row_no = ws.max_row + 3
    _write_headers(
        ws, row_no,
        ["Product Group", "Unit", "Specification", "Base Opening Unit Cost", "Comparison Opening Unit Cost", "Delta Formula", "Direction", "Aligned", "Coverage", "Base Source", "Comparison Source"],
    )
    for item in inventory.get("opening_inventory_units") or []:
        current_row = ws.max_row + 1
        ws.append([
            item.get("product_group"),
            "m" if item.get("unit_basis") == "LENGTH" else "PCS",
            item.get("specification"), item.get("base_unit_cost"),
            item.get("comparison_unit_cost"), None, item.get("evidence_direction"),
            item.get("direction_aligned"), item.get("coverage"),
            item.get("base_source_reference"), item.get("comparison_source_reference"),
        ])
        ws.cell(current_row, 6, f"=E{current_row}-D{current_row}").fill = _FORMULA_FILL

    row_no = ws.max_row + 3
    _write_headers(ws, row_no, ["Explanation Metadata", "Value", "Applied Rule / Notes"])
    metadata = (
        ("Primary", inventory.get("primary"), inventory.get("fallback_narrative")),
        ("Supporting", ", ".join(inventory.get("supporting") or []), "방향 일치·Rolling 3M evidence"),
        ("Reference", ", ".join(inventory.get("reference") or []), "Limited coverage evidence"),
        ("Confidence", inventory.get("confidence"), None),
        ("Persistence", inventory.get("persistence"), None),
        ("Coverage", inventory.get("product_unit_coverage"), None),
        ("Materiality", inventory.get("materiality_status"), "production threshold 미설정 시 보수적으로 No Primary"),
        ("Double-counting Gate", inventory.get("additive_bridge_status"), f"Current-cost explanation gap: {_number(inventory.get('current_cost_explanation_gap')):,.0f}"),
        ("Rule", inventory.get("explanation_rule"), "; ".join(inventory.get("scope_notes") or [])),
    )
    for item in metadata:
        ws.append(list(item))

    for row in ws.iter_rows():
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)
            if cell.column in {2, 3, 4, 5, 7} and isinstance(cell.value, (int, float)):
                cell.number_format = '#,##0'
    for column, width in {"A": 32, "B": 18, "C": 18, "D": 22, "E": 18, "F": 18, "G": 42, "H": 18, "I": 18, "J": 24, "K": 20, "L": 16, "M": 16, "N": 22, "O": 22, "P": 20, "Q": 20, "R": 20, "S": 20, "T": 20, "U": 20, "V": 16, "W": 34, "X": 42, "Y": 34, "Z": 42}.items():
        ws.column_dimensions[column].width = width
    ws.freeze_panes = "A5"
    return {
        "gross_inventory_timing": "D12",
        "core_quantity_overlap": "D13",
        "core_mix_overlap": "D14",
        "core_total_overlap": "D15",
        "inventory_timing": "D16",
        "core_overlap_policy": "F17",
    }


def _write_current_cost_basis(
    ws,
    result: dict[str, Any],
    evidence_cells: dict[str, dict[str, Any]] | None = None,
) -> None:
    inventory = result.get("inventory_analysis") or {}
    basis = inventory.get("current_cost_basis_analysis") or {}
    _write_title(
        ws,
        "당기제조원가 Basis Gap 검증",
        "row 325 직접 금액차이와 기존 Raw Material + Manufacturing Driver Effect의 Basis 차이를 Source 기준으로 설명합니다. Effect·Residual·Plug는 생성하거나 수정하지 않습니다.",
    )
    _write_headers(
        ws,
        4,
        ["Metric", "Engine Value", "Excel Formula", "Validation", "Formula Basis", "Status", "Source Reference"],
    )
    evidence_cells = evidence_cells or {}
    material_cells = evidence_cells.get("material") or {}
    manufacturing_cells = evidence_cells.get("manufacturing") or {}
    material_formula = (
        f"='원부재료_근거'!{material_cells['material_total']}"
        if material_cells.get("material_total") else "=0"
    )
    activity_formula = (
        f"='제조경비_근거'!{manufacturing_cells['manufacturing_activity']}"
        if manufacturing_cells.get("manufacturing_activity") else "=0"
    )
    unit_formula = (
        f"='제조경비_근거'!{manufacturing_cells['manufacturing_unit']}"
        if manufacturing_cells.get("manufacturing_unit") else "=0"
    )
    fixed_formula = (
        f"='제조경비_근거'!{manufacturing_cells['manufacturing_fixed']}"
        if manufacturing_cells.get("manufacturing_fixed") else "=0"
    )
    component_rows = list(basis.get("component_details") or [])
    current_total_row = 16 + len(component_rows) + 4
    current_cost_sources = ", ".join(
        str(item.get("source_reference") or "")
        for item in inventory.get("source_details") or []
        if item.get("canonical_field") == "current_manufacturing_cost"
    ) or "UNMAPPED"
    summary_rows = [
        ("Current Manufacturing Cost Effect", basis.get("current_manufacturing_cost_effect"), f"=D{current_total_row}", "Base Current Manufacturing Cost - Comparison Current Manufacturing Cost", basis.get("status"), current_cost_sources),
        ("Existing Raw Material Effect", basis.get("raw_material_effect"), material_formula, "Canonical unit-cost driver × Comparison sales/applicable basis", "UNCHANGED_FORMULA", "원부재료_근거"),
        ("Manufacturing Volume Effect", basis.get("manufacturing_activity_effect"), activity_formula, "Existing Activity formula", "UNCHANGED_FORMULA", "제조경비_근거"),
        ("Manufacturing Unit Cost Effect", basis.get("manufacturing_unit_effect"), unit_formula, "Existing Unit Cost formula", "UNCHANGED_FORMULA", "제조경비_근거"),
        ("Manufacturing Fixed Effect", basis.get("manufacturing_fixed_effect"), fixed_formula, "Existing Fixed formula", "UNCHANGED_FORMULA", "제조경비_근거"),
        ("Existing Manufacturing Effect", basis.get("manufacturing_effect"), "=SUM(C7:C9)", "Activity + Unit Cost + Fixed", "PASS_DIRECT_TIE", "제조경비_근거"),
        ("Existing Current Cost Driver subtotal", basis.get("existing_current_cost_driver_subtotal"), "=C6+C10", "Raw Material + Manufacturing", basis.get("status"), "Canonical drivers"),
        ("Basis Gap", basis.get("basis_gap"), "=C5-C11", "Current Manufacturing Cost Effect - Existing Driver subtotal", basis.get("status"), "No residual/plug backsolve"),
    ]
    for row_no, row in enumerate(summary_rows, 5):
        metric, engine_value, formula, formula_basis, status, source_ref = row
        ws.append([metric, _number(engine_value), None, None, formula_basis, status, source_ref])
        ws.cell(row_no, 3, formula).fill = _FORMULA_FILL
        ws.cell(row_no, 4, _formula_check(f"C{row_no}", f"B{row_no}")).fill = _CHECK_FILL

    _write_headers(
        ws,
        15,
        [
            "Component", "Base", "Comparison", "Direct Difference", "Existing Effect",
            "Gap", "Engine Gap", "Formula Validation", "Business Status", "Reason",
            "Formula Basis", "Source Coverage", "Base Source", "Comparison Source",
            "Base Source Formula", "Comparison Source Formula",
        ],
    )
    component_start = 16
    for offset, item in enumerate(component_rows):
        row_no = component_start + offset
        code = str(item.get("component_code") or "")
        if code == "raw_material_production_issue":
            existing_formula = "=C6"
        elif code in {"raw_material_tariff_refund", "paid_supply"}:
            existing_formula = "=0"
        elif manufacturing_cells.get("detail_range"):
            manufacturing_start, manufacturing_end = manufacturing_cells["detail_range"]
            component_column = manufacturing_cells.get("component_column", "AO")
            subtotal_column = manufacturing_cells.get("subtotal_column", "AK")
            existing_formula = (
                f'=SUMIF(\'제조경비_근거\'!${component_column}${manufacturing_start}:'
                f'${component_column}${manufacturing_end},"{code}",'
                f'\'제조경비_근거\'!${subtotal_column}${manufacturing_start}:'
                f'${subtotal_column}${manufacturing_end})'
            )
        else:
            existing_formula = "=0"
        ws.append([
            item.get("business_source"), _number(item.get("base")), _number(item.get("comparison")),
            None, None, None, _number(item.get("gap")), None, item.get("validation_status"),
            item.get("reason"), item.get("formula_basis"), item.get("source_coverage"),
            item.get("base_source_reference"), item.get("comparison_source_reference"),
            item.get("base_source_formula"), item.get("comparison_source_formula"),
        ])
        ws.cell(row_no, 4, f"=B{row_no}-C{row_no}").fill = _FORMULA_FILL
        ws.cell(row_no, 5, existing_formula).fill = _FORMULA_FILL
        ws.cell(row_no, 6, f"=D{row_no}-E{row_no}").fill = _FORMULA_FILL
        ws.cell(row_no, 8, _formula_check(f"F{row_no}", f"G{row_no}")).fill = _CHECK_FILL

    aggregate_header = component_start + len(component_rows) + 1
    _write_headers(
        ws,
        aggregate_header,
        ["Aggregate", "Base", "Comparison", "Direct Difference", "Existing Effect", "Basis Gap", "Engine Gap", "Validation"],
    )
    aggregate_rows = list(basis.get("aggregate_details") or [])
    aggregate_start = aggregate_header + 1
    member_ranges = {
        "raw_material_total": (component_start, component_start + 2),
        "manufacturing_processing_total": (component_start + 3, component_start + 4),
        "current_manufacturing_cost": (component_start, component_start + 4),
    }
    for offset, item in enumerate(aggregate_rows):
        row_no = aggregate_start + offset
        first, last = member_ranges[str(item.get("component_code"))]
        ws.append([item.get("business_source"), None, None, None, None, None, _number(item.get("gap")), None])
        for col in (2, 3, 4, 5, 6):
            source_col = get_column_letter(col)
            ws.cell(row_no, col, f"=SUM({source_col}{first}:{source_col}{last})").fill = _FORMULA_FILL
        ws.cell(row_no, 8, _formula_check(f"F{row_no}", f"G{row_no}")).fill = _CHECK_FILL

    driver_header = aggregate_start + len(aggregate_rows) + 2
    _write_headers(
        ws,
        driver_header,
        ["Manufacturing Component", "Base", "Comparison", "Direct Difference", "Activity", "Unit", "Fixed", "Existing Effect", "Gap", "Validation", "Reason"],
    )
    for item in basis.get("manufacturing_driver_details") or []:
        row_no = ws.max_row + 1
        ws.append([
            item.get("business_source"), _number(item.get("base")), _number(item.get("comparison")),
            None, _number(item.get("activity_effect")), _number(item.get("unit_effect")),
            _number(item.get("fixed_effect")), None, None, None, item.get("reason"),
        ])
        ws.cell(row_no, 4, f"=B{row_no}-C{row_no}").fill = _FORMULA_FILL
        ws.cell(row_no, 8, f"=SUM(E{row_no}:G{row_no})").fill = _FORMULA_FILL
        ws.cell(row_no, 9, f"=D{row_no}-H{row_no}").fill = _FORMULA_FILL
        ws.cell(row_no, 10, f'=IF(ABS(I{row_no})<=1,"PASS","CHECK")').fill = _CHECK_FILL

    classification_header = ws.max_row + 3
    _write_headers(ws, classification_header, ["Gap Classification", "Business Source", "Amount", "Source Coverage", "Reason"])
    for item in basis.get("gap_classification") or []:
        ws.append([
            item.get("classification"), item.get("business_source"), _number(item.get("amount")),
            item.get("source_coverage"), item.get("reason"),
        ])

    residual_header = ws.max_row + 3
    _write_headers(ws, residual_header, ["Residual Analysis", "Value", "Excel Formula", "Validation / Policy"])
    residual_start = residual_header + 1
    ws.append(["Current Residual", _number(basis.get("residual")), f"=B{residual_start}", "UNCHANGED"])
    ws.append(["Basis Gap mathematically linked", _number(basis.get("residual_basis_gap_link")), "=C12", "DISCLOSURE_ONLY"])
    ws.append(["Residual remainder", _number(basis.get("residual_remainder")), f"=B{residual_start}-B{residual_start + 1}", "NO_PLUG"])
    ws.append(["Plug created", bool(basis.get("plug_created")), "=FALSE", "PASS"])
    ws.append(["Architecture Decision", basis.get("architecture_decision"), None, basis.get("architecture_rationale")])

    for row in ws.iter_rows():
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)
            if isinstance(cell.value, (int, float)) and not isinstance(cell.value, bool):
                cell.number_format = '#,##0.000;[Red](#,##0.000);-'
    for column, width in {
        "A": 34, "B": 20, "C": 20, "D": 20, "E": 22, "F": 20,
        "G": 20, "H": 20, "I": 22, "J": 54, "K": 48, "L": 34,
        "M": 40, "N": 40, "O": 58, "P": 58,
    }.items():
        ws.column_dimensions[column].width = width
    ws.freeze_panes = "A5"


def _write_sga_detail(ws, result: dict[str, Any]) -> None:
    header_row = _write_title(
        ws,
        "판관비 효과 검증",
        "Golden Model 계정을 개별 행으로 기록하며 고객배송 운반비와 관세의 Bridge 반영 위치를 구분합니다.",
    )
    headers = [
        "원천 행", "구역", "계정과목", "구분", "기준 금액", "비교 금액",
        "증감", "손익효과", "손익 Bridge 반영",
    ]
    _write_headers(ws, header_row, headers)
    for item in result.get("sga_accounts", []):
        ws.append([
            item.get("row"), item.get("section"), item.get("account"),
            item.get("classification"), item.get("baseline_amount"),
            item.get("comparison_amount"), item.get("delta"),
            item.get("profit_effect"), item.get("bridge_position"),
        ])
    _style_data_sheet(ws, header_row, money_columns=(5, 6, 7, 8))


def _write_formula_catalog(ws) -> None:
    header_row = _write_title(ws, "수식 정의", "분석 엔진과 검증 엑셀에서 사용하는 주요 산식 및 처리 원칙입니다.")
    headers = ["영역", "항목", "산식", "부호·처리 기준", "코드 위치"]
    _write_headers(ws, header_row, headers)
    rows = [
        ("공통", "증감", "비교값 - 기준값", "단순 증감", "forecast/comparison.py"),
        ("판매", "수량효과", "Pool별 (Comparison 총수량-Base 총수량)×Σ(Base Mix×Base GP/unit)", "PCS/LENGTH 분리; 개선 + / 악화 -", "forecast/analysis/sales_effects.py"),
        ("판매", "Mix효과", "Pool별 Comparison 총수량×Σ((Comparison Mix-Base Mix)×Base GP/unit)", "제품군 내부 SKU 선합산", "forecast/analysis/sales_effects.py"),
        ("판매", "순수 단가효과", "비교수량×(비교외화단가-기준외화단가)×(기준FX+비교FX)÷2", "환율효과와 합계가 원화 단가효과에 일치", "forecast/sales_comparison.py"),
        ("판매", "매출환율효과", "비교수량×(비교FX-기준FX)×(기준외화단가+비교외화단가)÷2", "KRW/USD", "forecast/sales_comparison.py"),
        ("판매", "고객배송 운반비 효과", "기준 관세제외 운반비-비교 관세제외 운반비", "판매단가 효과에 1회 포함; 판관비 Bridge 0", "forecast/analysis/sales_effects.py"),
        ("원부재료", "분해 원칙", "부직포 단가(환율 제외)+부직포 엔화+부직포 제외 원재료", "MCM·수율/사용량 독립효과 금지", "forecast/analysis/material_effects.py"),
        ("생산", "조업도 기준", "SAP 수불부 생산입고", "MES는 정합성 확인 보조", "분석 설정"),
        ("제조경비", "외주가공비 수량", "일반 외주가공 대상 수량", "MCM 관련 수량 제외", "분석 설정"),
        ("제조경비", "최종 제조경비 Effect", "조업도+원단위+고정비 발생효과", "재고실현율은 참고지표이며 multiplier 미적용", "forecast/analysis/manufacturing_effects.py"),
        ("재고시차", "Manufactured COGS Effect", "Base Manufactured COGS-Comparison Manufactured COGS", "제품+반제품 COGS", "forecast/analysis/inventory_effects.py"),
        ("재고시차", "Current Manufacturing Cost Effect", "Base Current Manufacturing Cost-Comparison Current Manufacturing Cost", "당기투입제조원가", "forecast/analysis/inventory_effects.py"),
        ("재고시차", "Gross Inventory Timing", "Manufactured COGS Effect-Current Manufacturing Cost Effect", "Evidence only; non-additive", "forecast/analysis/inventory_effects.py"),
        ("재고시차", "Core Manufactured COGS Overlap", "Core Quantity overlap+Core Mix overlap", "Inventory Timing 내부 차감; 비가산", "forecast/analysis/core_cogs_overlap.py"),
        ("재고시차", "Net Inventory Timing Effect", "Gross Inventory Timing-Core Manufactured COGS Overlap", "개선 + / 악화 -; 공식 additive Effect", "forecast/analysis/inventory_effects.py"),
        ("당기제조원가 Basis", "Existing Driver subtotal", "Raw Material Effect+Manufacturing Activity+Unit+Fixed", "기존 공식 불변", "forecast/analysis/current_cost_basis.py"),
        ("당기제조원가 Basis", "Basis Gap", "Current Manufacturing Cost Effect-Existing Driver subtotal", "설명 Evidence only; Effect/Residual/Plug 아님", "forecast/analysis/current_cost_basis.py"),
        ("손익 브리지", "비용 효과", "기준 비용-비교 비용", "비용 감소는 손익 개선 +", "forecast/comparison.py"),
        ("정합성", "잔여차이", "영업이익 증감-세부효과 합계", "허용오차 이내 PASS", "forecast/comparison.py"),
    ]
    for row in rows:
        ws.append(row)
    _style_data_sheet(ws, header_row)


def _mapping_specs(mapping: dict[str, Any]) -> list[tuple[str, str, str, Any]]:
    output: list[tuple[str, str, str, Any]] = []
    for code, row in mapping.get("pnl_rows", {}).items():
        output.append(("손익계산서", code, mapping.get("pnl_labels", {}).get(code, code), row))
    for code, spec in mapping.get("products", {}).items():
        output.append(("판매 제품", f"{code}.quantity", f"{spec.get('label', code)} 수량", spec.get("quantity_row")))
        output.append(("판매 제품", f"{code}.amount", f"{spec.get('label', code)} 매출액", spec.get("amount_row")))
    for code, spec in mapping.get("sales_groups", {}).items():
        output.append(("판매 제품군", f"{code}.quantity", f"{spec.get('label', code)} 수량", spec.get("quantity_row")))
        output.append(("판매 제품군", f"{code}.amount", f"{spec.get('label', code)} 매출액", spec.get("amount_row")))
        output.append(("판매 제품군", f"{code}.cogs", f"{spec.get('label', code)} 매출원가", spec.get("cogs_row")))
    for code, row in mapping.get("production_rows", {}).items():
        output.append(("생산", code, mapping.get("production_labels", {}).get(code, code), row))
    for code, row in mapping.get("mcm_rows", {}).items():
        output.append(("MCM", code, mapping.get("mcm_labels", {}).get(code, code), row))
    for code, spec in mapping.get("cost_rows", {}).items():
        output.append(("비용 요약", code, mapping.get("cost_labels", {}).get(code, code), spec))
    for code, spec in mapping.get("effect_rows", {}).items():
        output.append(("손익 브리지", code, mapping.get("effect_labels", {}).get(code, code), spec))
    return output


def _analysis_source_specs(payload: dict[str, Any]) -> list[tuple[str, str, str, Any]]:
    adapter = payload.get("analysis_adapter", {})
    material = adapter.get("material", {})
    front = material.get("front_process", {})
    back = material.get("back_process", {})
    output: list[tuple[str, str, str, Any]] = []
    if material.get("jpy_fx_row"):
        output.append(("원부재료", "jpy_fx", "엔화환율(KRW/JPY)", material["jpy_fx_row"]))
    for key, label in (
        ("nonwoven_quantity_row", "전공정 부직포 생산출고 수량"),
        ("nonwoven_amount_row", "전공정 부직포 생산출고 금액"),
        ("nonwoven_unit_row", "전공정 부직포 생산출고 단가"),
        ("other_quantity_row", "부직포 제외 전공정 원재료 생산출고 수량"),
        ("other_amount_row", "부직포 제외 전공정 원재료 생산출고 금액"),
        ("other_unit_row", "부직포 제외 전공정 원재료 생산출고 단가"),
        ("total_amount_row", "전공정 원재료 생산출고 합계"),
    ):
        if front.get(key):
            output.append(("원부재료", key, label, front[key]))
    if back.get("source_start_row") and back.get("source_end_row"):
        for row in range(int(back["source_start_row"]), int(back["source_end_row"]) + 1):
            output.append(("원부재료", f"back_process_{row}", f"후공정 원재료 생산출고 {row}행", row))
    for row in payload.get("manufacturing_input_rows", ()):
        output.append((
            "제조경비",
            f"manufacturing_{int(row)}",
            f"제조경비 명세 {int(row)}행",
            int(row),
        ))
    for key, row in adapter.get("manufacturing", {}).get("front_ratio_rows", {}).items():
        output.append(("제조경비", f"front_ratio_{key}", f"전공정 가공비 투입비율({key})", row))
    inventory = adapter.get("inventory_timing", {})
    for key in (
        "current_manufacturing_cost", "finished_goods_cogs", "semi_finished_goods_cogs"
    ):
        source = inventory.get(key, {})
        if source.get("row"):
            output.append((
                "재고시차", key, source.get("business_source", key), source["row"]
            ))
    for key, source in inventory.get(
        "current_manufacturing_cost_components", {}
    ).items():
        if source.get("row"):
            output.append((
                "당기제조원가 Basis",
                key,
                source.get("business_source", key),
                source["row"],
            ))
    for key, source in inventory.get(
        "current_manufacturing_cost_formula_relationships", {}
    ).items():
        if source.get("row"):
            output.append((
                "당기제조원가 Basis",
                f"formula_{key}",
                key,
                source["row"],
            ))
    for group, source in inventory.get("opening_inventory_units", {}).items():
        output.append((
            "재고시차 기초재고", f"{group}.quantity", f"{group} 기초재고 수량",
            list(source.get("quantity_rows", ())),
        ))
        output.append((
            "재고시차 기초재고", f"{group}.amount", f"{group} 기초재고 금액",
            list(source.get("amount_rows", ())),
        ))
    return output


def _expand_spec(spec: Any) -> list[tuple[int, int, str]]:
    if isinstance(spec, int):
        return [(spec, 1, "direct")]
    if isinstance(spec, list):
        return [(int(row), 1, "add") for row in spec]
    if isinstance(spec, dict):
        rows = [(int(row), 1, "add") for row in spec.get("add", [])]
        rows.extend((int(row), -1, "subtract") for row in spec.get("subtract", []))
        return rows
    return []


def _write_source_trace(
    ws,
    baseline_path: str | Path,
    comparison_path: str | Path,
    mapping_path: str | Path,
    months: tuple[int, ...],
) -> None:
    header_row = _write_title(ws, "원천셀 추적", "모형별·월별로 실제 읽은 셀, 저장 수식, 계산값과 집계 부호를 표시합니다.")
    headers = ["모형", "영역", "지표코드", "지표명", "월", "시트", "셀", "집계부호", "집계규칙", "원본수식", "엔진 사용값"]
    _write_headers(ws, header_row, headers)
    payload = json.loads(Path(mapping_path).read_text(encoding="utf-8"))
    mapping = payload["comparison"]
    specs = [*_mapping_specs(mapping), *_analysis_source_specs(payload)]
    models = [("기준", GoldenWorkbook(baseline_path)), ("비교", GoldenWorkbook(comparison_path))]
    for side, workbook in models:
        for domain, code, label, spec in specs:
            for row_number, sign, rule in _expand_spec(spec):
                for month in months:
                    cell_ref = f"{MONTH_COLUMNS[int(month)]}{row_number}"
                    source_formula = workbook.formulas.get(cell_ref, "")
                    ws.append([
                        side, domain, code, label, f"{month}월", "Data", cell_ref, sign, rule,
                        f"'{source_formula}" if source_formula else "",
                        _number(workbook.value(cell_ref)),
                    ])
    _style_data_sheet(ws, header_row, money_columns=(11,))


def _write_stored_source_provenance(ws, result: dict[str, Any]) -> None:
    """Write pinned input identity without reopening either source workbook."""
    header_row = _write_title(
        ws,
        "원천모형 Provenance",
        "완료 Result에 고정된 입력 식별자와 SHA-256입니다. 원천 XLSX는 다운로드 시 다시 열지 않습니다.",
    )
    _write_headers(ws, header_row, ["항목", "값"])
    provenance = result.get("evidence_provenance")
    if not isinstance(provenance, dict):
        provenance = {}
    for key in (
        "result_id",
        "job_id",
        "baseline_model_id",
        "comparison_model_id",
        "baseline_workbook_sha256",
        "comparison_workbook_sha256",
        "engine_version",
        "mapping_version",
        "mapping_hash",
        "result_schema_version",
        "analysis_request",
    ):
        value = provenance.get(key)
        if isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False, sort_keys=True)
        ws.append([key, value])
    _style_data_sheet(ws, header_row)


def build_comparison_audit_workbook(
    *,
    result: dict[str, Any],
    sales_rows: Iterable[Any],
    sales_totals: dict[str, float],
    baseline_fx: float,
    comparison_fx: float,
    baseline_path: str | Path | None = None,
    comparison_path: str | Path | None = None,
    mapping_path: str | Path,
) -> bytes:
    """Build a formula-bearing audit workbook for the current comparison result."""
    workbook = Workbook()
    workbook.remove(workbook.active)
    workbook.calculation.fullCalcOnLoad = True
    workbook.calculation.forceFullCalc = True
    workbook.calculation.calcMode = "auto"

    _write_readme(workbook.create_sheet("README"), result, baseline_fx, comparison_fx)
    sales_cells = write_sales_evidence(
        workbook.create_sheet("판매효과_근거"),
        result,
        sales_rows,
        sales_totals,
        baseline_fx,
        comparison_fx,
    )
    material_cells = write_material_evidence(
        workbook.create_sheet("원부재료_근거"), result
    )
    manufacturing_cells = write_manufacturing_evidence(
        workbook.create_sheet("제조경비_근거"), result
    )
    inventory_cells = _write_inventory_timing(
        workbook.create_sheet("재고원가반영시차_근거"), result
    )
    merchandise_cells = write_merchandise_link(
        workbook.create_sheet("상품원가검증")
    )
    sga_cells = write_sga_evidence(workbook.create_sheet("판관비_검증"), result)
    evidence_cells = {
        "sales": sales_cells,
        "material": material_cells,
        "manufacturing": manufacturing_cells,
        "sga": sga_cells,
    }
    _write_current_cost_basis(
        workbook.create_sheet("당기제조원가_기준차이"), result, evidence_cells
    )
    bridge_cells: dict[str, tuple[str, str]] = {
        code: ("판매효과_근거", cell)
        for code, cell in sales_cells.items()
        if code in {"sales_quantity", "sales_mix", "sales_price", "sales_fx", "tariff"}
    }
    if material_cells.get("material_total"):
        bridge_cells["material_total"] = (
            "원부재료_근거", str(material_cells["material_total"])
        )
    if manufacturing_cells.get("manufacturing_realized"):
        bridge_cells["manufacturing_realized"] = (
            "제조경비_근거", str(manufacturing_cells["manufacturing_realized"])
        )
    bridge_cells["inventory_timing"] = (
        "재고원가반영시차_근거", inventory_cells["inventory_timing"]
    )
    bridge_cells["gross_inventory_timing"] = (
        "재고원가반영시차_근거", inventory_cells["gross_inventory_timing"]
    )
    bridge_cells["core_cogs_quantity_overlap"] = (
        "재고원가반영시차_근거", inventory_cells["core_quantity_overlap"]
    )
    bridge_cells["core_cogs_mix_overlap"] = (
        "재고원가반영시차_근거", inventory_cells["core_mix_overlap"]
    )
    bridge_cells["core_manufactured_cogs_overlap"] = (
        "재고원가반영시차_근거", inventory_cells["core_total_overlap"]
    )
    bridge_cells["core_overlap_policy"] = (
        "재고원가반영시차_근거", inventory_cells["core_overlap_policy"]
    )
    for code in ("sga_variable", "sga_fixed"):
        if sga_cells.get(code):
            bridge_cells[code] = ("판관비_검증", sga_cells[code])
    final_bridge_cells = write_final_bridge(
        workbook.create_sheet("최종Bridge_검증"),
        result,
        bridge_cells,
        ("상품원가검증", merchandise_cells["scope_validation"]),
    )
    write_residual_rca(
        workbook.create_sheet("Residual_RCA"),
        result,
        final_bridge_cells,
    )
    write_sales_cogs_basis(
        workbook.create_sheet("Sales_COGS_Basis"),
        result,
        final_bridge_cells,
    )
    write_sales_cogs_scope(
        workbook.create_sheet("Sales_COGS_Scope"),
        result,
    )
    _write_formula_catalog(workbook.create_sheet("수식_정의"))
    months = tuple(int(month) for month in result.get("period", {}).get("months", ()))
    source_sheet = workbook.create_sheet("원천셀_추적")
    if baseline_path is not None and comparison_path is not None:
        _write_source_trace(source_sheet, baseline_path, comparison_path, mapping_path, months)
    else:
        _write_stored_source_provenance(source_sheet, result)

    required = {
        "README", "판매효과_근거", "원부재료_근거", "제조경비_근거",
        "재고원가반영시차_근거", "상품원가검증", "최종Bridge_검증", "Residual_RCA",
        "Sales_COGS_Basis", "Sales_COGS_Scope",
        "당기제조원가_기준차이", "판관비_검증", "수식_정의", "원천셀_추적",
    }
    missing = required.difference(workbook.sheetnames)
    if missing:
        raise ValueError(f"검증 엑셀 필수 시트 누락: {sorted(missing)}")
    if not any(
        isinstance(cell.value, str) and cell.value.startswith("=")
        for row in workbook["판매효과_근거"].iter_rows()
        for cell in row
    ):
        raise ValueError("판매효과 검증 수식이 생성되지 않았습니다.")

    _validate_formula_integrity(workbook)

    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def write_comparison_audit_workbook(
    output_path: str | Path,
    **kwargs: Any,
) -> None:
    """Write the existing bounded in-memory exporter payload to a temp artifact.

    The exporter itself is intentionally unchanged: this adapter prevents the
    HTTP layer from making another full workbook copy and enables FileResponse
    streaming plus deterministic cleanup.
    """
    Path(output_path).write_bytes(build_comparison_audit_workbook(**kwargs))
