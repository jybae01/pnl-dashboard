from __future__ import annotations

from forecast.ai_analysis import build_fact_pack
from forecast.comparison import GenericComparisonEngine, PeriodOption
from forecast.storage import ModelMeta
from forecast.presentation.analysis_view import build_analysis_view
from forecast.presentation.formatting import format_million, million_value
from streamlit.testing.v1 import AppTest


def sample_result() -> dict:
    return {
        "baseline": {"id": "base", "name": "Plan"},
        "comparison": {"id": "comparison", "name": "Actual"},
        "period": {"key": "R2026_01_06", "label": "1~6월"},
        "pnl": [
            {"code": "operating_profit", "baseline": 200_000_000, "comparison": 115_000_000, "delta": -85_000_000},
        ],
        "sales_groups": [
            {
                "product_group": "SW", "baseline_quantity": 100, "comparison_quantity": 90,
                "baseline_amount": 1_000_000_000, "comparison_amount": 990_000_000,
                "baseline_gross_margin_rate": 0.2, "comparison_gross_margin_rate": 0.19,
            },
            {
                "product_group": "FS", "baseline_quantity": 200, "comparison_quantity": 220,
                "baseline_amount": 400_000_000, "comparison_amount": 462_000_000,
                "baseline_gross_margin_rate": 0.3, "comparison_gross_margin_rate": 0.31,
            },
        ],
        "production": [
            {"code": "FS_SW", "baseline": 1000, "comparison": 1100, "delta": 100},
            {"code": "FS_BW", "baseline": 500, "comparison": 450, "delta": -50},
            {"code": "SW400", "baseline": 100, "comparison": 90, "delta": -10},
            {"code": "SW440", "baseline": 10, "comparison": 20, "delta": 10},
            {"code": "BW400", "baseline": 50, "comparison": 60, "delta": 10},
            {"code": "LC", "baseline": 30, "comparison": 80, "delta": 50},
        ],
        "effects": [
            {"code": "revenue", "factor": "매출액", "profit_effect": 52_000_000},
            {"code": "product_raw_material", "factor": "제품 원재료비", "profit_effect": -20_000_000},
            {"code": "semi_raw_material", "factor": "반제품 원재료비", "profit_effect": -5_000_000},
            {"code": "tariff", "factor": "관세", "profit_effect": -3_000_000},
        ],
        "cost_summary": [],
        "manufacturing_accounts": [
            {
                "row": 290, "account": "수도광열비", "classification": "variable",
                "baseline_amount": 100_000_000, "comparison_amount": 110_000_000,
                "delta": 10_000_000, "activity_effect": None, "unit_effect": None,
                "fixed_effect": 0, "occurrence_effect": -10_000_000,
                "inventory_realization_rate": 1.12, "final_profit_effect": -11_200_000,
                "calculation_status": "배부율 매핑 필요",
            },
            {
                "row": 291, "account": "급여", "classification": "fixed",
                "baseline_amount": 50_000_000, "comparison_amount": 40_000_000,
                "delta": -10_000_000, "activity_effect": 0, "unit_effect": 0,
                "fixed_effect": 10_000_000, "occurrence_effect": 10_000_000,
                "inventory_realization_rate": 1.12, "final_profit_effect": 11_200_000,
                "calculation_status": "완료",
            },
        ],
        "sga_accounts": [
            {
                "row": 1168, "account": "운반비", "classification": "transport",
                "baseline_amount": 10_000_000, "comparison_amount": 20_000_000,
                "delta": 10_000_000, "profit_effect": 0, "bridge_position": "판매효과",
            },
            {
                "row": 1194, "account": "포장비", "classification": "variable",
                "baseline_amount": 30_000_000, "comparison_amount": 20_000_000,
                "delta": -10_000_000, "profit_effect": 10_000_000,
                "bridge_position": "변동 판관비",
            },
            {
                "row": 1200, "account": "급여", "classification": "fixed",
                "baseline_amount": 100_000_000, "comparison_amount": 90_000_000,
                "delta": -10_000_000, "profit_effect": 10_000_000,
                "bridge_position": "고정 판관비",
            },
            {
                "row": None, "account": "관세(직접입력)", "classification": "tariff",
                "baseline_amount": 0, "comparison_amount": 3_000_000,
                "delta": 3_000_000, "profit_effect": -3_000_000,
                "bridge_position": "관세효과",
            },
        ],
        "operating_profit_delta": -85_000_000,
        "effects_total": -85_000_000,
        "residual": 0,
        "reconciled": True,
    }


def test_formatter_converts_only_at_display_boundary():
    assert million_value(85_340_000) == 85.34
    assert format_million(85_340_000) == "85백만원"
    assert format_million(-73_200_000) == "-73백만원"
    assert format_million(420_000) == "0.4백만원"
    assert format_million(35_000_000, signed=True) == "+35백만원"
    assert format_million(None) == "미산출"


