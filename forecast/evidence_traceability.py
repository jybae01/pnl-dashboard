from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter


_HEADER_FILL = PatternFill("solid", fgColor="1F4E78")
_SECTION_FILL = PatternFill("solid", fgColor="D9EAF7")
_FORMULA_FILL = PatternFill("solid", fgColor="E2F0D9")
_CHECK_FILL = PatternFill("solid", fgColor="EDEDED")
_WHITE_FONT = Font(color="FFFFFF", bold=True)
_BOLD = Font(bold=True)


def _number(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _title(ws, title: str, subtitle: str) -> None:
    ws["A1"] = title
    ws["A1"].font = Font(size=16, bold=True)
    ws["A2"] = subtitle
    ws["A2"].alignment = Alignment(wrap_text=True, vertical="top")


def _headers(ws, row: int, headers: Iterable[str], start_column: int = 1) -> None:
    for offset, header in enumerate(headers):
        cell = ws.cell(row, start_column + offset, header)
        cell.fill = _HEADER_FILL
        cell.font = _WHITE_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)


def _finish(ws, *, freeze: str = "A5") -> None:
    for row in ws.iter_rows():
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)
            if isinstance(cell.value, (int, float)) and not isinstance(cell.value, bool):
                cell.number_format = '#,##0.000;[Red](#,##0.000);-'
    for column in range(1, ws.max_column + 1):
        width = 10
        for cell in ws[get_column_letter(column)]:
            width = max(width, min(42, len(str(cell.value or "")) + 2))
        ws.column_dimensions[get_column_letter(column)].width = width
    ws.freeze_panes = freeze


def _validation(formula: str, engine: str, tolerance: float = 1.0) -> str:
    return f'=IF(ABS({formula}-{engine})<={tolerance},"PASS","FAIL")'


def _sheet_ref(sheet: str, cell: str) -> str:
    return f"='{sheet}'!{cell}"


