from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from ..ai_ui import render_ai_analysis
from .analysis_view import build_analysis_view
from .formatting import format_million, format_number, format_signed_number


def _frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def _render_common_header(view: dict[str, Any]) -> None:
    metadata, summary = view["metadata"], view["summary"]
    baseline = metadata["baseline"]
    comparison = metadata["comparison"]
    period = metadata["period"]
    st.caption("단위: 금액 백만원 / 수량 PCS 또는 m / 환율 KRW/USD·KRW/JPY")
    c1, c2, c3 = st.columns(3)
    c1.markdown(f"**기준 모형**  \n{baseline.get('name') or baseline.get('id') or '-'}")
    c2.markdown(f"**비교 모형**  \n{comparison.get('name') or comparison.get('id') or '-'}")
    c3.markdown(f"**분석기간**  \n{period.get('label') or period.get('key') or '-'}")
    cards = st.columns(4)
    cards[0].metric("영업이익 증감", format_million(summary["operating_profit_delta"], signed=True))
    cards[1].metric("효과 합계", format_million(summary["effects_total"], signed=True))
    cards[2].metric("잔여차이", format_million(summary["residual"], signed=True))
    cards[3].metric("정합성", summary["status"])
    if summary["reconciled"]:
        st.success("정합성 PASS — effects_total + residual = operating_profit_delta")
    else:
        st.warning("정합성 CHECK — 잔여차이를 기타 손익요인에 숨기지 않았습니다.")


def _render_summary(view: dict[str, Any]) -> None:
    summary = view["summary"]
    st.markdown("#### 경영진 손익 요약")
    cards = st.columns(4)
    cards[0].metric("기준 영업이익", format_million(summary["baseline_operating_profit"]))
    cards[1].metric("비교 영업이익", format_million(summary["comparison_operating_profit"]))
    cards[2].metric("영업이익 증감", format_million(summary["operating_profit_delta"], signed=True))
    cards[3].metric("정합성", summary["status"])
    st.markdown("#### 주요 손익 Bridge")
    st.caption("단위: 백만원 · + 영업이익 개선 / - 영업이익 악화")
    rows = [{
        "손익 변동요인": row["factor"],
        "손익효과": format_million(row["profit_effect"], suffix=False, signed=True),
    } for row in summary["bridge"]]
    st.dataframe(_frame(rows), width="stretch", hide_index=True)
    st.caption(
        "‘기타 주요 손익요인’은 엔진에서 식별됐으나 위 V1 대분류에 속하지 않은 효과입니다. "
        "잔여차이(Residual)는 별도 정합성 항목이며 여기에 포함하지 않습니다."
    )
    st.markdown("#### 주요 손익 변동")
    st.write(summary["narrative"])


def _render_sales(view: dict[str, Any]) -> None:
    sales = view["sales"]
    st.markdown("#### 판매 수량·단가·환율 효과")
    fx_cols = st.columns([1, 1, 3])
    fx_cols[0].metric("기준 매출환율(KRW/USD)", f"{sales['baseline_fx_krw_per_usd']:,.2f}")
    fx_cols[1].metric("비교 매출환율(KRW/USD)", f"{sales['comparison_fx_krw_per_usd']:,.2f}")
    fx_cols[2].caption(
        "원화 단가 변동을 순수 단가효과와 매출환율효과로 분해합니다. "
        "수량효과는 기준 제품군 GP/unit을 적용합니다."
    )
    totals = sales.get("totals", {})
    effect_cards = st.columns(4)
    effect_cards[0].metric(
        "판매수량 효과", format_million(totals.get("quantity_effect"), signed=True)
    )
    effect_cards[1].metric(
        "제품 Mix 효과", format_million(totals.get("mix_effect"), signed=True)
    )
    effect_cards[2].metric(
        "고객배송 운반비 포함 판매단가 효과",
        format_million(
            totals.get("sales_price_effect", totals.get("pure_price_effect")),
            signed=True,
        ),
    )
    effect_cards[3].metric(
        "매출환율 효과", format_million(totals.get("sales_fx_effect"), signed=True)
    )
    st.caption(
        "고객배송 운반비 효과: "
        + format_million(totals.get("transport_effect"), signed=True)
        + " (판매단가 효과에 1회 포함)"
    )
    st.caption("단위: 금액 백만원 / 수량 SW·BW·LC PCS, FS m / 단가차이 USD/판매단위")
    rows = []
    for row in sales["rows"]:
        is_total = row["product_group"] == "Total"
        revenue = format_million(row["comparison_amount"], suffix=False)
        revenue_delta = format_million(row["revenue_delta"], suffix=False, signed=True)
        quantity_effect = format_million(row["quantity_effect"], suffix=False, signed=True)
        pure_price = format_million(row["pure_price_effect"], suffix=False, signed=True)
        rows.append({
            "제품군": row["product_group"],
            "매출액 (증감)": f"{revenue} ({revenue_delta})",
            "기준 매출총이익률": f"{row['baseline_gross_margin_rate']:.1%}",
            "수량효과 (수량증감)": (
                f"{quantity_effect} ({format_signed_number(row['quantity_delta'])} {row['quantity_unit']})"
                if not is_total else quantity_effect
            ),
            "순수단가 효과 ($단가차이)": (
                f"{pure_price} ({format_signed_number(row['pure_price_delta_usd'], decimals=2)} USD)"
                if not is_total else pure_price
            ),
            "내부효과": format_million(row["internal_effect"], suffix=False, signed=True),
            "외부효과 (매출환율)": format_million(row["sales_fx_effect"], suffix=False, signed=True),
            "판매효과 합계": format_million(row["total_sales_effect"], suffix=False, signed=True),
        })
    st.dataframe(_frame(rows), width="stretch", hide_index=True)
    st.caption("Total의 수량·USD 단가차이는 단위가 달라 합산하지 않으며, 금액효과만 합산합니다.")

    with st.expander("계산 상세 보기", expanded=False):
        details = []
        for row in sales["rows"]:
            details.append({
                "제품군": row["product_group"],
                "기준 수량": format_number(row["baseline_quantity"]),
                "비교 수량": format_number(row["comparison_quantity"]),
                "기준 매출액": format_million(row["baseline_amount"], suffix=False),
                "비교 매출액": format_million(row["comparison_amount"], suffix=False),
            })
        st.dataframe(_frame(details), width="stretch", hide_index=True)


