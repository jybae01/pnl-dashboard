from __future__ import annotations

import json

import streamlit as st

from forecast.ai_analysis import (
    analysis_signature,
    build_executive_prompt,
    build_fact_pack,
    build_question_prompt,
    build_synthesis_prompt,
)
from forecast.sales_comparison import calculate_sales_effect_rows, sales_effect_totals


st.set_page_config(page_title="AI 분석 · ChatGPT", layout="wide")
st.title("AI 분석 — ChatGPT")
st.caption(
    "API를 사용하지 않는 ChatGPT 연결 방식입니다. 이 화면에서는 분석용 FACT PACK과 프롬프트만 만들며, "
    "사용자가 복사해 ChatGPT에 붙여넣기 전까지 외부로 데이터를 전송하지 않습니다."
)

result = st.session_state.get("comparison_result")
if not result:
    st.info("먼저 손익 분석에서 기준/비교 모형과 분석기간을 선택한 뒤 비교 분석을 실행해 주세요.")
    st.page_link("app.py", label="손익 분석 화면으로 이동")
    st.stop()

signature = analysis_signature(result)
baseline = result.get("baseline", {})
comparison = result.get("comparison", {})
period = result.get("period", {})

c1, c2, c3 = st.columns(3)
c1.metric("기준 모형", baseline.get("name") or baseline.get("id") or "-")
c2.metric("비교 모형", comparison.get("name") or comparison.get("id") or "-")
c3.metric("분석기간", period.get("label") or period.get("key") or "-")

if result.get("reconciled"):
    st.success("손익 Bridge 정합성 PASS — AI 분석용 프롬프트를 생성할 수 있습니다.")
else:
    st.warning(
        "손익 Bridge 정합성 CHECK 상태입니다. 잘못된 숫자를 AI가 설명하지 않도록 프롬프트 생성 기능을 잠갔습니다. "
        "먼저 상세 탭에서 잔여차이를 확인해 주세요."
    )

business_notes = st.text_area(
    "분석 특이사항",
    key=f"ai_business_notes_{signature}",
    height=130,
    placeholder=(
        "숫자만으로 알 수 없는 경영적 사실을 한 줄씩 입력하세요.\n"
        "예) 8월 1주 정기보수로 생산라인 비가동\n"
        "예) SW 주요 고객 출하 일부가 차월로 이연"
    ),
)
st.caption("AI는 위 특이사항과 확정 계산값 외의 원인을 사실처럼 만들지 않도록 프롬프트에 제한을 둡니다.")

fx_key = f"{baseline.get('id', '')}_{comparison.get('id', '')}_{period.get('key', '')}"
baseline_fx = float(st.session_state.get(f"baseline_sales_fx_{fx_key}", 1480.0))
comparison_fx = float(st.session_state.get(f"comparison_sales_fx_{fx_key}", 1480.0))

sales_rows = []
sales_totals = {}
if result.get("sales_groups"):
    sales_rows = calculate_sales_effect_rows(result["sales_groups"], baseline_fx, comparison_fx)
    sales_totals = sales_effect_totals(sales_rows)

fact_pack = build_fact_pack(
    result,
    sales_rows=sales_rows,
    sales_totals=sales_totals,
    baseline_sales_fx=baseline_fx,
    comparison_sales_fx=comparison_fx,
    business_notes=business_notes,
)

with st.expander("AI에 전달되는 FACT PACK 확인", expanded=False):
    st.json(fact_pack)


def show_prompt(prompt_key: str, file_name: str) -> None:
    prompt = st.session_state.get(prompt_key)
    if not prompt:
        return
    st.markdown("#### ChatGPT에 전달할 프롬프트")
    st.code(prompt, language=None)
    st.caption("위 코드 박스의 복사 버튼을 누른 뒤 ChatGPT에 붙여넣으세요.")
    c1, c2 = st.columns([1, 1])
    c1.link_button("ChatGPT 열기", "https://chatgpt.com/", use_container_width=True)
    c2.download_button(
        "프롬프트 TXT 저장",
        data=prompt.encode("utf-8"),
        file_name=file_name,
        mime="text/plain",
        use_container_width=True,
    )


analysis_tab, question_tab, synthesis_tab = st.tabs(["경영진 분석", "현재 분석 질문", "종합분석"])

with analysis_tab:
    st.markdown("#### 1~4단계: 경영진용 손익분석")
    st.write(
        "확정 계산값, 판매/원부재료/제조경비/판관비 정보와 특이사항을 묶어 ChatGPT용 경영진 분석 프롬프트를 만듭니다."
    )
    executive_key = f"chatgpt_executive_prompt_{signature}"
    if st.button(
        "ChatGPT 경영진 분석 프롬프트 생성",
        type="primary",
        disabled=not result.get("reconciled"),
        key=f"make_executive_{signature}",
    ):
        st.session_state[executive_key] = build_executive_prompt(fact_pack)
    show_prompt(executive_key, f"chatgpt_executive_{signature}.txt")

with question_tab:
    st.markdown("#### 5단계: 현재 분석결과에 대해 질문")
    question = st.text_area(
        "질문",
        key=f"chatgpt_question_{signature}",
        height=100,
        placeholder=(
            "예) 계획 대비 영업이익 감소의 핵심 원인만 3개로 정리해줘.\n"
            "예) SW 관련 영향만 분리해서 설명해줘.\n"
            "예) 제조경비에서 실무자가 우선 확인할 항목을 알려줘."
        ),
    )
    question_key = f"chatgpt_question_prompt_{signature}"
    if st.button(
        "ChatGPT 질문 프롬프트 생성",
        type="primary",
        disabled=(not result.get("reconciled") or not question.strip()),
        key=f"make_question_{signature}",
    ):
        st.session_state[question_key] = build_question_prompt(fact_pack, question)
    show_prompt(question_key, f"chatgpt_question_{signature}.txt")

with synthesis_tab:
    st.markdown("#### 최종 종합분석")
    st.write(
        "상세 탭을 다시 나열하지 않고 영업이익 증감 구조, 주요 상쇄관계, 실무 확인사항을 하나의 보고문으로 정리하는 프롬프트입니다. "
        "버튼을 눌렀을 때만 생성됩니다."
    )
    synthesis_key = f"chatgpt_synthesis_prompt_{signature}"
    if st.button(
        "ChatGPT 종합분석 프롬프트 생성",
        type="primary",
        disabled=not result.get("reconciled"),
        key=f"make_synthesis_{signature}",
    ):
        st.session_state[synthesis_key] = build_synthesis_prompt(fact_pack)
    show_prompt(synthesis_key, f"chatgpt_synthesis_{signature}.txt")

st.divider()
st.caption(
    "현재 버전은 OpenAI API를 호출하지 않습니다. 따라서 ChatGPT 답변이 이 Streamlit 화면 안에서 자동 생성되지는 않으며, "
    "ChatGPT에서 답변을 생성하는 방식입니다."
)