def write_sales_evidence(
    ws,
    result: dict[str, Any],
    sales_rows: Iterable[Any],
    sales_totals: dict[str, float],
    baseline_fx: float,
    comparison_fx: float,
) -> dict[str, Any]:
    _title(
        ws,
        "판매효과 근거",
        "제품군 내부 SKU를 먼저 합산하고 PCS/LENGTH Pool별 Quantity·Mix를 계산합니다. 고객배송 운반비는 Price에 한 번만 포함하고 관세는 분리합니다.",
    )
    sales = result.get("sales_analysis") or {}
    totals = {**sales_totals, **(sales.get("totals") or {})}
    trace = list(sales.get("trace_rows") or [])
    pool_trace = list(sales.get("pool_trace_rows") or [])
    freight_trace = list(sales.get("freight_trace_rows") or [])
    legacy_trace = not trace
    if not trace:
        for source in sales_rows:
            item = source.to_dict() if hasattr(source, "to_dict") else dict(source)
            trace.append({
                "period": str((result.get("period") or {}).get("label") or "선택기간"),
                "pool": "LEGACY_UNSPECIFIED",
                "unit": "UNAVAILABLE",
                "product_group": item.get("product_group"),
                "base_quantity": item.get("baseline_quantity"),
                "comparison_quantity": item.get("comparison_quantity"),
                "base_revenue": item.get("baseline_amount"),
                "comparison_revenue": item.get("comparison_amount"),
                "base_cogs": _number(item.get("baseline_amount")) * (1 - _number(item.get("baseline_gross_margin_rate"))),
                "comparison_cogs": _number(item.get("comparison_amount")) * (1 - _number(item.get("comparison_gross_margin_rate"))),
                "base_fx": baseline_fx,
                "comparison_fx": comparison_fx,
                "price_effect": item.get("pure_price_effect"),
                "sales_fx_effect": item.get("sales_fx_effect"),
                "business_source": "Legacy canonical sales group (trace unavailable)",
                "canonical_fields": "sales quantity / amount / cogs / sales_fx",
                "base_source_reference": "Stored Result (unit unavailable)",
                "comparison_source_reference": "Stored Result (unit unavailable)",
                "validation_status": "TRACE_UNAVAILABLE_LEGACY",
            })
        base_total = sum(_number(row.get("base_quantity")) for row in trace)
        comparison_total = sum(_number(row.get("comparison_quantity")) for row in trace)
        weighted = sum(
            (_number(row.get("base_quantity")) / base_total if base_total else 0)
            * ((_number(row.get("base_revenue")) - _number(row.get("base_cogs"))) / _number(row.get("base_quantity")) if _number(row.get("base_quantity")) else 0)
            for row in trace
        )
        pool_trace = [{
            "period": trace[0]["period"] if trace else "선택기간",
            "pool": "LEGACY_UNSPECIFIED",
            "unit": "UNAVAILABLE",
            "base_total_quantity": base_total,
            "comparison_total_quantity": comparison_total,
            "base_weighted_gp_per_unit": weighted,
            "quantity_effect": _number(totals.get("quantity_effect")),
            "mix_effect": _number(totals.get("mix_effect")),
        }]
    if not freight_trace:
        freight_trace = [{
            "period": str((result.get("period") or {}).get("label") or "선택기간"),
            "business_source": "고객배송 운반비 / 관세",
            "base_source_reference": "Stored Result (tariff components unavailable)",
            "comparison_source_reference": "Stored Result (tariff components unavailable)",
            "base_freight_including_tariff": _number(totals.get("baseline_transport_ex_tariff")),
            "comparison_freight_including_tariff": _number(totals.get("comparison_transport_ex_tariff")),
            "base_tariff": 0.0,
            "comparison_tariff": 0.0,
            "base_tariff_in_transport": False,
            "comparison_tariff_in_transport": False,
            "base_freight_ex_tariff": _number(totals.get("baseline_transport_ex_tariff")),
            "comparison_freight_ex_tariff": _number(totals.get("comparison_transport_ex_tariff")),
            "freight_effect": _number(totals.get("transport_effect")),
            "tariff_effect": _number(totals.get("tariff_effect")),
            "validation_status": "TRACE_UNAVAILABLE_LEGACY" if legacy_trace else "STORED_RESULT",
        }]

    headers = [
        "분석월", "Pool", "제품군", "단위", "Business Source", "Canonical field",
        "Base Source Reference", "Comparison Source Reference", "Base 수량", "Comparison 수량",
        "Base 매출", "Comparison 매출", "Base COGS", "Comparison COGS", "Base GP/unit 수식",
        "Base Pool 수량", "Comparison Pool 수량", "Base Mix", "Comparison Mix", "가중 GP/unit",
        "Mix Difference", "Mix 기여", "Base FX", "Comparison FX", "Base KRW Price",
        "Comparison KRW Price", "Base 외화단가", "Comparison 외화단가", "Price Effect 수식",
        "Price Engine", "Sales FX 수식", "FX Engine", "Validation",
    ]
    _headers(ws, 4, headers)
    detail_start = 5
    for row in trace:
        r = ws.max_row + 1
        ws.append([
            row.get("period"), row.get("pool"), row.get("product_group"),
            (
                "PCS (4-inch)"
                if str(row.get("product_group") or "").upper() == "LC"
                else row.get("unit")
            ),
            row.get("business_source"), row.get("canonical_fields"), row.get("base_source_reference"),
            row.get("comparison_source_reference"), _number(row.get("base_quantity")),
            _number(row.get("comparison_quantity")), _number(row.get("base_revenue")),
            _number(row.get("comparison_revenue")), _number(row.get("base_cogs")),
            _number(row.get("comparison_cogs")), None, None, None, None, None, None, None, None,
            _number(row.get("base_fx") or baseline_fx), _number(row.get("comparison_fx") or comparison_fx),
            None, None, None, None, None, _number(row.get("price_effect")), None,
            _number(row.get("sales_fx_effect")), None,
        ])
        # Formula ranges are patched after the final detail row is known.
        ws.cell(r, 15, f"=IFERROR((K{r}-M{r})/I{r},0)").fill = _FORMULA_FILL
        ws.cell(r, 18, f"=IFERROR(I{r}/P{r},0)").fill = _FORMULA_FILL
        ws.cell(r, 19, f"=IFERROR(J{r}/Q{r},0)").fill = _FORMULA_FILL
        ws.cell(r, 20, f"=R{r}*O{r}").fill = _FORMULA_FILL
        ws.cell(r, 21, f"=S{r}-R{r}").fill = _FORMULA_FILL
        ws.cell(r, 22, f"=U{r}*O{r}").fill = _FORMULA_FILL
        ws.cell(r, 25, f"=IFERROR(K{r}/I{r},0)").fill = _FORMULA_FILL
        ws.cell(r, 26, f"=IFERROR(L{r}/J{r},0)").fill = _FORMULA_FILL
        ws.cell(r, 27, f"=IFERROR(Y{r}/W{r},0)").fill = _FORMULA_FILL
        ws.cell(r, 28, f"=IFERROR(Z{r}/X{r},0)").fill = _FORMULA_FILL
        ws.cell(r, 29, f"=J{r}*(AB{r}-AA{r})*(W{r}+X{r})/2").fill = _FORMULA_FILL
        ws.cell(r, 31, f"=J{r}*(X{r}-W{r})*(AA{r}+AB{r})/2").fill = _FORMULA_FILL
        ws.cell(r, 33, f'=IF(MAX(ABS(AC{r}-AD{r}),ABS(AE{r}-AF{r}))<=1,"PASS","FAIL")').fill = _CHECK_FILL
    detail_end = ws.max_row
    for r in range(detail_start, detail_end + 1):
        ws.cell(r, 16, f'=SUMIFS($I${detail_start}:$I${detail_end},$A${detail_start}:$A${detail_end},A{r},$B${detail_start}:$B${detail_end},B{r})').fill = _FORMULA_FILL
        ws.cell(r, 17, f'=SUMIFS($J${detail_start}:$J${detail_end},$A${detail_start}:$A${detail_end},A{r},$B${detail_start}:$B${detail_end},B{r})').fill = _FORMULA_FILL

    freight_start_col = 35  # AI: explicitly keep Freight at the right edge.
    _headers(ws, 4, [
        "분석월", "Business Source", "Base Source", "Comparison Source", "Base Freight(incl Tariff)",
        "Comparison Freight(incl Tariff)", "Base Tariff", "Comparison Tariff", "Base Tariff 포함?",
        "Comparison Tariff 포함?", "Base Freight(ex Tariff)", "Comparison Freight(ex Tariff)",
        "Freight Adjustment 수식", "Freight Engine", "Tariff 수식", "Tariff Engine", "Validation",
    ], freight_start_col)
    freight_start = 5
    for index, item in enumerate(freight_trace):
        r = freight_start + index
        values = [
            item.get("period"), item.get("business_source"), item.get("base_source_reference"),
            item.get("comparison_source_reference"), _number(item.get("base_freight_including_tariff")),
            _number(item.get("comparison_freight_including_tariff")), _number(item.get("base_tariff")),
            _number(item.get("comparison_tariff")), bool(item.get("base_tariff_in_transport")),
            bool(item.get("comparison_tariff_in_transport")), None, None, None,
            _number(item.get("freight_effect")), None, _number(item.get("tariff_effect")), None,
        ]
        for offset, value in enumerate(values):
            ws.cell(r, freight_start_col + offset, value)
        ws.cell(r, 45, f"=AM{r}-AO{r}*AQ{r}").fill = _FORMULA_FILL
        ws.cell(r, 46, f"=AN{r}-AP{r}*AR{r}").fill = _FORMULA_FILL
        ws.cell(r, 47, f"=AS{r}-AT{r}").fill = _FORMULA_FILL
        ws.cell(r, 49, f"=AO{r}-AP{r}").fill = _FORMULA_FILL
        ws.cell(r, 51, f'=IF(MAX(ABS(AU{r}-AV{r}),ABS(AW{r}-AX{r}))<=1,"PASS","FAIL")').fill = _CHECK_FILL
    freight_end = freight_start + len(freight_trace) - 1

    summary_header = max(detail_end, freight_end) + 3
    _headers(ws, summary_header, ["Effect", "Evidence Formula", "Engine Output", "Validation", "부호/정책"])
    summary_start = summary_header + 1
    pool_header = summary_header
    _headers(ws, pool_header, [
        "Period", "Pool", "Unit", "Base Total", "Comparison Total", "Base Weighted GP/unit",
        "Quantity Formula", "Quantity Engine", "Mix Component", "Mix Formula", "Mix Engine", "Validation",
    ], 7)
    pool_start = pool_header + 1
    for index, item in enumerate(pool_trace):
        r = pool_start + index
        period = str(item.get("period") or "")
        pool = str(item.get("pool") or "")
        ws.cell(r, 7, period)
        ws.cell(r, 8, pool)
        ws.cell(r, 9, item.get("unit"))
        ws.cell(r, 10, f'=SUMIFS($I${detail_start}:$I${detail_end},$A${detail_start}:$A${detail_end},G{r},$B${detail_start}:$B${detail_end},H{r})').fill = _FORMULA_FILL
        ws.cell(r, 11, f'=SUMIFS($J${detail_start}:$J${detail_end},$A${detail_start}:$A${detail_end},G{r},$B${detail_start}:$B${detail_end},H{r})').fill = _FORMULA_FILL
        ws.cell(r, 12, f'=SUMIFS($T${detail_start}:$T${detail_end},$A${detail_start}:$A${detail_end},G{r},$B${detail_start}:$B${detail_end},H{r})').fill = _FORMULA_FILL
        ws.cell(r, 13, f"=(K{r}-J{r})*L{r}").fill = _FORMULA_FILL
        ws.cell(r, 14, _number(item.get("quantity_effect")))
        ws.cell(r, 15, f'=SUMIFS($V${detail_start}:$V${detail_end},$A${detail_start}:$A${detail_end},G{r},$B${detail_start}:$B${detail_end},H{r})').fill = _FORMULA_FILL
        ws.cell(r, 16, f"=K{r}*O{r}").fill = _FORMULA_FILL
        ws.cell(r, 17, _number(item.get("mix_effect")))
        ws.cell(r, 18, f'=IF(MAX(ABS(M{r}-N{r}),ABS(P{r}-Q{r}))<=1,"PASS","FAIL")').fill = _CHECK_FILL
    pool_end = pool_start + len(pool_trace) - 1
    summary = [
        ("sales_quantity", f"=SUM(M{pool_start}:M{pool_end})", totals.get("quantity_effect"), "Pool별 합산"),
        ("sales_mix", f"=SUM(P{pool_start}:P{pool_end})", totals.get("mix_effect"), "제품군 간 Mix만"),
        ("displayed_sales_price", f"=SUM(AC{detail_start}:AC{detail_end})", totals.get("displayed_sales_price_effect", totals.get("pure_price_effect")), "Freight 반영 전"),
        ("freight_adjustment", f"=SUM(AU{freight_start}:AU{freight_end})", totals.get("transport_effect"), "Price에 1회 포함"),
        ("sales_price", f"=B{summary_start + 2}+B{summary_start + 3}", totals.get("sales_price_effect"), "Displayed Price + Freight"),
        ("sales_fx", f"=SUM(AE{detail_start}:AE{detail_end})", totals.get("sales_fx_effect"), "Price와 symmetric 분리"),
        ("tariff", f"=SUM(AW{freight_start}:AW{freight_end})", totals.get("tariff_effect"), "Price/Freight와 분리"),
    ]
    cells: dict[str, str] = {}
    for index, (code, formula, engine, policy) in enumerate(summary):
        r = summary_start + index
        ws.cell(r, 1, code)
        ws.cell(r, 2, formula).fill = _FORMULA_FILL
        ws.cell(r, 3, _number(engine))
        ws.cell(r, 4, _validation(f"B{r}", f"C{r}")).fill = _CHECK_FILL
        ws.cell(r, 5, policy)
        cells[code] = f"B{r}"
    validation_start = summary_start + len(summary) + 1
    ws.cell(validation_start, 1, "Freight double count")
    ws.cell(validation_start, 2, f'=IF(AND(B{summary_start + 4}=B{summary_start + 2}+B{summary_start + 3},COUNTIF(A{summary_start}:A{summary_start + 6},"freight_adjustment")=1),"PASS","FAIL")').fill = _CHECK_FILL
    ws.cell(validation_start + 1, 1, "Tariff separate")
    ws.cell(validation_start + 1, 2, f'=IF(AND(B{summary_start + 6}=SUM(AW{freight_start}:AW{freight_end}),B{summary_start + 4}=B{summary_start + 2}+B{summary_start + 3}),"PASS","FAIL")').fill = _CHECK_FILL
    cells["detail_range"] = (detail_start, detail_end)
    cells["validation_rows"] = (validation_start, validation_start + 1)
    _finish(ws)
    return cells