def _render_material(view: dict[str, Any]) -> None:
    material = view["material"]
    st.markdown("#### 제품군별 원부재료 효과")
    st.caption("단위: 금액 백만원 / 원부재료 원단위 원/판매단위 / JPY 환율 KRW/JPY")
    rows = []
    for row in material["rows"]:
        unit_cost = (
            f"{format_number(row['comparison_unit_cost'])} "
            f"({format_signed_number(row['unit_cost_delta'])})"
            if row["comparison_unit_cost"] is not None else "미산출"
        )
        rows.append({
            "제품군": row["product_group"],
            "원부재료 원단위 (증감)": unit_cost,
            "부직포 단가효과(환율 제외)": format_million(row["nonwoven_price_ex_fx"], suffix=False, signed=True),
            "부직포 엔화효과": format_million(row["nonwoven_jpy"], suffix=False, signed=True),
            "부직포 제외 원재료 효과": format_million(row["materials_ex_nonwoven"], suffix=False, signed=True),
            "원부재료 효과 합계": format_million(row["total"], suffix=False, signed=True),
            "계산상태": row["calculation_status"],
        })
    st.dataframe(_frame(rows), width="stretch", hide_index=True)
    if material["total"] is None or material["calculation_status"] != "완료":
        st.warning(material["calculation_status"])
    st.caption(
        "원천은 JPY 9행, 전공정 부직포 생산출고 205~207행, 부직포 제외 전공정 원재료 "
        "208~210행, 후공정 원재료 생산출고 684~699행입니다. MCM·수율·사용량은 V1 독립 "
        "손익효과가 아니며 JPY는 KRW/JPY를 그대로 사용해 100JPY 환산이나 ÷100을 적용하지 않습니다."
    )


