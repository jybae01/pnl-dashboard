from __future__ import annotations

import streamlit as st

from forecast.ai_ui import render_ai_analysis


st.set_page_config(page_title="AI 분석 · ChatGPT", layout="wide")
result = st.session_state.get("comparison_result")
if not result:
    st.title("AI 분석 — ChatGPT")
    st.info("먼저 손익 분석에서 기준/비교 모형과 분석기간을 선택한 뒤 비교 분석을 실행해 주세요.")
    st.page_link("app.py", label="손익 분석 화면으로 이동")
    st.stop()

render_ai_analysis(result, show_title=True)