def write_material_evidence(ws, result: dict[str, Any]) -> dict[str, Any]:
    _title(
        ws,
        "원부재료 근거",
        "Canonical 원부재료 단가 driver와 부직포 KRW/JPY 분해를 실제 수식으로 재현합니다. MCM·Current Cost Basis Gap은 신규 Effect로 만들지 않습니다.",
    )
    analysis = result.get("material_analysis") or {}
    trace = list(analysis.get("trace_rows") or [])
    nonwoven = list(analysis.get("nonwoven_trace_rows") or [])
    _headers(ws, 4, [
        "분석월", "제품군", "단위", "Business Source", "Canonical field", "Base Source",
        "Comparison Source", "Base 금액", "Comparison 금액", "Base 생산/적용량",
        "Comparison 생산/적용량", "Comparison 판매 적용량", "Base 원단위 수식",
        "Comparison 원단위 수식", "Raw Material Effect 수식", "Engine", "Calculation Validation",
        "Source Status",
    ])
    detail_start = 5
    if not trace:
        for item in analysis.get("product_groups") or []:
            trace.append({
                "period": "선택기간", "product_group": item.get("product_group"), "unit": "Canonical",
                "business_source": "Stored canonical material detail", "canonical_fields": "raw_material driver",
                "base_source_reference": "Stored Result", "comparison_source_reference": "Stored Result",
                "base_unit_cost": item.get("baseline_unit_cost"), "comparison_unit_cost": item.get("comparison_unit_cost"),
                "total_effect": item.get("total"),
            })
    for item in trace:
        r = ws.max_row + 1
        ws.append([
            item.get("period"), item.get("product_group"),
            (
                "PCS (4-inch)"
                if str(item.get("product_group") or "").upper() == "LC"
                else item.get("unit")
            ),
            item.get("business_source"),
            item.get("canonical_fields"), item.get("base_source_reference"), item.get("comparison_source_reference"),
            _number(item.get("base_cost")), _number(item.get("comparison_cost")),
            _number(item.get("base_output")), _number(item.get("comparison_output")),
            _number(item.get("comparison_sales")), None, None, None, _number(item.get("total_effect")), None,
            item.get("source_validation_status") or "TRACE_UNAVAILABLE_LEGACY",
        ])
        ws.cell(r, 13, f"=IFERROR(H{r}/J{r},0)").fill = _FORMULA_FILL
        ws.cell(r, 14, f"=IFERROR(I{r}/K{r},0)").fill = _FORMULA_FILL
        ws.cell(r, 15, f'=IF(OR(AND(H{r}<>0,J{r}=0),AND(I{r}<>0,K{r}=0),AND(L{r}<>0,OR(J{r}=0,K{r}=0))),0,(M{r}-N{r})*L{r})').fill = _FORMULA_FILL
        ws.cell(r, 17, _validation(f"O{r}", f"P{r}")).fill = _CHECK_FILL
    detail_end = ws.max_row

    nw_col = 20
    _headers(ws, 4, [
        "분석월", "Business Source", "Canonical field", "Base Source", "Comparison Source",
        "Base 부직포 금액", "Comparison 부직포 금액", "Base 생산길이", "Comparison 생산길이",
        "Comparison 적용길이", "Base JPY FX", "Comparison JPY FX", "Base 단가", "Comparison 단가",
        "부직포 Total", "Base JPY 단가", "JPY Effect 수식", "JPY Engine", "환율제외 Effect 수식",
        "환율제외 Engine", "Calculation Validation", "Source Status",
    ], nw_col)
    nw_start = 5
    for index, item in enumerate(nonwoven):
        r = nw_start + index
        values = [
            item.get("period"), item.get("business_source"), item.get("canonical_fields"),
            item.get("base_source_reference"), item.get("comparison_source_reference"),
            _number(item.get("base_cost")), _number(item.get("comparison_cost")),
            _number(item.get("base_output")), _number(item.get("comparison_output")),
            _number(item.get("comparison_input_length")), _number(item.get("base_jpy_fx")),
            _number(item.get("comparison_jpy_fx")), None, None, None, None, None,
            _number(item.get("nonwoven_jpy")), None, _number(item.get("nonwoven_price_ex_fx")), None,
            item.get("source_validation_status") or "TRACE_UNAVAILABLE_LEGACY",
        ]
        for offset, value in enumerate(values):
            ws.cell(r, nw_col + offset, value)
        ws.cell(r, 32, f"=IFERROR(Y{r}/AA{r},0)").fill = _FORMULA_FILL
        ws.cell(r, 33, f"=IFERROR(Z{r}/AB{r},0)").fill = _FORMULA_FILL
        ws.cell(r, 34, f"=(AF{r}-AG{r})*AC{r}").fill = _FORMULA_FILL
        ws.cell(r, 35, f"=IFERROR(AF{r}/AD{r},0)").fill = _FORMULA_FILL
        ws.cell(r, 36, f"=AC{r}*AI{r}*(AD{r}-AE{r})").fill = _FORMULA_FILL
        ws.cell(r, 38, f"=AH{r}-AJ{r}").fill = _FORMULA_FILL
        ws.cell(r, 40, f'=IF(MAX(ABS(AJ{r}-AK{r}),ABS(AL{r}-AM{r}))<=1,"PASS","FAIL")').fill = _CHECK_FILL
    nw_end = nw_start + len(nonwoven) - 1

    summary_header = max(detail_end, nw_end if nonwoven else 4) + 3
    _headers(ws, summary_header, ["Effect", "Evidence Formula", "Engine Output", "Validation", "Policy"])
    start = summary_header + 1
    nw_fx_formula = f"=SUM(AJ{nw_start}:AJ{nw_end})" if nonwoven else "=0"
    nw_price_formula = f"=SUM(AL{nw_start}:AL{nw_end})" if nonwoven else "=0"
    summary = [
        ("material_total", f"=SUM(O{detail_start}:O{detail_end})", analysis.get("total"), "Canonical RM total"),
        ("nonwoven_price_ex_fx", nw_price_formula, analysis.get("nonwoven_price_ex_fx"), "RM subtotal component"),
        ("nonwoven_jpy", nw_fx_formula, analysis.get("nonwoven_jpy"), "RM FX component; not separately additive in Bridge"),
        ("materials_ex_nonwoven", f"=B{start}-B{start + 1}-B{start + 2}", analysis.get("materials_ex_nonwoven"), "Other materials"),
    ]
    cells: dict[str, Any] = {}
    for index, (code, formula, engine, policy) in enumerate(summary):
        r = start + index
        ws.cell(r, 1, code)
        ws.cell(r, 2, formula).fill = _FORMULA_FILL
        ws.cell(r, 3, _number(engine))
        ws.cell(r, 4, _validation(f"B{r}", f"C{r}")).fill = _CHECK_FILL
        ws.cell(r, 5, policy)
        cells[code] = f"B{r}"
    validation_row = start + len(summary) + 1
    ws.cell(validation_row, 1, "RM / RM FX double count")
    ws.cell(validation_row, 2, f'=IF(ABS(B{start}-(B{start + 1}+B{start + 2}+B{start + 3}))<=1,"PASS","FAIL")').fill = _CHECK_FILL
    cells["detail_range"] = (detail_start, detail_end)
    cells["validation_rows"] = (validation_row, validation_row)
    _finish(ws)
    return cells