def _render_manufacturing(view: dict[str, Any]) -> None:
    manufacturing = view["manufacturing"]
    st.markdown("#### A. 조업도")
    activity_rows = [{
        "공정": row["process"],
        "생산기준": row["production_basis"],
        "단위": row["unit"],
        "기준 생산량": format_number(row["baseline"]),
        "비교 생산량": format_number(row["comparison"]),
        "증감": format_signed_number(row["delta"]),
        "증감률": "-" if row["change_rate"] is None else f"{row['change_rate']:+.1%}",
        "계산 Driver": "적용" if row["calculation_driver"] else "구성 확인",
    } for row in manufacturing["activities"]]
    st.dataframe(_frame(activity_rows), width="stretch", hide_index=True)
    st.caption("전공정 Driver는 FS 길이(m), 후공정 Driver는 SW+BW+LC 생산입고 PCS 합계입니다. MCM은 외주가공비 조업도에서 제외합니다.")

    st.markdown("#### B. 제조경비 계정별 상세")
    st.caption("단위: 금액 백만원 / 재고실현율 %")
    account_rows = [{
        "계정과목": row.get("account"),
        "구분": "변동" if row.get("classification") == "variable" else "고정",
        "기준 금액": format_million(row.get("baseline_amount"), suffix=False),
        "비교 금액": format_million(row.get("comparison_amount"), suffix=False),
        "증감": format_million(row.get("delta"), suffix=False, signed=True),
        "조업도 효과": format_million(row.get("activity_effect"), suffix=False, signed=True),
        "원단위 효과": format_million(row.get("unit_effect"), suffix=False, signed=True),
        "고정비 효과": format_million(row.get("fixed_effect"), suffix=False, signed=True),
        "실현 전 효과": format_million(row.get("occurrence_effect"), suffix=False, signed=True),
        "재고실현율": (
            "미산출" if row.get("inventory_realization_rate") is None
            else f"{float(row['inventory_realization_rate']):.1%}"
        ),
        "최종 손익효과": format_million(row.get("final_profit_effect"), suffix=False, signed=True),
        "계산상태": row.get("calculation_status", ""),
    } for row in manufacturing["accounts"]]
    st.dataframe(_frame(account_rows), width="stretch", hide_index=True)
    with st.expander("계정 원천 추적", expanded=False):
        st.dataframe(_frame([{
            "계정과목": row.get("account"),
            "Golden Model Data 행": row.get("row"),
            "전공정 배부율 원천 행": row.get("allocation_ratio_row"),
            "기준 전공정 배부율": ", ".join(
                f"{float(value):.1%}" for value in row.get("baseline_front_ratios", [])
            ),
            "계산상태": row.get("calculation_status"),
        } for row in manufacturing["accounts"]]), width="stretch", hide_index=True)
    if manufacturing["has_uncomputed_accounts"]:
        st.warning("일부 제조경비는 Golden Model 전후공정 배부율 또는 재고실현율 분모 매핑이 없어 미산출입니다.")
    st.caption(
        "Golden Model 289~319행 계정을 개별 표시하고, 기준 모형 345~347행 전공정 가공비 "
        "투입비율을 기준·비교 양쪽에 동일 적용합니다. 상세 탭에서 ‘기타 제조경비’로 합치지 "
        "않으며 재고실현율은 비교 모형 기준으로 100% 상한을 두지 않습니다."
    )


def _render_sga(view: dict[str, Any]) -> None:
    st.markdown("#### 판관비 계정별 상세")
    st.caption("단위: 백만원 · 증감은 비교-기준, 손익효과는 + 개선 / - 악화")
    labels = {
        "variable": "변동 판관비",
        "fixed": "고정 판관비",
        "transport": "판매효과 연계",
        "tariff": "외부효과",
    }
    rows = [{
        "계정과목": row.get("account"),
        "구분": labels.get(str(row.get("classification")), str(row.get("classification", ""))),
        "기준 금액": format_million(row.get("baseline_amount"), suffix=False),
        "비교 금액": format_million(row.get("comparison_amount"), suffix=False),
        "증감": format_million(row.get("delta"), suffix=False, signed=True),
        "손익효과": format_million(row.get("profit_effect"), suffix=False, signed=True),
        "손익 Bridge 반영": row.get("bridge_position"),
    } for row in view["sga"]["accounts"]]
    st.dataframe(_frame(rows), width="stretch", hide_index=True)
    with st.expander("계정 원천 추적", expanded=False):
        st.dataframe(_frame([{
            "구역": row.get("section"),
            "계정과목": row.get("account"),
            "Golden Model Data 행": row.get("row"),
            "Bridge": row.get("bridge_position"),
        } for row in view["sga"]["accounts"]]), width="stretch", hide_index=True)
    st.caption(
        "고객배송 운반비는 실제 금액을 표시하되 판매효과로만 연결하여 판관비에서 중복 계산하지 않습니다. "
        "관세는 외부효과/관세효과로 한 번만 반영합니다. 상세 계정을 ‘기타 판관비’로 합치지 않습니다."
    )


def render_comparison_analysis(result: dict[str, Any]) -> dict[str, Any]:
    """Render all six V1 tabs from one deterministic presentation result."""
    view = build_analysis_view(result)
    _render_common_header(view)
    tabs = st.tabs(["종합", "판매효과", "원부재료", "제조경비", "판관비", "AI 분석"])
    with tabs[0]:
        _render_summary(view)
    with tabs[1]:
        _render_sales(view)
    with tabs[2]:
        _render_material(view)
    with tabs[3]:
        _render_manufacturing(view)
    with tabs[4]:
        _render_sga(view)
    with tabs[5]:
        render_ai_analysis(result, analysis_view=view)
    return view


def render_persisted_analysis_view(view: dict[str, Any]) -> None:
    """Render a worker-produced view without rebuilding any calculation."""

    _render_common_header(view)
    tabs = st.tabs(["종합", "판매효과", "원부재료", "제조경비", "판관비"])
    with tabs[0]:
        _render_summary(view)
    with tabs[1]:
        _render_sales(view)
    with tabs[2]:
        _render_material(view)
    with tabs[3]:
        _render_manufacturing(view)
    with tabs[4]:
        _render_sga(view)
