from pathlib import Path


APP = (Path(__file__).resolve().parents[1] / "app.py").read_text(encoding="utf-8")


def test_comparison_has_agreed_six_tabs_and_embedded_ai_renderer():
    assert '["종합", "판매효과", "원부재료", "제조경비", "판관비", "AI 분석"]' in APP
    assert "render_ai_analysis(result)" in APP


def test_mcm_is_not_rendered_as_a_detail_effect():
    assert "MCM(유상사급) 상세 원인" not in APP
    assert 'st.dataframe(center_table_text(pd.DataFrame(result["mcm"]))' not in APP
