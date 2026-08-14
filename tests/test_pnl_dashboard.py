from __future__ import annotations

import copy
from pathlib import Path

import pytest

from forecast.bff.auth import AccessCodeSessionService
from forecast.bff.errors import ApiErrorCode, BffError
from forecast.bff.pnl_dashboard import PnlDashboardService, build_pnl_dashboard_response
from forecast.presentation.pnl_dashboard import build_pnl_dashboard_snapshot


BASE_ID = "11111111-1111-4111-8111-111111111111"
COMP_ID = "22222222-2222-4222-8222-222222222222"
JOB_ID = "33333333-3333-4333-8333-333333333333"
RESULT_ID = "44444444-4444-4444-8444-444444444444"


def comparison(months=(1, 2), scale=1.0):
    def line(code, label, base, comp):
        return {"code": code, "item": label, "baseline": base * scale,
                "comparison": comp * scale, "delta": (comp - base) * scale}
    return {
        "baseline": {"id": BASE_ID, "name": "Plan", "year": 2026,
                     "period_types": {str(m): "계획" for m in range(1, 13)}},
        "comparison": {"id": COMP_ID, "name": "Actual", "year": 2026,
                       "period_types": {"1": "실적", "2": "추정"}},
        "period": {"months": list(months)},
        "pnl": [line("revenue", "매출액", 100, 120), line("cogs", "매출원가", 60, 70),
                line("gross_profit", "매출총이익", 40, 50),
                line("selling_expense", "판매비", 10, 10),
                line("general_admin", "일반관리비", 10, 13),
                line("operating_profit", "영업이익", 20, 27)],
        "cost_summary": [line("raw_material", "원재료비", 30, 33),
                         line("manufacturing_expense", "제조경비", 10, 12)],
        "material_analysis": {"nonwoven_price_ex_fx": -1, "nonwoven_jpy": -2,
                              "materials_ex_nonwoven": -3, "total": -6},
        "inventory_analysis": {"inventory_timing_effect": 0, "persistence": "MIXED",
                               "coverage": "LIMITED", "materiality_status": "UNCONFIGURED"},
        "manufacturing_accounts": [
            {"account": "변동 제조경비", "classification": "variable", "baseline_amount": 6,
             "comparison_amount": 7, "delta": 1, "final_profit_effect": -1,
             "inventory_realization_rate": 1, "activity_effect": -.4, "unit_effect": -.6,
             "fixed_effect": 0},
            {"account": "고정 제조경비", "classification": "fixed", "baseline_amount": 4,
             "comparison_amount": 5, "delta": 1, "final_profit_effect": -1,
             "inventory_realization_rate": 1, "activity_effect": 0, "unit_effect": 0,
             "fixed_effect": -1},
        ],
        "sga_accounts": [
            {"account": "급여", "classification": "fixed", "baseline_amount": 10,
             "comparison_amount": 12, "delta": 2, "profit_effect": -2},
            {"account": "고객배송 운반비", "classification": "transport", "baseline_amount": 2,
             "comparison_amount": 1, "delta": -1, "profit_effect": 0},
        ],
        "sales_groups": [
            {"product_group": "LC", "baseline_quantity": 3, "comparison_quantity": 4,
             "baseline_amount": 20, "comparison_amount": 25, "baseline_cogs": 12, "comparison_cogs": 14},
            {"product_group": "FS", "baseline_quantity": 100, "comparison_quantity": 110,
             "baseline_amount": 30, "comparison_amount": 35, "baseline_cogs": 15, "comparison_cogs": 17},
        ],
        "effects": [
            {"code": code, "factor": code, "profit_effect": amount}
            for code, amount in {
                "sales_quantity": 2, "sales_mix": 0, "sales_price": 1, "sales_fx": 0,
                "tariff": -1, "material_total": -2, "manufacturing_realized": -2,
                "inventory_timing": 0, "sga_variable": 2, "sga_fixed": -2,
            }.items()
        ],
        "effects_total": -2, "residual": 9, "operating_profit_delta": 7, "reconciled": False,
    }


def row():
    overall = comparison()
    monthly = [comparison((1,), .45), comparison((2,), .55)]
    dashboard = build_pnl_dashboard_snapshot(overall, monthly)
    return {"result_id": RESULT_ID, "job_id": JOB_ID, "dashboard": dashboard,
            "baseline_model_id": BASE_ID, "comparison_model_id": COMP_ID,
            "result_schema_version": "1", "completed_at": "2026-08-11T00:00:00+00:00",
            "published_at": "2026-08-11T01:00:00+00:00"}