def test_sales_identity_uses_base_gp_and_weighted_total_rate():
    view = build_analysis_view(sample_result(), baseline_sales_fx=1_000, comparison_sales_fx=1_100)
    rows = view["sales"]["rows"]
    sw = next(row for row in rows if row["product_group"] == "SW")
    assert sw["quantity_effect"] == (90 - 100) * (1_000_000_000 / 100) * 0.2
    assert sw["internal_effect"] == sw["quantity_effect"] + sw["pure_price_effect"]
    assert sw["total_sales_effect"] == sw["internal_effect"] + sw["sales_fx_effect"]
    total = rows[-1]
    expected_rate = (1_000_000_000 * 0.2 + 400_000_000 * 0.3) / 1_400_000_000
    assert total["baseline_gross_margin_rate"] == expected_rate
    assert total["quantity_delta"] is None
    assert total["pure_price_delta_usd"] is None


def test_material_exposes_three_part_policy_without_mcm_or_yield_effects():
    material = build_analysis_view(sample_result())["material"]
    assert material["jpy_fx_unit"] == "KRW/JPY"
    assert all(row["nonwoven_price_ex_fx"] is None for row in material["rows"])
    assert all(row["nonwoven_jpy"] is None for row in material["rows"])
    assert all(row["materials_ex_nonwoven"] is None for row in material["rows"])
    assert "MCM" not in str(material)
    assert "수율" not in str(material)


def test_back_process_activity_is_sw_bw_lc_and_keeps_fs_separate():
    activities = build_analysis_view(sample_result())["manufacturing"]["activities"]
    back_total = next(row for row in activities if row["process"] == "후공정 합계")
    assert back_total["baseline"] == 110 + 50 + 30
    assert back_total["comparison"] == 110 + 60 + 80
    assert back_total["production_basis"] == "SW+BW+LC"
    front = next(row for row in activities if row["process"] == "전공정")
    assert front["baseline"] == 1500
    assert front["unit"] == "m"


def test_account_rows_are_not_collapsed_and_realization_is_uncapped():
    view = build_analysis_view(sample_result())
    manufacturing = view["manufacturing"]["accounts"]
    assert [row["account"] for row in manufacturing] == ["수도광열비", "급여"]
    assert all("기타 제조경비" not in row["account"] for row in manufacturing)
    assert manufacturing[0]["inventory_realization_rate"] == 1.12
    sga = view["sga"]["accounts"]
    assert all("기타 판관비" not in row["account"] for row in sga)


def test_transport_and_tariff_are_visible_but_not_double_counted_in_sga():
    view = build_analysis_view(sample_result())
    sga = view["sga"]
    transport = next(row for row in sga["accounts"] if row["classification"] == "transport")
    tariff = next(row for row in sga["accounts"] if row["classification"] == "tariff")
    assert transport["profit_effect"] == 0
    assert transport["bridge_position"] == "판매효과"
    assert tariff["bridge_position"] == "관세효과"
    assert sga["variable_effect"] == 10_000_000
    assert sga["fixed_effect"] == 10_000_000
    assert sga["tariff_effect"] == -3_000_000


def test_summary_keeps_residual_separate_and_reconciles():
    summary = build_analysis_view(sample_result())["summary"]
    assert sum(row["profit_effect"] for row in summary["bridge"][:-1]) == summary["effects_total"]
    assert summary["effects_total"] + summary["residual"] == summary["operating_profit_delta"]
    assert summary["bridge"][-2]["factor"] == "기타 주요 손익요인"
    assert all(row["factor"] != "잔여차이" for row in summary["bridge"])


def test_ai_fact_pack_uses_view_millions_and_has_no_independent_mcm():
    result = sample_result()
    view = build_analysis_view(result)
    pack = build_fact_pack(result, analysis_view=view, business_notes="정기보수")
    assert pack["metadata"]["currency_display_unit"] == "KRW million"
    assert pack["metadata"]["raw_krw_values_included"] is False
    assert pack["pnl"]["operating_profit_delta_million_krw"] == -85
    ranked_values = [abs(row["effect_million_krw"]) for row in pack["effect_ranking"]]
    assert ranked_values == sorted(ranked_values, reverse=True)
    assert "85000000" not in str(pack).replace("-", "")
    assert "mcm_transition" not in str(pack).lower()
    assert "yield_effect" not in str(pack).lower()


def test_generic_account_result_is_dynamic_and_tariff_is_once():
    engine = GenericComparisonEngine("config/model_mapping.json")
    manufacturing = engine._manufacturing_account_rows(
        [{"row": 1, "account": "수도광열비", "amount": 100}],
        [{"row": 1, "account": "수도광열비", "amount": 120}, {"row": 2, "account": "새계정", "amount": 30}],
        {"cogs": 200},
        {"raw_material": 100, "labor": 50, "outsourcing": 25, "other_processing": 25},
    )
    assert [row["account"] for row in manufacturing] == ["수도광열비", "새계정"]
    assert manufacturing[0]["classification"] == "variable"
    assert manufacturing[0]["inventory_realization_rate"] == 1.0
    sga = engine._sga_account_rows(
        [{"row": 1, "account": "운반비", "section": "판매비", "amount": 10}],
        [{"row": 1, "account": "운반비", "section": "판매비", "amount": 20}, {"row": 2, "account": "신규계정", "section": "일반관리비", "amount": 5}],
        {"tariff": 0}, {"tariff": 3},
    )
    assert [row["account"] for row in sga].count("관세(직접입력)") == 1
    assert next(row for row in sga if row["account"] == "운반비")["profit_effect"] == 0


