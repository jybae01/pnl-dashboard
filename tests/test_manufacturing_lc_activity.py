from pathlib import Path

from forecast.analysis import ActivityRecord, AnalysisScenario, ExpenseRecord, PnlRecord, ProductRecord, ScenarioMeta
from forecast.analysis.configuration import AnalysisConfig
from forecast.analysis.manufacturing_effects import calculate_manufacturing_effects


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "analysis_v1.json"


def _scenario(scenario_id: str, *, products, account: str, amount: float) -> AnalysisScenario:
    return AnalysisScenario(
        meta=ScenarioMeta(scenario_id, "PLAN", "v1"),
        products=products,
        manufacturing_expenses=[ExpenseRecord("2026-07", account, amount, "manufacturing", 0, 1)],
        activities=[ActivityRecord("2026-07", inventory_realization_rate=1)],
        pnl=[PnlRecord("2026-07", 0, 0, 0)],
    )


def test_back_process_activity_uses_sw_bw_lc_total_sap_receipts():
    config = AnalysisConfig.load(CONFIG)
    base = _scenario(
        "base",
        account="수도광열비",
        amount=1750,
        products=[
            ProductRecord("2026-07", "SW", "SW", sap_production_qty=100),
            ProductRecord("2026-07", "BW", "BW", sap_production_qty=50),
            ProductRecord("2026-07", "LC", "LC", sap_production_qty=25),
        ],
    )
    comparison = _scenario(
        "comparison",
        account="수도광열비",
        amount=2000,
        products=[
            ProductRecord("2026-07", "SW", "SW", sap_production_qty=80),
            ProductRecord("2026-07", "BW", "BW", sap_production_qty=70),
            ProductRecord("2026-07", "LC", "LC", sap_production_qty=50),
        ],
    )

    result = calculate_manufacturing_effects(base, comparison, config)
    detail = result.details[0]

    assert detail["base_back_activity"] == 175
    assert detail["comparison_back_activity"] == 200
    assert result.back_activity == -250
    assert result.back_unit == 0


def test_outsourcing_activity_includes_lc_but_still_excludes_mcm_quantity():
    config = AnalysisConfig.load(CONFIG)
    base = _scenario(
        "base",
        account="외주가공비",
        amount=1200,
        products=[
            ProductRecord(
                "2026-07", "SW_NORMAL", "SW", sap_production_qty=100,
                outsourcing_eligible_flag=True,
            ),
            ProductRecord(
                "2026-07", "LC_NORMAL", "LC", sap_production_qty=20,
                outsourcing_eligible_flag=True,
            ),
            ProductRecord(
                "2026-07", "SW_MCM", "SW", sap_production_qty=30,
                outsourcing_eligible_flag=True, mcm_flag=True, mcm_qty=30,
            ),
        ],
    )
    comparison = _scenario(
        "comparison",
        account="외주가공비",
        amount=1300,
        products=[
            ProductRecord(
                "2026-07", "SW_NORMAL", "SW", sap_production_qty=80,
                outsourcing_eligible_flag=True,
            ),
            ProductRecord(
                "2026-07", "LC_NORMAL", "LC", sap_production_qty=50,
                outsourcing_eligible_flag=True,
            ),
            ProductRecord(
                "2026-07", "SW_MCM", "SW", sap_production_qty=60,
                outsourcing_eligible_flag=True, mcm_flag=True, mcm_qty=60,
            ),
        ],
    )

    result = calculate_manufacturing_effects(base, comparison, config)
    detail = result.details[0]

    assert detail["base_back_activity"] == 120
    assert detail["comparison_back_activity"] == 130
    assert result.back_activity == -100
    assert result.back_unit == 0
