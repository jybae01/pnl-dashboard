from __future__ import annotations

import pytest

from forecast.analysis.configuration import AnalysisConfig
from forecast.analysis.sales_effects import calculate_sales_effects
from forecast.analysis.schema import AnalysisScenario, ProductRecord, ScenarioMeta
from forecast.bff.application import _validate_submit
from forecast.bff.dto import AnalysisSubmitRequest
from forecast.bff.errors import BffError
from forecast.worker_runtime import AnalysisRequest


BASE = "11111111-1111-4111-8111-111111111111"
COMPARISON = "22222222-2222-4222-8222-222222222222"
CONFIG = AnalysisConfig.load("config/analysis_v1.json")


def maps():
    return (
        {"2026-07": 1480.0, "2026-08": 1480.0, "2026-09": 1480.0},
        {"2026-07": 1380.0, "2026-08": 1420.0, "2026-09": 1500.0},
    )


def request(**overrides):
    baseline, comparison = maps()
    values = {
        "baseline_model_id": BASE,
        "comparison_model_id": COMPARISON,
        "start_month": 7,
        "end_month": 9,
        "idempotency_key": "monthly-fx",
        "baseline_sales_fx_monthly": baseline,
        "comparison_sales_fx_monthly": comparison,
    }
    values.update(overrides)
    return AnalysisSubmitRequest(**values)


@pytest.mark.parametrize(
    "mutation",
    ("middle_missing", "base_missing", "comparison_missing", "extra", "wrong_key", "zero", "negative", "malformed"),
)
def test_monthly_fx_submit_validation_is_exact_and_strict(mutation):
    baseline, comparison = maps()
    if mutation == "middle_missing":
        baseline.pop("2026-08"); comparison.pop("2026-08")
    elif mutation == "base_missing":
        baseline.pop("2026-08")
    elif mutation == "comparison_missing":
        comparison.pop("2026-08")
    elif mutation == "extra":
        baseline["2026-10"] = 1480.0; comparison["2026-10"] = 1500.0
    elif mutation == "wrong_key":
        baseline["2026-8"] = baseline.pop("2026-08")
    elif mutation == "zero":
        comparison["2026-08"] = 0.0
    elif mutation == "negative":
        comparison["2026-08"] = -1.0
    else:
        comparison["2026-08"] = "1402"  # type: ignore[assignment]
    with pytest.raises(BffError):
        _validate_submit(request(
            baseline_sales_fx_monthly=baseline,
            comparison_sales_fx_monthly=comparison,
        ))


def test_worker_monthly_request_is_authoritative_and_legacy_scalar_still_parses():
    baseline, comparison = maps()
    parsed = AnalysisRequest.parse({
        "months": [7, 8, 9],
        "baseline_sales_fx_monthly": baseline,
        "comparison_sales_fx_monthly": comparison,
    })
    parsed.validate_period(2026, (7, 8, 9))
    assert parsed.baseline_sales_fx is None and parsed.comparison_sales_fx is None
    assert parsed.comparison_sales_fx_monthly == comparison
    with pytest.raises(ValueError, match="selected analysis period"):
        parsed.validate_period(2025, (7, 8, 9))

    legacy = AnalysisRequest.parse({
        "months": [7, 8, 9], "baseline_sales_fx": 1480.0,
        "comparison_sales_fx": 1490.0,
    })
    assert legacy.baseline_sales_fx == 1480.0
    assert legacy.baseline_sales_fx_monthly is None


def scenario(identifier: str, fx: dict[str, float], *, comparison: bool) -> AnalysisScenario:
    products = []
    for index, month in enumerate(("2026-07", "2026-08", "2026-09"), start=1):
        quantity = 100.0 + index * 10 + (20.0 if comparison else 0.0)
        price = 1000.0 + index * 100 + (100.0 if comparison else 0.0)
        products.append(ProductRecord(
            month, f"SW-{index}", "SW", sales_qty=quantity,
            sales_amount=quantity * price, product_cogs=quantity * 600.0,
            sales_fx=fx[month], sales_fx_source=f"Analysis request input: fx[{month}]",
        ))
    return AnalysisScenario(meta=ScenarioMeta(identifier, "ACTUAL", "v1"), products=products)


def test_different_monthly_fx_changes_only_price_fx_allocation_and_reconciles_months():
    baseline, comparison = maps()
    varying = calculate_sales_effects(
        scenario("base", baseline, comparison=False),
        scenario("comparison", comparison, comparison=True),
        CONFIG,
    )
    fixed_comparison = {month: 1490.0 for month in comparison}
    fixed = calculate_sales_effects(
        scenario("base", baseline, comparison=False),
        scenario("comparison", fixed_comparison, comparison=True),
        CONFIG,
    )

    assert [row["comparison_sales_fx"] for row in varying.monthly_effects] == [1380.0, 1420.0, 1500.0]
    assert len({row["sales_fx_effect"] for row in varying.monthly_effects}) == 3
    assert sum(row["sales_price_effect"] for row in varying.monthly_effects) == pytest.approx(varying.price)
    assert sum(row["sales_fx_effect"] for row in varying.monthly_effects) == pytest.approx(varying.sales_fx)
    assert varying.quantity == pytest.approx(fixed.quantity)
    assert varying.mix == pytest.approx(fixed.mix)
    assert varying.price + varying.sales_fx == pytest.approx(fixed.price + fixed.sales_fx)
