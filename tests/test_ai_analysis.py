from forecast.ai_analysis import (
    build_executive_prompt,
    build_fact_pack,
    build_question_prompt,
    build_synthesis_prompt,
)


def _sample_result(reconciled=True):
    return {
        "baseline": {"id": "plan", "name": "2026 Plan"},
        "comparison": {"id": "actual", "name": "2026 Actual"},
        "period": {"key": "R2026_07_07", "label": "7월"},
        "operating_profit_delta": -85_000_000,
        "effects_total": -85_000_000,
        "residual": 0 if reconciled else 10_000_000,
        "reconciled": reconciled,
        "effects": [{
            "code": "revenue", "factor": "매출액", "baseline": 1_000_000_000,
            "comparison": 950_000_000, "delta": -50_000_000, "profit_effect": -50_000_000,
        }],
        "cost_summary": [{
            "code": "raw_material", "item": "원부재료", "baseline": 300_000_000,
            "comparison": 330_000_000, "delta": 30_000_000,
        }],
        "production": [{"code": "LC", "item": "LC", "baseline": 500, "comparison": 700, "delta": 200}],
        "mcm": [{"code": "SW400", "delta": 99}],
        "mcm_transition": {"mcm_quantity_delta": 99},
    }


def test_fact_pack_excludes_mcm_and_carries_core_context():
    pack = build_fact_pack(_sample_result(), business_notes="정기보수로 1주 비가동")
    text = str(pack)
    assert "mcm_transition" not in text
    assert "mcm_quantity_delta" not in text
    assert pack["business_notes"] == ["정기보수로 1주 비가동"]
    assert pack["manufacturing"]["activity_policy"]["back_process"].startswith("SW + BW + LC")
    assert pack["reconciliation"]["status"] == "PASS"


def test_prompts_forbid_recalculation_and_unsupported_causes():
    pack = build_fact_pack(_sample_result())
    prompts = [
        build_executive_prompt(pack),
        build_question_prompt(pack, "왜 영업이익이 감소했어?"),
        build_synthesis_prompt(pack),
    ]
    for prompt in prompts:
        assert "숫자를 변경하거나 새로 계산하지 않는다" in prompt
        assert "MCM은 현재 V1에서 별도 효과로 식별되지 않았으므로" in prompt
        assert "FACT PACK" in prompt


def test_check_reconciliation_is_carried_into_fact_pack():
    pack = build_fact_pack(_sample_result(reconciled=False))
    assert pack["reconciliation"]["status"] == "CHECK"
    assert pack["reconciliation"]["residual_million_krw"] == 10.0
