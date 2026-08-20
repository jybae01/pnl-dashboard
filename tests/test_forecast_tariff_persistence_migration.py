from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / (
    "supabase/migrations/"
    "202608210001_forecast_tariff_metadata_finalize_v11.sql"
)
FOUNDATION = ROOT / "supabase/migrations/202608090001_phase1_foundation.sql"


def _compact(value: str) -> str:
    return " ".join(value.lower().split())


def test_v11_finalize_is_versioned_atomic_and_uses_existing_metadata_columns():
    sql = _compact(MIGRATION.read_text(encoding="utf-8"))

    assert "create function public.finalize_forecast_generation_v11(" in sql
    assert (
        "select * into v_model from public.finalize_forecast_generation(" in sql
    )
    assert "select public.finalize_forecast_generation(" not in sql
    assert "update public.models model_row set regional_sales_monthly" in sql
    assert "tariff_applicable_rate = 0.85" in sql
    assert "tariff_rate = 0.10" in sql
    assert "tariff_adjustment_monthly = '{}'::jsonb" in sql
    assert "tariff_in_workbook = true" in sql
    assert "forecast_generation_id = p_generation_id" in sql
    assert "source_kind = 'forecast_generated'" in sql
    assert "returning * into v_model" in sql
    assert "if not found then raise exception" in sql
    assert sql.startswith("begin;") and sql.endswith("commit;")


def test_v11_finalize_derives_only_regional_revenue_from_reserved_request():
    sql = _compact(MIGRATION.read_text(encoding="utf-8"))

    assert "v_request.request_payload #> '{request,months}'" in sql
    assert "month_item.value -> 'na_sa_sales'" in sql
    assert "jsonb_object_agg(" in sql
    assert "v1.1 월별" not in sql
    assert "p_tariff" not in sql
    assert "p_regional" not in sql
    assert "generic" not in sql


def test_v11_finalize_preserves_old_rpc_and_restricts_execute_privileges():
    sql = _compact(MIGRATION.read_text(encoding="utf-8"))

    assert "drop function" not in sql
    assert "create or replace function public.finalize_forecast_generation(" not in sql
    assert "revoke all on function public.finalize_forecast_generation_v11(" in sql
    assert ") from public, anon, authenticated, service_role;" in sql
    assert "grant execute on function public.finalize_forecast_generation_v11(" in sql
    assert ") to service_role;" in sql
    assert "security definer set search_path = ''" in sql


def test_migration_does_not_relax_models_or_rls_security():
    sql = _compact(MIGRATION.read_text(encoding="utf-8"))
    foundation = _compact(FOUNDATION.read_text(encoding="utf-8"))

    assert "grant update" not in sql
    assert "alter table" not in sql
    assert "drop table" not in sql
    assert "cascade" not in sql
    assert "disable row level security" not in sql
    assert "revoke update, delete, truncate on table public.models" in foundation


def test_v11_finalize_signature_is_distinct_by_name_not_overload():
    sql = _compact(MIGRATION.read_text(encoding="utf-8"))
    signature = (
        "uuid, uuid, text, text, integer, text, text, jsonb, text, text, text"
    )

    assert signature in sql
    assert sql.count("public.finalize_forecast_generation_v11(") == 3