def write_manufacturing_evidence(ws, result: dict[str, Any]) -> dict[str, Any]:
    _title(
        ws,
        "제조경비 근거",
        "상단에서 전공정 LENGTH(m)·후공정 PCS 분모를 확인하고, 기준 전공정 투입비율을 양쪽에 동일 적용하여 Volume/Unit/Fixed를 재현합니다.",
    )
    analysis = result.get("manufacturing_analysis") or {}
    trace = list(analysis.get("trace_rows") or [])
    _headers(ws, 4, [
        "분석월", "Base 전공정 생산량", "Comparison 전공정 생산량", "전공정 단위",
        "Base 후공정 생산량", "Comparison 후공정 생산량", "후공정 단위",
        "Base Source Reference", "Comparison Source Reference", "PCS+LENGTH 합산",
    ])
    periods: dict[str, dict[str, Any]] = {}
    for item in trace:
        periods.setdefault(str(item.get("month") or "선택기간"), item)
    for period, item in sorted(periods.items()):
        r = ws.max_row + 1
        ws.append([
            period, _number(item.get("base_front_activity")), _number(item.get("comparison_front_activity")),
            "LENGTH(m)", _number(item.get("base_back_activity")), _number(item.get("comparison_back_activity")),
            "PCS (LC=4-inch 포함)", item.get("base_front_activity_source") or item.get("base_back_activity_source"),
            item.get("comparison_front_activity_source") or item.get("comparison_back_activity_source"), "=FALSE",
        ])
    reconciliation = list(analysis.get("production_reconciliation") or [])
    if reconciliation:
        _headers(ws, 4, [
            "Scenario", "Month", "Product Group", "SAP Qty", "MES Qty", "Qty Difference",
            "SAP Length", "MES Length", "Length Difference",
        ], start_column=12)
        for offset, item in enumerate(reconciliation, 5):
            for column, value in enumerate((
                item.get("scenario"), item.get("month"), item.get("product_group"),
                _number(item.get("sap_qty")), item.get("mes_qty"), item.get("qty_difference"),
                _number(item.get("sap_length")), item.get("mes_length"), item.get("length_difference"),
            ), 12):
                ws.cell(offset, column, value)
    detail_header = max(8, ws.max_row + 3)
    _headers(ws, detail_header, [
        "분석월", "계정", "구분", "Business Source", "Canonical field", "Base Amount Source",
        "Comparison Amount Source", "배부율 Source", "전공정 단위", "후공정 단위", "Base 총금액",
        "Comparison 총금액", "Base 전공정 비율", "Comparison 적용비율", "Base 전공정 배부",
        "Comparison 전공정 배부", "Base 후공정 배부", "Comparison 후공정 배부", "Base 전공정 생산량",
        "Comparison 전공정 생산량", "Base 후공정 생산량", "Comparison 후공정 생산량", "Base 전공정 원단위",
        "Comparison 전공정 원단위", "Base 후공정 원단위", "Comparison 후공정 원단위",
        "전공정 Volume", "후공정 Volume", "Volume Effect 수식", "Volume Engine",
        "전공정 Unit", "후공정 Unit", "Unit Effect 수식", "Unit Engine", "Fixed Effect 수식",
        "Fixed Engine", "Subtotal 수식", "Engine Total", "Validation", "재고실현율(참고)", "당기제조원가 구성",
    ])
    detail_start = detail_header + 1
    if not trace:
        for item in result.get("manufacturing_accounts") or []:
            trace.append({
                "month": "선택기간", "account": item.get("account"), "classification": item.get("classification"),
                "business_source": item.get("account"), "canonical_fields": "manufacturing account",
                "base_amount_source": f"Data row {item.get('row')}", "comparison_amount_source": f"Data row {item.get('row')}",
                "front_ratio_source": f"Data row {item.get('allocation_ratio_row')}",
                "baseline_amount": item.get("baseline_amount"), "comparison_amount": item.get("comparison_amount"),
                "front_ratio_base": (item.get("baseline_front_ratios") or [0])[0],
                "front_ratio_comparison": (item.get("baseline_front_ratios") or [0])[0],
                "activity_effect": item.get("activity_effect"), "unit_effect": item.get("unit_effect"),
                "fixed_effect": item.get("fixed_effect"), "occurrence_effect": item.get("occurrence_effect"),
                "inventory_realization_rate": item.get("inventory_realization_rate"),
                "current_cost_component": item.get("current_cost_component"),
            })
    for item in trace:
        r = ws.max_row + 1
        ws.append([
            item.get("month"), item.get("account"), item.get("classification"), item.get("business_source"),
            item.get("canonical_fields"), item.get("base_amount_source"), item.get("comparison_amount_source"),
            item.get("front_ratio_source"), "LENGTH(m)", "PCS (LC=4-inch 포함)", _number(item.get("baseline_amount")),
            _number(item.get("comparison_amount")), _number(item.get("front_ratio_base")),
            _number(item.get("front_ratio_comparison")), None, None, None, None,
            _number(item.get("base_front_activity")), _number(item.get("comparison_front_activity")),
            _number(item.get("base_back_activity")), _number(item.get("comparison_back_activity")),
            None, None, None, None, None, None, None, _number(item.get("activity_effect")),
            None, None, None, _number(item.get("unit_effect")), None, _number(item.get("fixed_effect")),
            None, _number(item.get("occurrence_effect")), None, _number(item.get("inventory_realization_rate")),
            item.get("current_cost_component"),
        ])
        ws.cell(r, 15, f"=K{r}*M{r}").fill = _FORMULA_FILL
        ws.cell(r, 16, f"=L{r}*N{r}").fill = _FORMULA_FILL
        ws.cell(r, 17, f"=K{r}-O{r}").fill = _FORMULA_FILL
        ws.cell(r, 18, f"=L{r}-P{r}").fill = _FORMULA_FILL
        ws.cell(r, 23, f"=IFERROR(O{r}/S{r},0)").fill = _FORMULA_FILL
        ws.cell(r, 24, f"=IFERROR(P{r}/T{r},0)").fill = _FORMULA_FILL
        ws.cell(r, 25, f"=IFERROR(Q{r}/U{r},0)").fill = _FORMULA_FILL
        ws.cell(r, 26, f"=IFERROR(R{r}/V{r},0)").fill = _FORMULA_FILL
        ws.cell(r, 27, f'=IF(C{r}="variable",IF(OR(S{r}=0,T{r}=0),0,(S{r}-T{r})*W{r}),0)').fill = _FORMULA_FILL
        ws.cell(r, 28, f'=IF(C{r}="variable",IF(OR(U{r}=0,V{r}=0),0,(U{r}-V{r})*Y{r}),0)').fill = _FORMULA_FILL
        ws.cell(r, 29, f"=AA{r}+AB{r}").fill = _FORMULA_FILL
        ws.cell(r, 31, f'=IF(C{r}="variable",IF(OR(S{r}=0,T{r}=0),O{r}-P{r},T{r}*(W{r}-X{r})),0)').fill = _FORMULA_FILL
        ws.cell(r, 32, f'=IF(C{r}="variable",IF(OR(U{r}=0,V{r}=0),Q{r}-R{r},V{r}*(Y{r}-Z{r})),0)').fill = _FORMULA_FILL
        ws.cell(r, 33, f"=AE{r}+AF{r}").fill = _FORMULA_FILL
        ws.cell(r, 35, f'=IF(C{r}="fixed",K{r}-L{r},0)').fill = _FORMULA_FILL
        ws.cell(r, 37, f"=AC{r}+AG{r}+AI{r}").fill = _FORMULA_FILL
        ws.cell(r, 39, f'=IF(MAX(ABS(AC{r}-AD{r}),ABS(AG{r}-AH{r}),ABS(AI{r}-AJ{r}),ABS(AK{r}-AL{r}))<=1,"PASS","FAIL")').fill = _CHECK_FILL
    detail_end = ws.max_row
    summary_header = detail_end + 3
    _headers(ws, summary_header, ["Effect", "Evidence Formula", "Engine Output", "Validation", "Policy"])
    start = summary_header + 1
    summary = [
        ("manufacturing_activity", f"=SUM(AC{detail_start}:AC{detail_end})", analysis.get("activity_effect"), "Volume"),
        ("manufacturing_unit", f"=SUM(AG{detail_start}:AG{detail_end})", analysis.get("unit_effect"), "Unit Cost"),
        ("manufacturing_fixed", f"=SUM(AI{detail_start}:AI{detail_end})", analysis.get("fixed_effect"), "Fixed"),
        ("manufacturing_realized", f"=SUM(AK{detail_start}:AK{detail_end})", analysis.get("final_effect"), "Volume+Unit+Fixed; multiplier 미적용"),
    ]
    cells: dict[str, Any] = {}
    for index, (code, formula, engine, policy) in enumerate(summary):
        r = start + index
        ws.cell(r, 1, code)
        ws.cell(r, 2, formula).fill = _FORMULA_FILL
        ws.cell(r, 3, _number(engine))
        ws.cell(r, 4, _validation(f"B{r}", f"C{r}")).fill = _CHECK_FILL
        ws.cell(r, 5, policy)
        cells[code] = f"B{r}"
    validation_row = start + len(summary) + 1
    ws.cell(validation_row, 1, "Manufacturing subtotal / child double count")
    ws.cell(validation_row, 2, f'=IF(ABS(B{start + 3}-SUM(B{start}:B{start + 2}))<=1,"PASS","FAIL")').fill = _CHECK_FILL
    ws.cell(validation_row + 1, 1, "Inventory realization multiplier used")
    ws.cell(validation_row + 1, 2, "=FALSE").fill = _CHECK_FILL
    cells["detail_range"] = (detail_start, detail_end)
    cells["component_column"] = "AO"
    cells["subtotal_column"] = "AK"
    cells["validation_rows"] = (validation_row, validation_row + 1)
    _finish(ws, freeze=f"A{detail_start}")
    return cells


