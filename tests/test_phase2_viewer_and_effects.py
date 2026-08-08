from forecast.ai_analysis import build_fact_pack
from forecast.presentation.analysis_view import build_analysis_view
from forecast.presentation.viewer_dashboard import InvalidCompletedResult, persisted_analysis_view


def _result():
    return {
        "baseline": {"id": "base", "name": "Plan"},
        "comparison": {"id": "comparison", "name": "Actual"},
        "period": {"key": "M01", "label": "1월"},
        "pnl": [
            {"code": "operating_profit", "baseline": 100, "comparison": 140},
        ],
        "production": [],
        "effects": [
            {"code": "sales_quantity", "profit_effect": 10},
            {"code": "sales_mix", "profit_effect": 5},
            {"code": "sales_price", "profit_effect": 7},
            {"code": "sales_fx", "profit_effect": 3},
            {"code": "material_total", "profit_effect": 9},
        ],
        "operating_profit_delta": 40,
        "effects_total": 34,
        "residual": 6,
        "reconciled": False,
        "fx_total": 5,
        "raw_material_excl_fx": 7,
        "sales_analysis": {
            "baseline_fx_krw_per_usd": 1400,
            "comparison_fx_krw_per_usd": 1450,
            "rows": [],
            "totals": {
                "quantity_effect": 10,
                "mix_effect": 5,
                "pure_price_effect": 7,
                "sales_fx_effect": 3,
                "total_sales_effect": 25,
            },
        },
        "material_analysis": {
            "product_groups": [],
            "total": 9,
            "nonwoven_price_ex_fx": 2,
            "nonwoven_jpy": 2,
            "materials_ex_nonwoven": 5,
            "calculation_status": "완료",
        },
        "manufacturing_accounts": [],
        "sga_accounts": [],
    }


def test_backend_derived_fx_material_and_mix_flow_to_persisted_view():
    result = _result()
    view = build_analysis_view(result)
    factors = {row["factor"]: row["profit_effect"] for row in view["summary"]["bridge"]}
    pack = build_fact_pack(result, analysis_view=view)

    assert factors["제품 Mix"] == 5
    assert factors["환율효과 합계"] == 5
    assert factors["환율 제외 원부재료"] == 7
    assert pack["sales"]["mix_effect_million_krw"] == 0.0
    assert pack["materials"]["fx_total_million_krw"] == 0.0


def test_viewer_accepts_only_worker_materialized_analysis_view():
    view = build_analysis_view(_result())
    assert persisted_analysis_view({
        "payload_type": "comparison_analysis",
        "analysis_view": view,
    }) is view

    try:
        persisted_analysis_view({"payload_type": "comparison_analysis", "comparison_result": _result()})
    except InvalidCompletedResult:
        pass
    else:
        raise AssertionError("viewer must not rebuild a missing analysis_view")
