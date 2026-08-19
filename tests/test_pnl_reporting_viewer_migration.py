from pathlib import Path


MIGRATION = Path("supabase/migrations/202608190002_pnl_reporting_viewer_read_slice_c.sql")
BOOTSTRAP_MIGRATION = Path(
    "supabase/migrations/202608190003_pnl_reporting_viewer_year_bootstrap.sql"
)


def test_viewer_rpc_is_additive_service_role_only_and_fixed_search_path():
    text = MIGRATION.read_text(encoding="utf-8").casefold()
    assert "create or replace function public.get_pnl_reporting_viewer_source" in text
    function = text.split(
        "create or replace function public.get_pnl_reporting_viewer_source", 1
    )[1]
    assert "security definer" in function
    assert "set search_path = ''" in function
    assert "pg_catalog.coalesce" not in function
    assert "revoke all on function public.get_pnl_reporting_viewer_source(integer)" in function
    assert "from public, anon, authenticated, service_role" in function
    assert "grant execute on function public.get_pnl_reporting_viewer_source(integer)" in function
    assert "to service_role" in function
    assert "to authenticated" not in function
    assert "to anon" not in function


def test_viewer_rpc_reads_only_active_canonical_identity_without_reporting_arithmetic():
    text = MIGRATION.read_text(encoding="utf-8").casefold()
    assert "from public.pnl_reporting_active_datasets" in text
    assert "left join public.pnl_reporting_datasets" in text
    assert "on dataset.id = active.dataset_id" in text
    assert "canonical_schema_version" in text
    assert "canonical_payload" in text
    assert "actual_through_month" in text
    assert "uploaded_at" in text
    assert "superseded_at" in text
    assert "superseded_by_dataset_id" in text
    assert "is_default" not in text
    assert "is_published" not in text
    assert "calculation_results" not in text
    assert "pnl_dashboard" not in text
    assert "revenue" not in text
    assert "margin" not in text


def test_viewer_year_bootstrap_is_backend_authoritative_and_service_role_only():
    text = BOOTSTRAP_MIGRATION.read_text(encoding="utf-8").casefold()
    assert "p_reporting_year integer default null" in text
    assert "'selected_year', v_selected_year" in text
    assert "pg_catalog.max(active.reporting_year)" in text
    assert "pg_catalog.date_part('year', pg_catalog.now())" in text
    assert "where active.reporting_year = v_selected_year" in text
    assert "set search_path = ''" in text
    assert "from public, anon, authenticated, service_role" in text
    assert "to service_role" in text
    assert "to authenticated" not in text
    assert "to anon" not in text
