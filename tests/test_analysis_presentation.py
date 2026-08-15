from __future__ import annotations

from pathlib import Path

import pytest

from forecast.bff.analysis_presentation import (
    EFFECT_ORDER,
    AnalysisPresentationService,
    build_analysis_presentation,
)
from forecast.bff.auth import AccessCodeSessionService
from forecast.bff.errors import ApiErrorCode, BffError
from forecast.provenance import ResultProvenance


BASE_ID = "11111111-1111-4111-8111-111111111111"
COMP_ID = "22222222-2222-4222-8222-222222222222"
JOB_ID = "33333333-3333-4333-8333-333333333333"
RESULT_ID = "44444444-4444-4444-8444-444444444444"
PROVENANCE = ResultProvenance("engine-1", "mapping-1", "a" * 64, "1")


def presentation_row() -> dict:
    effects = {
        "sales_quantity": 10.0,
        "sales_mix": -2.0,
        "sales_price": 8.0,
        "sales_fx": 4.0,
        "material_total": -5.0,
        "manufacturing_realized": 6.0,
        "inventory_timing": 2.0,
        "sga_variable": 3.0,
        "sga_fixed": 4.0,
        "tariff": -1.0,
    }
    result = {
        "baseline": {"id": BASE_ID, "name": "Base"},
        "comparison": {"id": COMP_ID, "name": "Comparison"},
        "period": {"key": "R2026_01_02", "label": "1~2월", "months": [1, 2]},
        "pnl": [
            {"code": "revenue", "baseline": 1000.0, "comparison": 1100.0, "delta": 100.0},
            {"code": "operating_profit", "baseline": 100.0, "comparison": 135.0, "delta": 35.0},
        ],
        "effects": [
            {"code": code, "factor": code, "profit_effect": value}
            for code, value in effects.items()
        ],
        "operating_profit_delta": 35.0,
        "effects_total": 29.0,
        "residual": 6.0,
        "reconciled": False,
        "sales_analysis": {
            "baseline_fx_krw_per_usd": 1400.0,
            "comparison_fx_krw_per_usd": 1450.0,
            "rows": [
                {
                    "product_group": "SW", "baseline_quantity": 100.0,
                    "comparison_quantity": 110.0, "quantity_delta": 10.0,
                    "baseline_amount": 600.0, "comparison_amount": 660.0,
                    "quantity_effect": 6.0, "pure_price_effect": 3.0,
                    "sales_fx_effect": 2.0,
                },
                {
                    "product_group": "LC", "baseline_quantity": 20.0,
                    "comparison_quantity": 19.0, "quantity_delta": -1.0,
                    "baseline_amount": 200.0, "comparison_amount": 190.0,
                    "quantity_effect": 0.0, "pure_price_effect": 1.0,
                    "sales_fx_effect": 1.0,
                },
                {
                    "product_group": "FS", "baseline_quantity": 200.0,
                    "comparison_quantity": 220.0, "quantity_delta": 20.0,
                    "baseline_amount": 200.0, "comparison_amount": 250.0,
                    "quantity_effect": 4.0, "pure_price_effect": 1.0,
                    "sales_fx_effect": 1.0,
                },
            ],
            "totals": {
                "quantity_effect": 10.0,
                "mix_effect": -2.0,
                "displayed_sales_price_effect": 5.0,
                "pure_price_effect": 5.0,
                "sales_price_effect": 8.0,
                "sales_fx_effect": 4.0,
                "baseline_transport_ex_tariff": 20.0,
                "comparison_transport_ex_tariff": 17.0,
                "transport_effect": 3.0,
                "transport_quantity_effect": 0.0,
                "transport_unit_effect": 3.0,
                "tariff_effect": -1.0,
                "total_sales_effect": 20.0,
            },
        },
        "material_analysis": {
            "total": -5.0,
            "nonwoven_price_ex_fx": -2.0,
            "nonwoven_jpy": -1.0,
            "materials_ex_nonwoven": -2.0,
            "product_groups": [],
        },
        "inventory_analysis": {
            "source_validation_status": "PASS",
            "scope_validation_status": "PASS",
            "base_manufactured_cogs": 100.0,
            "comparison_manufactured_cogs": 88.0,
            "manufactured_cogs_effect": 12.0,
            "base_current_manufacturing_cost": 90.0,
            "comparison_current_manufacturing_cost": 80.0,
            "current_manufacturing_cost_effect": 10.0,
            "inventory_timing_effect": 2.0,
        },
        "manufacturing_accounts": [
            {
                "row": 290, "account": "수도광열비", "classification": "variable",
                "baseline_amount": 10.0, "comparison_amount": 6.0, "delta": -4.0,
                "final_profit_effect": 4.0, "inventory_realization_rate": 1.0,
                "calculation_status": "완료",
            },
            {
                "row": 291, "account": "노무비", "classification": "fixed",
                "baseline_amount": 5.0, "comparison_amount": 3.0, "delta": -2.0,
                "final_profit_effect": 2.0, "inventory_realization_rate": 1.2,
                "calculation_status": "완료",
            },
        ],
        "sga_accounts": [
            {
                "row": 1168, "account": "고객배송 운반비", "classification": "transport",
                "baseline_amount": 20.0, "comparison_amount": 17.0, "delta": -3.0,
                "profit_effect": 0.0,
            },
            {
                "row": 1190, "account": "시장비", "classification": "variable",
                "baseline_amount": 8.0, "comparison_amount": 5.0, "delta": -3.0,
                "profit_effect": 3.0,
            },
            {
                "row": 1200, "account": "급여", "classification": "fixed",
                "baseline_amount": 10.0, "comparison_amount": 6.0, "delta": -4.0,
                "profit_effect": 4.0,
            },
            {
                "row": None, "account": "관세", "classification": "tariff",
                "baseline_amount": 0.0, "comparison_amount": 1.0, "delta": 1.0,
                "profit_effect": -1.0,
            },
        ],
    }
    analysis_view = {
        "manufacturing": {
            "activities": [
                {"process": "전공정", "production_basis": "FS", "unit": "m", "baseline": 100.0, "comparison": 120.0, "delta": 20.0},
                {"process": "후공정", "production_basis": "SW+BW+LC", "unit": "PCS", "baseline": 200.0, "comparison": 210.0, "delta": 10.0},
            ],
        },
    }
    return {
        "result_id": RESULT_ID,
        "job_id": JOB_ID,
        "result_payload": {
            "payload_schema_version": "1",
            "comparison_result": result,
            "analysis_view": analysis_view,
            "fact_pack": {"reconciliation": {"status": "CHECK"}},
        },
        "analysis_request": {
            "start_month": 1, "end_month": 2,
            "baseline_sales_fx": 1400.0, "comparison_sales_fx": 1450.0,
        },
        "baseline_model_id": BASE_ID,
        "baseline_model_name": "Base model",
        "comparison_model_id": COMP_ID,
        "comparison_model_name": "Comparison model",
        "baseline_workbook_sha256": "b" * 64,
        "comparison_workbook_sha256": "c" * 64,
        "engine_version": PROVENANCE.engine_version,
        "mapping_version": PROVENANCE.mapping_version,
        "mapping_hash": PROVENANCE.mapping_hash,
        "result_schema_version": PROVENANCE.result_schema_version,
        "completed_at": "2026-08-11T01:00:00+00:00",
        "created_at": "2026-08-11T01:00:01+00:00",
        "is_published": False,
        "is_default": False,
        "published_at": None,
    }


