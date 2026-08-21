from pathlib import Path


MIGRATION = Path("supabase/migrations/202608210002_analysis_monthly_fx_idempotent_v11.sql")


def _sql() -> str:
    return MIGRATION.read_text(encoding="utf-8")


def test_monthly_fx_migration_is_additive_and_service_role_only():
    sql = _sql()

    assert "create or replace function public.create_durable_calculation_job_idempotent_v11(" in sql
    assert "p_baseline_sales_fx_monthly jsonb" in sql
    assert "p_comparison_sales_fx_monthly jsonb" in sql
    assert "set search_path = ''" in sql
    assert "revoke all on function public.create_durable_calculation_job_idempotent_v11(" in sql
    assert ") from public, anon, authenticated;" in sql
    assert ") to service_role;" in sql

    # This migration must not alter the legacy scalar RPC or broaden table/RLS
    # access. Existing deployments retain the old submission boundary.
    assert "create or replace function public.create_durable_calculation_job_idempotent(" not in sql
    assert "alter table" not in sql.lower()
    assert "create policy" not in sql.lower()
    assert "grant select" not in sql.lower()
    assert "grant insert" not in sql.lower()


def test_monthly_fx_migration_validates_exact_keys_and_positive_numbers():
    sql = _sql()

    assert "jsonb_typeof(p_baseline_sales_fx_monthly) <> 'object'" in sql
    assert "jsonb_typeof(p_comparison_sales_fx_monthly) <> 'object'" in sql
    assert "^[0-9]{4}-(0[1-9]|1[0-2])$" in sql
    assert "jsonb_typeof(entry.value) <> 'number'" in sql
    assert "(entry.value #>> '{}')::numeric > 0" in sql
    assert "('NaN', 'Infinity', '-Infinity')" in sql
    assert "v_expected_year := v_baseline.model_year::text" in sql
    assert "v_expected_count := p_end_month - p_start_month + 1" in sql
    assert sql.count("p_start_month::integer, p_end_month::integer") == 3
    assert "jsonb_object_keys(p_baseline_sales_fx_monthly)" in sql
    assert "jsonb_object_keys(p_comparison_sales_fx_monthly)" in sql
    assert "monthly sales FX keys must exactly match" in sql


def test_monthly_fx_migration_persists_maps_in_fingerprint_and_atomic_job():
    sql = _sql()

    assert "'baseline_sales_fx_monthly', p_baseline_sales_fx_monthly" in sql
    assert "'comparison_sales_fx_monthly', p_comparison_sales_fx_monthly" in sql
    assert "existing_job.idempotency_actor = p_idempotency_actor" in sql
    assert "existing_job.idempotency_key = p_idempotency_key" in sql
    assert "v_existing.request_fingerprint is distinct from v_fingerprint" in sql
    assert "'IDEMPOTENCY_CONFLICT: key already used for another request'" in sql
    assert "'baseline_sales_fx'," not in sql
    assert "'comparison_sales_fx'," not in sql
    assert "perform public.enqueue_calculation_job(v_job.id);" in sql
    assert "max_attempts, created_by, analysis_request," in sql
    assert "idempotency_actor, idempotency_key, request_fingerprint" in sql