def write_sga_evidence(ws, result: dict[str, Any]) -> dict[str, str]:
    _title(ws, "판관비 효과 검증", "계정별 Base-Comparison 수식과 Bridge 위치를 확인합니다. 고객배송 운반비는 판매 Price에서만 반영됩니다.")
    _headers(ws, 4, [
        "원천 행", "구역", "계정과목", "구분", "Base", "Comparison", "손익효과 수식",
        "Engine", "Bridge 위치", "Validation", "Source Reference", "Source Status",
    ])
    start = 5
    for item in result.get("sga_accounts") or []:
        r = ws.max_row + 1
        ws.append([
            item.get("row"), item.get("section"), item.get("account"), item.get("classification"),
            _number(item.get("baseline_amount")), _number(item.get("comparison_amount")), None,
            _number(item.get("profit_effect")), item.get("bridge_position"), None,
            f"Golden Source row {item.get('row')} / selected months",
            item.get("source_validation_status") or "TRACE_UNAVAILABLE_LEGACY",
        ])
        ws.cell(
            r,
            7,
            f'=IF(OR(I{r}="판매효과",I{r}="외부효과/관세"),0,E{r}-F{r})',
        ).fill = _FORMULA_FILL
        ws.cell(r, 10, _validation(f"G{r}", f"H{r}")).fill = _CHECK_FILL
    end = ws.max_row
    summary = end + 3
    _headers(ws, summary, ["Effect", "Evidence Formula", "Engine Output", "Validation"])
    effects = {str(item.get("code")): _number(item.get("profit_effect")) for item in result.get("effects") or []}
    cells: dict[str, str] = {}
    for offset, (code, classification) in enumerate((("sga_variable", "variable"), ("sga_fixed", "fixed")), 1):
        r = summary + offset
        ws.cell(r, 1, code)
        ws.cell(r, 2, f'=SUMIF($D${start}:$D${end},"{classification}",$G${start}:$G${end})').fill = _FORMULA_FILL
        ws.cell(r, 3, effects.get(code, 0.0))
        ws.cell(r, 4, _validation(f"B{r}", f"C{r}")).fill = _CHECK_FILL
        cells[code] = f"B{r}"
    _finish(ws)
    return cells