def test_mapper_uses_exact_canonical_effects_and_identity_without_plugging():
    response = build_analysis_presentation(RESULT_ID, presentation_row(), PROVENANCE, ("1",))
    assert tuple(effect.code for effect in response.effects) == EFFECT_ORDER
    assert sum(effect.profit_effect for effect in response.effects) == response.kpis.effects_total
    assert response.kpis.effects_total + response.residual.amount == response.kpis.operating_profit_delta
    assert response.residual.classification == "UNEXPLAINED"
    assert response.kpis.baseline_revenue == 1000.0
    assert response.kpis.comparison_revenue == 1100.0
    assert response.identity.baseline_sales_fx == 1400.0
    assert response.identity.comparison_sales_fx == 1450.0


def test_customer_freight_is_once_tariff_separate_and_material_policy_is_preserved():
    response = build_analysis_presentation(RESULT_ID, presentation_row(), PROVENANCE, ("1",))
    by_code = {effect.code: effect for effect in response.effects}
    assert "transport" not in by_code
    assert by_code["sales_price"].profit_effect == 8.0
    transport = next(row for row in by_code["sales_price"].drilldown.rows if "운반비" in row.label)
    assert transport.profit_effect == 3.0
    assert by_code["tariff"].profit_effect == -1.0
    material = by_code["material_total"].drilldown.rows
    assert [row.profit_effect for row in material] == [-2.0, -1.0, -2.0]
    assert "KRW/100JPY" not in str(response)
    assert all("mcm" not in effect.code.casefold() for effect in response.effects)


