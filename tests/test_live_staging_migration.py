from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SQL = (
    ROOT
    / "supabase/migrations/20260811085901_revoke_audit_trigger_rpc_013.sql"
).read_text(encoding="utf-8").lower()
LOCKOUT_SQL = (
    ROOT
    / "supabase/migrations/20260811091516_fix_shared_lockout_null_014.sql"
).read_text(encoding="utf-8").lower()
MONTH_SERIES_SQL = (
    ROOT
    / "supabase/migrations/20260811145917_fix_analysis_month_series_pg17.sql"
).read_text(encoding="utf-8").lower()
DASHBOARD_SQL = (
    ROOT
    / "supabase/migrations/20260811150705_align_pnl_dashboard_viewer_contract.sql"
).read_text(encoding="utf-8").lower()
RESTORED_DASHBOARD_SQL = (
    ROOT
    / "supabase/migrations/20260811151052_restore_pnl_dashboard_default_contract.sql"
).read_text(encoding="utf-8").lower()


def test_audit_trigger_is_not_exposed_as_a_browser_rpc():
    assert SQL.startswith("-- live postgresql 17/supabase advisor correction.")
    assert "revoke execute on function public.append_row_audit_log()" in SQL
    assert "from public, anon, authenticated" in SQL
    assert SQL.rstrip().endswith("commit;")


def test_unlocked_shared_limiter_returns_true_instead_of_sql_null():
    assert "create or replace function public.record_bff_login_failure" in LOCKOUT_SQL
    assert "not coalesce(v_row.locked_until > now(), false)" in LOCKOUT_SQL
    assert "pg_advisory_xact_lock" in LOCKOUT_SQL
    assert LOCKOUT_SQL.rstrip().endswith("commit;")


def test_analysis_month_series_selects_the_postgresql_17_integer_overload():
    assert "create or replace function public.create_durable_calculation_job_idempotent" in MONTH_SERIES_SQL
    assert "p_start_month::integer" in MONTH_SERIES_SQL
    assert "p_end_month::integer" in MONTH_SERIES_SQL
    assert "from pg_catalog.generate_series" in MONTH_SERIES_SQL
    assert "generate_series(p_start_month, p_end_month)" not in MONTH_SERIES_SQL
    assert "uuid, uuid, smallint, smallint, numeric, numeric," in MONTH_SERIES_SQL
    assert "language plpgsql" in MONTH_SERIES_SQL
    assert "security definer" in MONTH_SERIES_SQL
    assert "set search_path = ''" in MONTH_SERIES_SQL
    assert "perform public.enqueue_calculation_job(v_job.id)" in MONTH_SERIES_SQL
    assert "from public, anon, authenticated" in MONTH_SERIES_SQL
    assert ") to service_role;" in MONTH_SERIES_SQL
    assert MONTH_SERIES_SQL.rstrip().endswith("commit;")


def test_live_dashboard_selector_matches_the_migration_010_availability_contract():
    assert "create or replace function public.get_pnl_dashboard_viewer" in DASHBOARD_SQL
    assert "get_calculation_result_presentation_viewer_by_id" in DASHBOARD_SQL
    assert "jsonb_typeof(available.result_payload -> 'pnl_dashboard') = 'object'" in DASHBOARD_SQL
    assert "available.is_default desc" in DASHBOARD_SQL
    assert "available.created_at desc" in DASHBOARD_SQL
    assert "and available.is_default" not in DASHBOARD_SQL
    assert "dashboard_model.is_default" not in DASHBOARD_SQL
    assert "security definer" in DASHBOARD_SQL
    assert "set search_path = ''" in DASHBOARD_SQL
    assert "from public, anon, authenticated" in DASHBOARD_SQL
    assert "to service_role;" in DASHBOARD_SQL
    assert DASHBOARD_SQL.rstrip().endswith("commit;")


def test_final_dashboard_selector_restores_the_migration_011_default_contract():
    assert "create or replace function public.get_pnl_dashboard_viewer" in RESTORED_DASHBOARD_SQL
    assert "and available.is_default" in RESTORED_DASHBOARD_SQL
    assert "dashboard_model.is_default and dashboard_model.is_published" in RESTORED_DASHBOARD_SQL
    assert "get_calculation_result_presentation_viewer_by_id" in RESTORED_DASHBOARD_SQL
    assert "security definer" in RESTORED_DASHBOARD_SQL
    assert "set search_path = ''" in RESTORED_DASHBOARD_SQL
    assert "from public, anon, authenticated" in RESTORED_DASHBOARD_SQL
    assert "to service_role;" in RESTORED_DASHBOARD_SQL
    assert RESTORED_DASHBOARD_SQL.rstrip().endswith("commit;")