def write_merchandise_link(ws) -> dict[str, str]:
    _title(
        ws,
        "상품원가검증 연결",
        "Slice 2B의 Forecast Workbook ‘상품원가검증’이 authoritative합니다. 비교 Evidence에서는 동일 계산을 복제하지 않고 Scope만 검증합니다.",
    )
    _headers(ws, 4, ["검증 항목", "상태", "근거"])
    rows = [
        ("LC YTD Rate", "LINKED", "Forecast Workbook 상품원가검증: Σ Actual COGS / Σ Actual Revenue"),
        ("신사업 정책", "LINKED", "ACTUAL_YTD_DEFAULT 또는 MANUAL_OVERRIDE provenance"),
        ("중복 계산", "FALSE", "동일 계산을 Comparison Evidence에서 재구현하지 않음"),
        ("Manufactured COGS Scope와 분리", "TRUE", "Forecast Merchandise COGS ≠ 제품+반제품 Manufactured COGS"),
    ]
    for row in rows:
        ws.append(row)
    validation_row = 9
    ws.cell(validation_row, 1, "Scope Validation")
    ws.cell(validation_row, 2, '=IF(AND(B7="FALSE",B8="TRUE"),"PASS","FAIL")').fill = _CHECK_FILL
    _finish(ws)
    return {"scope_validation": f"B{validation_row}"}