def test_product_and_activity_units_never_mix_and_lc_is_four_inch():
    response = build_analysis_presentation(RESULT_ID, presentation_row(), PROVENANCE, ("1",))
    groups = {row.code: row for row in response.product_groups}
    assert groups["LC"].display_name == "4인치 LC"
    assert groups["LC"].quantity_unit == "PCS"
    assert groups["FS"].quantity_unit == "m"
    assert {(row.production_basis, row.unit) for row in response.manufacturing_activities} == {
        ("FS", "m"), ("SW+BW+LC", "PCS")
    }


def test_net_inventory_timing_payload_validates_gross_and_overlap_contract():
    row = presentation_row()
    inventory = row["result_payload"]["comparison_result"]["inventory_analysis"]
    inventory.update({
        "gross_inventory_timing_effect": 10.0,
        "core_cogs_quantity_overlap_effect": 5.0,
        "core_cogs_mix_overlap_effect": 3.0,
        "core_manufactured_cogs_overlap_effect": 8.0,
        "core_overlap_policy_status": "APPLIED_CORE_ONLY",
        "core_overlap_source_validation_status": "PASS",
        "core_overlap_pool_validation_status": "PASS",
    })

    build_analysis_presentation(RESULT_ID, row, PROVENANCE, ("1",))

    inventory["core_manufactured_cogs_overlap_effect"] = 7.0
    with pytest.raises(BffError):
        build_analysis_presentation(RESULT_ID, row, PROVENANCE, ("1",))


@pytest.mark.parametrize(
    "status_field",
    (
        "core_overlap_policy_status",
        "core_overlap_source_validation_status",
        "core_overlap_pool_validation_status",
    ),
)
def test_net_inventory_timing_payload_requires_authoritative_policy_status(
    status_field: str,
):
    row = presentation_row()
    inventory = row["result_payload"]["comparison_result"]["inventory_analysis"]
    inventory.update({
        "gross_inventory_timing_effect": 10.0,
        "core_cogs_quantity_overlap_effect": 5.0,
        "core_cogs_mix_overlap_effect": 3.0,
        "core_manufactured_cogs_overlap_effect": 8.0,
        "core_overlap_policy_status": "APPLIED_CORE_ONLY",
        "core_overlap_source_validation_status": "PASS",
        "core_overlap_pool_validation_status": "PASS",
    })
    inventory[status_field] = "FAIL"

    with pytest.raises(BffError):
        build_analysis_presentation(RESULT_ID, row, PROVENANCE, ("1",))


