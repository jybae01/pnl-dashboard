from __future__ import annotations

import unittest

from forecast.ai_analysis import (
    build_executive_prompt,
    build_fact_pack,
    build_question_prompt,
    build_synthesis_prompt,
)


class AiAnalysisTest(unittest.TestCase):
    def sample_result(self):
        return {
            "baseline": {"id": "plan", "name": "2026 Plan"},
            "comparison": {"id": "actual", "name": "2026 Actual"},
            "period": {"key": "R2026_07_07", "label": "7월"},
            "operating_profit_delta": -85_000_000,
            "effects_total": -85_000_000,
            "residual": 0,
            "reconciled": True,
            "effects": [
                {"code": "revenue", "factor": "매출액", "baseline": 1000_000_000,
                 "comparison": 950_000_000, "delta": -50_000_000, "profit_effect": -50_000_000},
                {"code": "selling_expense", "factor": "판매비", "baseline": 100_000_000,
                 "comparison": 80_000_000, "delta": -20_000_000, "profit_effect": 20_000_000},
            ],
            "cost_summary": [
                {"code": "raw_material", "item": "원부재료", "baseline": 300_000_000,
                 "comparison": 330_000_000, "delta": 30_000_000, "profit_effect": -30_000_000},
                {"code": "manufacturing_expense", "item": "제조경비", "baseline": 200_000_000,
                 "comparison": 210_000_000, "delta": 10_000_000, "profit_effect": -10_000_000},
                {"code": "selling_expense", "item": "판매비", "baseline": 100_000_000,
                 "comparison": 80_000_000, "delta": -20_000_000, "profit_effect": 20_000_000},
            ],
            "production": [
                {"code": "LC", "label": "LC", "baseline": 500, "comparison": 700, "delta": 200},
            ],
            "mcm": [{"code": "SW400", "delta": 99}],
            "mcm_transition": {"mcm_quantity_delta": 99},
        }

    def test_fact_pack_excludes_separate_mcm_attribution(self):
        pack = build_fact_pack(self.sample_result(), business_notes="정기보수로 1주 비가동")
        text = str(pack)
        self.assertNotIn("mcm_transition", text)
        self.assertNotIn("mcm_quantity_delta", text)
        self.assertEqual(pack["manufacturing"]["activity_policy"]["back_process"],
                         "SW + BW + LC SAP production receipt PCS total")
        self.assertEqual(pack["business_notes"], ["정기보수로 1주 비가동"])
        self.assertEqual(pack["reconciliation"]["status"], "PASS")

    def test_prompts_forbid_recalculation_and_unsupported_causes(self):
        pack = build_fact_pack(self.sample_result())
        executive = build_executive_prompt(pack)
        question = build_question_prompt(pack, "왜 영업이익이 감소했어?")
        synthesis = build_synthesis_prompt(pack)
        for prompt in (executive, question, synthesis):
            self.assertIn("숫자를 변경하거나 새로 계산하지 않는다", prompt)
            self.assertIn("MCM은 현재 V1에서 별도 효과로 식별되지 않았으므로", prompt)
            self.assertIn("FACT PACK", prompt)
        self.assertIn("왜 영업이익이 감소했어?", question)

    def test_check_reconciliation_is_carried_into_fact_pack(self):
        result = self.sample_result()
        result["reconciled"] = False
        result["residual"] = 10_000_000
        pack = build_fact_pack(result)
        self.assertEqual(pack["reconciliation"]["status"], "CHECK")
        self.assertEqual(pack["reconciliation"]["residual_million_krw"], 10.0)


if __name__ == "__main__":
    unittest.main()
