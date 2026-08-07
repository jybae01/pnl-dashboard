from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "app.py").read_text(encoding="utf-8")
TABS = (ROOT / "forecast" / "presentation" / "analysis_tabs.py").read_text(encoding="utf-8")


def test_comparison_has_agreed_six_tabs_and_embedded_ai_renderer():
    assert '["종합", "판매효과", "원부재료", "제조경비", "판관비", "AI 분석"]' in TABS
    assert "render_ai_analysis(result, analysis_view=view)" in TABS
    assert "render_comparison_analysis(result)" in APP


def test_ai_analysis_is_not_exposed_as_a_duplicate_streamlit_page():
    assert not (ROOT / "pages" / "5_AI_Analysis.py").exists()


def test_mcm_is_not_rendered_as_a_detail_effect():
    assert "MCM(유상사급) 상세 원인" not in APP
    assert 'st.dataframe(center_table_text(pd.DataFrame(result["mcm"]))' not in APP
    assert "MCM 효과" not in TABS


def test_old_summary_only_tabs_are_removed_and_export_is_directly_preserved():
    assert "manufacturing_codes" not in APP
    assert "sga_codes" not in APP
    assert "render_analysis_export(result)" in APP
