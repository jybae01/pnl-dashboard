from __future__ import annotations

import streamlit as st

from .ai_analysis import (
    analysis_signature,
    build_executive_prompt,
    build_fact_pack,
    build_question_prompt,
    build_synthesis_prompt,
)
from .presentation.analysis_view import build_analysis_view


def _show_prompt(prompt_key: str, file_name: str) -> None:
    prompt = st.session_state.get(prompt_key)
    if not prompt:
        return
    st.markdown("#### ChatGPT에 전달할 프롬프트")
    st.code(prompt, language=None)
    st.caption("코드 박스의 복사 버튼을 누른 뒤 ChatGPT에 붙여넣으세요.")
    c1, c2 = st.columns([1, 1])
    c1.link_button("ChatGPT 열기", "https://chatgpt.com/", width="stretch")
    c2.download_button(
        "프롬프트 TXT 저장",
        data=prompt.encode("utf-8"),
        file_name=file_name,
        mime="text/plain",
        width="stretch",
    )


def render_ai_analysis(
    result: dict,
    *,
    show_title: bool = False,
    analysis_view: dict | None = None,
) -> None:
    """Render the API-free ChatGPT workflow for the current comparison result."""
    if show_title:
        st.title("AI 분석 — ChatGPT")
    st.caption(
        "OpenAI API를 호출하지 않습니다. FACT PACK과 프롬프트를 만든 뒤 사용자가 직접 ChatGPT에 붙여넣는 방식입니다."
    )

    signature = analysis_signature(result)
    baseline = result.get("baseline", {})
    comparison = result.get("comparison", {})
    period = result.get("period", {})
    c1, c2, c3 = st.columns(3)
    c1.metric("기준 모형", baseline.get("name") or baseline.get("id") or "-")
    c2.metric("비교 모형", comparison.get("name") or comparison.get("id") or "-")
    c3.metric("분석기간", period.get("label") or period.get("key") or "-")

    reconciled = bool(result.get("reconciled"))
    if reconciled:
        st.success("손익 Bridge 정합성 PASS — AI 분석 프롬프트를 생성할 수 있습니다.")
    else:
        st.warning("손익 Bridge 정합성 CHECK 상태이므로 프롬프트 생성을 차단했습니다.")

    notes = st.text_area(
        "분석 특이사항",
        key=f"ai_business_notes_{signature}",
        height=130,
        placeholder="숫자만으로 알 수 없는 경영적 사실을 한 줄씩 입력하세요.",
    )

    fx_key = f"{baseline.get('id', '')}_{comparison.get('id', '')}_{period.get('key', '')}"
    baseline_fx = float(st.session_state.get(f"baseline_sales_fx_{fx_key}", 1480.0))
    comparison_fx = float(st.session_state.get(f"comparison_sales_fx_{fx_key}", 1480.0))
    if analysis_view is None:
        analysis_view = build_analysis_view(
            result,
            baseline_sales_fx=baseline_fx,
            comparison_sales_fx=comparison_fx,
        )
    sales_rows = analysis_view.get("sales", {}).get("rows", [])
    sales_totals = analysis_view.get("sales", {}).get("totals", {})
    fact_pack = build_fact_pack(
        result,
        sales_rows=sales_rows,
        sales_totals=sales_totals,
        baseline_sales_fx=baseline_fx,
        comparison_sales_fx=comparison_fx,
        business_notes=notes,
        analysis_view=analysis_view,
    )

    with st.expander("AI에 전달되는 FACT PACK 확인", expanded=False):
        st.json(fact_pack)

    executive_tab, question_tab, synthesis_tab = st.tabs(["경영진 분석", "현재 분석결과 질문", "종합분석"])
    with executive_tab:
        executive_key = f"chatgpt_executive_prompt_{signature}"
        if st.button(
            "ChatGPT 경영진 분석 프롬프트 생성",
            type="primary",
            disabled=not reconciled,
            key=f"make_executive_{signature}",
        ):
            st.session_state[executive_key] = build_executive_prompt(fact_pack)
        _show_prompt(executive_key, f"chatgpt_executive_{signature}.txt")

    with question_tab:
        question = st.text_area(
            "질문",
            key=f"chatgpt_question_{signature}",
            height=100,
            placeholder="예) 계획 대비 영업이익 감소의 핵심 원인만 3개로 정리해줘.",
        )
        question_key = f"chatgpt_question_prompt_{signature}"
        if st.button(
            "ChatGPT 질문 프롬프트 생성",
            type="primary",
            disabled=(not reconciled or not question.strip()),
            key=f"make_question_{signature}",
        ):
            st.session_state[question_key] = build_question_prompt(fact_pack, question)
        _show_prompt(question_key, f"chatgpt_question_{signature}.txt")

    with synthesis_tab:
        synthesis_key = f"chatgpt_synthesis_prompt_{signature}"
        if st.button(
            "ChatGPT 종합분석 프롬프트 생성",
            type="primary",
            disabled=not reconciled,
            key=f"make_synthesis_{signature}",
        ):
            st.session_state[synthesis_key] = build_synthesis_prompt(fact_pack)
        _show_prompt(synthesis_key, f"chatgpt_synthesis_{signature}.txt")

    st.caption("버튼을 눌렀을 때만 프롬프트를 만들며, ChatGPT 답변은 이 화면 안에서 자동 생성되지 않습니다.")