def test_general_admin_transport_name_is_not_misclassified_as_customer_delivery():
    engine = GenericComparisonEngine("config/model_mapping.json")
    rows = engine._sga_account_rows(
        [{"row": 1200, "account": "운반비", "section": "일반관리비", "amount": 10}],
        [{"row": 1200, "account": "운반비", "section": "일반관리비", "amount": 15}],
        {"tariff": 0}, {"tariff": 0},
    )
    general_transport = next(row for row in rows if row["row"] == 1200)
    assert general_transport["classification"] == "fixed"
    assert general_transport["profit_effect"] == -5
    assert general_transport["bridge_position"] == "고정 판관비"


def test_streamlit_v1_tabs_and_account_tables_render_without_runtime_errors():
    script = (
        "from forecast.presentation.analysis_tabs import render_comparison_analysis\n"
        f"result = {sample_result()!r}\n"
        "render_comparison_analysis(result)\n"
    )
    app = AppTest.from_string(script, default_timeout=15).run()
    assert not app.exception
    assert [tab.label for tab in app.tabs[:6]] == [
        "종합", "판매효과", "원부재료", "제조경비", "판관비", "AI 분석",
    ]
    assert list(app.dataframe[1].value.columns) == [
        "제품군", "매출액 (증감)", "기준 매출총이익률", "수량효과 (수량증감)",
        "순수단가 효과 ($단가차이)", "내부효과", "외부효과 (매출환율)", "판매효과 합계",
    ]
    assert "LC" in set(app.dataframe[4].value["생산기준"])
    manufacturing_table = next(
        table.value for table in app.dataframe
        if "최종 손익효과" in table.value.columns
    )
    sga_table = next(
        table.value for table in app.dataframe
        if "손익 Bridge 반영" in table.value.columns
    )
    assert list(manufacturing_table["계정과목"]) == ["수도광열비", "급여"]
    assert "운반비" in set(sga_table["계정과목"])
    assert "관세(직접입력)" in set(sga_table["계정과목"])


def test_streamlit_check_state_disables_all_ai_prompt_buttons():
    result = sample_result()
    result["reconciled"] = False
    result["residual"] = 1_000_000
    script = (
        "from forecast.presentation.analysis_tabs import render_comparison_analysis\n"
        f"result = {result!r}\n"
        "render_comparison_analysis(result)\n"
    )
    app = AppTest.from_string(script, default_timeout=15).run()
    ai_buttons = [button for button in app.button if "프롬프트 생성" in button.label]
    assert len(ai_buttons) == 3
    assert all(button.disabled for button in ai_buttons)


def test_generic_comparison_direction_reverses_all_deltas(monkeypatch):
    engine = GenericComparisonEngine("config/model_mapping.json")

    def extracted(operating_profit: float, revenue_effect: float) -> dict:
        return {
            "pnl": {code: (operating_profit if code == "operating_profit" else 0.0)
                    for code in engine.mapping["pnl_rows"]},
            "products": {code: {"quantity": 0.0, "amount": 0.0, "price": 0.0}
                         for code in engine.mapping["products"]},
            "sales_groups": {code: {"quantity": 0.0, "amount": 0.0, "cogs": 0.0, "gross_margin_rate": 0.0}
                             for code in engine.mapping["sales_groups"]},
            "production": {code: 0.0 for code in engine.mapping["production_rows"]},
            "mcm": {code: 0.0 for code in engine.mapping["mcm_rows"]},
            "cost_summary": {code: 0.0 for code in engine.mapping["cost_labels"]},
            "effect_bases": {code: (revenue_effect if code == "revenue" else 0.0)
                             for code in engine.mapping["effect_labels"]},
            "manufacturing_accounts": [],
            "sga_accounts": [],
        }

    payloads = {"base": extracted(10.0, 10.0), "comparison": extracted(15.0, 15.0)}
    monkeypatch.setattr("forecast.comparison.GoldenWorkbook", lambda path: path)
    monkeypatch.setattr(engine, "_extract", lambda path, meta, months: payloads[path])
    base_meta = ModelMeta("base", "Base", "계획", 2026, 1, 12, "2026-01-01", "V1", True, "base.xlsx", "now")
    comp_meta = ModelMeta("comp", "Comp", "실적", 2026, 1, 12, "2026-01-01", "V1", True, "comp.xlsx", "now")
    period = PeriodOption("M01", "1월", (1,), "월")
    forward = engine.compare(base_meta, "base", comp_meta, "comparison", period)
    reverse = engine.compare(comp_meta, "comparison", base_meta, "base", period)
    assert forward.operating_profit_delta == -reverse.operating_profit_delta == 5.0
    assert forward.effects_total == -reverse.effects_total == 5.0
    assert forward.effects[0]["delta"] == -reverse.effects[0]["delta"]
    assert forward.effects[0]["profit_effect"] == -reverse.effects[0]["profit_effect"]