@pytest.mark.parametrize("mutation", ["effects_total", "transport_quantity", "transport_duplicate", "fx_snapshot", "inventory_source", "payload_schema"])
def test_mismatch_payload_is_rejected_not_repaired(mutation):
    row = presentation_row()
    result = row["result_payload"]["comparison_result"]
    if mutation == "effects_total":
        result["effects_total"] = 28.0
    elif mutation == "transport_quantity":
        result["sales_analysis"]["totals"]["transport_quantity_effect"] = 1.0
    else:
        if mutation == "transport_duplicate":
            result["sga_accounts"][0]["profit_effect"] = 3.0
        elif mutation == "fx_snapshot":
            result["sales_analysis"]["baseline_fx_krw_per_usd"] = 999.0
        elif mutation == "inventory_source":
            result["inventory_analysis"]["source_validation_status"] = "FAIL"
        else:
            row["result_payload"]["payload_schema_version"] = "unsupported"
    with pytest.raises(BffError) as caught:
        build_analysis_presentation(RESULT_ID, row, PROVENANCE, ("1",))
    assert caught.value.code == ApiErrorCode.INPUT_INTEGRITY_MISMATCH


class Gateway:
    def __init__(self):
        self.row = presentation_row()
        self.available = True

    def get_admin_analysis_presentation(self, *_args, **_kwargs):
        return self.row

    def get_viewer_analysis_presentation(self, *_args, **_kwargs):
        return self.row if self.available else None

    def validate_result_availability(self, *_args, **_kwargs):
        return self.available


def test_admin_unpublished_preview_and_viewer_stale_revalidation_are_separate():
    sessions = AccessCodeSessionService(
        viewer_code="viewer", admin_code="admin", actor_namespace_secret="secret" * 8
    )
    admin = sessions.login("admin").session_id
    viewer = sessions.login("viewer").session_id
    gateway = Gateway()
    service = AnalysisPresentationService(
        sessions, gateway, PROVENANCE, supported_result_schema_versions=("1",)
    )
    assert service.admin_read(admin, RESULT_ID).identity.is_published is False
    assert service.viewer_read(viewer, RESULT_ID).identity.result_id == RESULT_ID
    gateway.available = False
    with pytest.raises(BffError) as caught:
        service.viewer_read(viewer, RESULT_ID)
    assert caught.value.code == ApiErrorCode.RESULT_NOT_AVAILABLE
    with pytest.raises(BffError) as forbidden:
        service.admin_read(viewer, RESULT_ID)
    assert forbidden.value.code == ApiErrorCode.FORBIDDEN


def test_viewer_malformed_stored_payload_is_safe_invalid_payload_not_empty():
    sessions = AccessCodeSessionService(
        viewer_code="viewer", admin_code="admin", actor_namespace_secret="secret" * 8
    )
    viewer = sessions.login("viewer").session_id
    gateway = Gateway()
    gateway.row["result_payload"]["comparison_result"]["effects_total"] = 28.0
    service = AnalysisPresentationService(
        sessions, gateway, PROVENANCE, supported_result_schema_versions=("1",)
    )
    with pytest.raises(BffError) as caught:
        service.viewer_read(viewer, RESULT_ID)
    assert caught.value.code == ApiErrorCode.INPUT_INTEGRITY_MISMATCH
    assert str(caught.value) == "Analysis presentation payload is invalid"


def test_migration_009_is_narrow_additive_and_service_role_only():
    sql = Path(
        "supabase/migrations/202608090009_analysis_presentation_vertical_slice.sql"
    ).read_text(encoding="utf-8").lower()
    assert "get_calculation_result_presentation_admin_by_id" in sql
    assert "get_calculation_result_presentation_viewer_by_id" in sql
    assert "validate_calculation_result_availability" in sql
    assert "jsonb_typeof(result_row.result -> 'comparison_result') = 'object'" in sql
    assert "jsonb_typeof(result_row.result -> 'analysis_view') = 'object'" in sql
    assert "jsonb_typeof(result_row.result -> 'fact_pack') = 'object'" in sql
    assert "set search_path = ''" in sql
    assert "from public, anon, authenticated" in sql
    assert "to service_role" in sql
    assert "workbook_path" not in sql
    assert "claim_token" not in sql