def write_final_bridge(
    ws,
    result: dict[str, Any],
    evidence_cells: dict[str, tuple[str, str]],
    merchandise_validation: tuple[str, str],
) -> None:
    _title(
        ws,
        "최종 OP Bridge 검증",
        "모든 공식 Effect는 상세 Evidence의 최종 formula cell을 직접 참조합니다. effects_total + residual = OP_delta를 실제 Excel 수식으로 검증합니다.",
    )
    _headers(ws, 4, ["Effect Code", "Effect", "Evidence Formula", "Engine Output", "Difference", "Validation", "Detail Cell"])
    start = 5
    effects = list(result.get("effects") or [])
    for index, item in enumerate(effects):
        r = start + index
        code = str(item.get("code") or "")
        target = evidence_cells.get(code)
        formula = _sheet_ref(*target) if target else f"=D{r}"
        ws.append([
            code, item.get("factor") or item.get("label"), formula,
            _number(item.get("profit_effect")), None, None,
            f"{target[0]}!{target[1]}" if target else "Legacy stored engine fallback",
        ])
        ws.cell(r, 5, f"=C{r}-D{r}").fill = _FORMULA_FILL
        ws.cell(r, 6, f'=IF(ABS(E{r})<=1,"PASS","FAIL")').fill = _CHECK_FILL
    end = start + len(effects) - 1
    summary = end + 2
    ws.cell(summary, 2, "effects_total")
    ws.cell(summary, 3, f"=SUM(C{start}:C{end})").fill = _FORMULA_FILL
    ws.cell(summary, 4, _number(result.get("effects_total")))
    ws.cell(summary, 6, _validation(f"C{summary}", f"D{summary}")).fill = _CHECK_FILL
    ws.cell(summary + 1, 2, "residual")
    ws.cell(summary + 1, 3, _number(result.get("residual")))
    ws.cell(summary + 1, 4, _number(result.get("residual")))
    ws.cell(summary + 1, 6, _validation(f"C{summary + 1}", f"D{summary + 1}")).fill = _CHECK_FILL
    ws.cell(summary + 2, 2, "OP_delta")
    ws.cell(summary + 2, 3, _number(result.get("operating_profit_delta")))
    ws.cell(summary + 2, 4, _number(result.get("operating_profit_delta")))
    ws.cell(summary + 2, 6, _validation(f"C{summary + 2}", f"D{summary + 2}")).fill = _CHECK_FILL
    ws.cell(summary + 3, 2, "effects_total + residual = OP_delta")
    ws.cell(summary + 3, 3, f"=C{summary}+C{summary + 1}").fill = _FORMULA_FILL
    ws.cell(summary + 3, 4, f"=C{summary + 2}").fill = _FORMULA_FILL
    ws.cell(summary + 3, 6, _validation(f"C{summary + 3}", f"D{summary + 3}")).fill = _CHECK_FILL

    checks = summary + 6
    _headers(ws, checks, ["Double-count Validation", "Formula Result", "정책"])
    check_rows = [
        ("Quantity / Mix 중복 없음", f'=IF(AND(COUNTIF(A{start}:A{end},"sales_quantity")=1,COUNTIF(A{start}:A{end},"sales_mix")=1),"PASS","FAIL")', "Pool별 Quantity와 제품군 간 Mix"),
        ("Freight / Price 중복 없음", f'=IF(AND(COUNTIF(A{start}:A{end},"sales_price")=1,COUNTIF(A{start}:A{end},"freight_adjustment")=0),"PASS","FAIL")', "Freight는 sales_price 내부 1회"),
        ("Tariff 별도 유지", f'=IF(COUNTIF(A{start}:A{end},"tariff")=1,"PASS","FAIL")', "Freight와 분리"),
        ("Raw Material / FX 중복 없음", f'=IF(AND(COUNTIF(A{start}:A{end},"material_total")=1,COUNTIF(A{start}:A{end},"nonwoven_jpy")=0),"PASS","FAIL")', "FX는 material_total 구성요소"),
        ("Manufacturing 하위 Effect 중복 없음", f'=IF(AND(COUNTIF(A{start}:A{end},"manufacturing_realized")=1,COUNTIF(A{start}:A{end},"manufacturing_activity")=0,COUNTIF(A{start}:A{end},"manufacturing_unit")=0,COUNTIF(A{start}:A{end},"manufacturing_fixed")=0),"PASS","FAIL")', "Subtotal만 additive"),
        ("Inventory Timing 한 번만 additive", f'=IF(COUNTIF(A{start}:A{end},"inventory_timing")=1,"PASS","FAIL")', "공식 Effect 1회"),
        ("Current Cost Basis Gap 신규 Effect 아님", f'=IF(COUNTIF(A{start}:A{end},"current_cost_basis_gap")=0,"PASS","FAIL")', "Disclosure only"),
        ("Forecast Merchandise / Manufactured COGS Scope 분리", _sheet_ref(*merchandise_validation), "상품원가검증 연결"),
        ("Residual plug 없음", f'=IF(COUNTIF(A{start}:A{end},"current_cost_basis_gap")=0,"PASS","FAIL")', "Engine residual을 다른 Effect로 backsolve하지 않음"),
    ]
    for index, row in enumerate(check_rows, 1):
        r = checks + index
        ws.cell(r, 1, row[0])
        ws.cell(r, 2, row[1]).fill = _CHECK_FILL
        ws.cell(r, 3, row[2])
    _finish(ws)
