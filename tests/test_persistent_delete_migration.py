from pathlib import Path


MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "supabase/migrations/20260815023857_persistent_delete_slice3.sql"
)
SQL = MIGRATION.read_text(encoding="utf-8").lower()


def test_delete_coordination_is_additive_rls_locked_and_service_role_only():
    assert "create table public.persistent_delete_receipts" in SQL
    assert "enable row level security" in SQL
    assert "revoke all on table public.persistent_delete_receipts" in SQL
    assert "from public, anon, authenticated, service_role" in SQL
    for function in (
        "prepare_model_persistent_delete",
        "prepare_analysis_persistent_delete",
        "complete_persistent_delete",
        "record_persistent_delete_cleanup_failure",
    ):
        assert f"security definer\nset search_path = ''" in SQL
        assert f"grant execute on function public.{function}" in SQL
    assert "grant execute" in SQL and "to authenticated" not in SQL
    assert "create policy" not in SQL
    assert "on delete cascade" not in SQL


def test_model_delete_preflights_every_real_reference_and_owned_saga_state():
    for source in (
        "public.calculation_jobs",
        "public.calculation_results",
        "public.forecast_generation_requests",
        "public.models derived",
        "public.model_ingestion_requests",
    ):
        assert source in SQL
    for field in (
        "job.model_id", "job.baseline_model_id", "job.comparison_model_id",
        "result_row.model_id", "result_row.baseline_model_id",
        "result_row.comparison_model_id", "request_row.base_model_id",
        "derived.source_model_id",
    ):
        assert field in SQL
    assert "v_ingestion_status <> 'completed'" in SQL
    assert "v_generation_status <> 'completed'" in SQL
    assert "'blocked_in_use'::text" in SQL
    assert SQL.index("delete from public.models model_row") < SQL.index(
        "delete from public.model_ingestion_requests request_row"
    )


def test_analysis_delete_is_terminal_owned_and_never_deletes_models():
    analysis_start = SQL.index("create or replace function public.prepare_analysis_persistent_delete")
    analysis_end = SQL.index("create or replace function public.complete_persistent_delete")
    analysis = SQL[analysis_start:analysis_end]
    assert "v_job.status not in ('completed', 'failed')" in analysis
    assert "queue_archived_at is null" in analysis
    assert analysis.index("delete from public.calculation_results") < analysis.index(
        "delete from public.calculation_jobs"
    )
    assert "delete from public.models" not in analysis
    assert "delete from public.forecast_generation_requests" not in analysis
    assert "delete from public.model_ingestion_requests" not in analysis


def test_storage_identity_is_canonical_and_sql_never_deletes_storage_objects():
    assert "storage_bucket = 'pnl-models'" in SQL
    assert "models/%s/source.xlsx" in SQL
    assert "models/%s/jobs/%s/result.xlsx" in SQL
    assert "is_valid_pnl_storage_path" in SQL
    assert "delete from storage.objects" not in SQL
    assert "storage.remove" not in SQL


def test_receipt_supports_partial_failure_and_idempotent_cleanup_replay():
    assert "storage_status in ('pending', 'cleanup_required', 'complete')" in SQL
    assert "cleanup_attempts" in SQL
    assert "unique (resource_type, resource_id)" in SQL
    assert "when v_receipt.storage_status = 'complete'" in SQL
    assert "then 'deleted' else 'ready_for_storage'" in SQL
    assert "idempotent_replayed" in SQL
    assert "persistent_delete_receipts_audit" in SQL