def test_seven_blocks_are_canonical_and_fixed_cost_gate_is_complete():
    dashboard = row()["dashboard"]
    assert set(dashboard) == {"snapshot_version", "identity", "kpis", "monthly_series",
                              "pnl_statement", "manufacturing", "sga", "product_groups", "key_facts"}
    assert dashboard["identity"]["actual_months"] == [1]
    assert dashboard["identity"]["actual_through_month"] == 1
    assert [item["comparison_period_type"] for item in dashboard["monthly_series"]] == ["실적", "추정"]
    assert {item["classification"] for item in dashboard["manufacturing"]["accounts"]} == {"variable", "fixed"}
    assert sum(item["profit_effect"] for item in dashboard["manufacturing"]["accounts"]) == -2
    assert dashboard["manufacturing"]["fixed_cost_policy"]["manufacturing_effect_includes_variable_and_fixed"]
    assert dashboard["sga"]["fixed_scope"].startswith("fixed SG&A")
    assert dashboard["key_facts"]["effects_total"] + dashboard["key_facts"]["residual"] == 7


def test_lc_fs_units_and_null_are_not_combined_or_coerced():
    dashboard = row()["dashboard"]
    groups = {item["code"]: item for item in dashboard["product_groups"]}
    assert groups["LC"]["display_name"] == "4인치 LC"
    assert groups["LC"]["quantity_unit"] == "PCS"
    assert groups["FS"]["quantity_unit"] == "m"
    assert "total_quantity" not in dashboard
    zero_revenue = comparison()
    for item in zero_revenue["pnl"]:
        item.update(baseline=0, comparison=0, delta=0)
    months = [copy.deepcopy(zero_revenue)]
    months[0]["period"] = {"months": [1]}
    zero_revenue["period"] = {"months": [1]}
    built = build_pnl_dashboard_snapshot(zero_revenue, months)
    assert built["kpis"]["period_operating_margin"]["comparison"] is None


class Gateway:
    def __init__(self, value): self.value = value
    def get_viewer_pnl_dashboard(self, **_): return self.value


def test_viewer_service_ready_empty_and_invalid_are_distinct():
    sessions = AccessCodeSessionService(viewer_code="viewer", admin_code="admin", ttl_seconds=60,
                                        actor_namespace_secret="actor-secret" * 4)
    ticket = sessions.login("viewer")
    assert PnlDashboardService(sessions, Gateway(row()), supported_result_schema_versions=("1",)).viewer_read(ticket.session_id).result_id == RESULT_ID
    with pytest.raises(BffError) as empty:
        PnlDashboardService(sessions, Gateway(None), supported_result_schema_versions=("1",)).viewer_read(ticket.session_id)
    assert empty.value.code == ApiErrorCode.RESULT_NOT_AVAILABLE
    broken = row(); broken["dashboard"]["key_facts"]["residual"] = 10
    with pytest.raises(BffError) as invalid:
        build_pnl_dashboard_response(broken, ("1",))
    assert invalid.value.code == ApiErrorCode.INPUT_INTEGRITY_MISMATCH


def test_migration_010_is_additive_narrow_and_reuses_strict_viewer_availability():
    sql = Path("supabase/migrations/202608090010_pnl_dashboard_vertical_slice.sql").read_text(encoding="utf-8").lower()
    assert "get_pnl_dashboard_viewer" in sql
    assert "get_calculation_result_presentation_viewer_by_id" in sql
    assert "security definer" in sql and "set search_path = ''" in sql
    assert "revoke all" in sql and "grant execute" in sql and "service_role" in sql
    assert "claim_token" not in sql and "queue_receipt" not in sql and "storage_path" not in sql


@pytest.mark.parametrize("month", [1, 6, 12])
def test_month_snapshot_has_no_hard_coded_actual_cutoff(month):
    source = comparison((month,))
    source["comparison"]["period_types"] = {str(month): "실적" if month == 1 else "추정"}
    dashboard = build_pnl_dashboard_snapshot(source, [copy.deepcopy(source)])
    assert dashboard["identity"]["available_months"] == [month]
    assert dashboard["monthly_series"][0]["month"] == month
    assert dashboard["monthly_series"][0]["comparison_period_type"] == ("실적" if month == 1 else "추정")


def test_connected_dashboard_route_has_no_legacy_mock_or_hard_coded_business_values():
    view = Path("frontend/src/views/PnlStatusView.tsx").read_text(encoding="utf-8")
    panel = Path("frontend/src/integration/PnlDashboardPanel.tsx").read_text(encoding="utf-8")
    connected = view + panel
    for forbidden in ("pnlService", "dummyPnlData", "MAX_ACTUAL_MONTH", "9060", "setTimeout"):
        assert forbidden not in connected
