from pathlib import Path


MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "supabase/migrations/202608240001_model_delete_terminal_reference_cleanup.sql"
)
SQL = MIGRATION.read_text(encoding="utf-8").lower()


def _section(start: str, end: str) -> str:
    return SQL[SQL.index(start):SQL.index(end)]


def test_migration_is_forward_only_and_redefines_both_authoritative_model_paths():
    assert "create or replace function public.prepare_model_persistent_delete" in SQL
    assert "create or replace function public.get_persistent_delete_status" in SQL
    assert "alter table" not in SQL
    assert "create table" not in SQL
    assert "on delete cascade" not in SQL
    assert "delete from storage.objects" not in SQL
    assert "storage.remove" not in SQL


def test_active_refs_block_but_terminal_history_is_not_counted_as_in_use():
    prepare = _section(
        "create or replace function public.prepare_model_persistent_delete",
        "create or replace function public.get_persistent_delete_status",
    )
    status = SQL[SQL.index("create or replace function public.get_persistent_delete_status"):]
    for section in (prepare, status):
        assert "job.status in ('pending', 'processing')" in section
        assert "result_row.job_id" in section
        assert "'analysis_jobs', v_active_analysis_jobs" in section
        assert "'analysis_results', v_active_analysis_results" in section
        assert "'forecast_generations', v_forecast_uses" in section
        assert "'derived_models', v_derived_models" in section
        assert "job.status in ('completed', 'failed')" in section
        assert "analysis_storage_cleanup_required" in section
    references = prepare[prepare.index("v_references :="):prepare.index("-- a terminal job is cleaned")]
    assert "v_active_analysis_jobs" in references
    assert "v_active_analysis_results" in references
    assert "v_terminal_job_ids" not in references


def test_terminal_cleanup_is_fk_safe_and_does_not_report_artifactful_delete_as_complete():
    prepare = _section(
        "create or replace function public.prepare_model_persistent_delete",
        "create or replace function public.get_persistent_delete_status",
    )
    assert "array_agg(distinct job.id)" in prepare
    assert "result_row.workbook_path is not null" in prepare
    assert "analysis_storage_cleanup_required" in prepare
    assert "'blocked_in_use'::text" in prepare
    assert "resource_type, resource_id, owner_model_id" in prepare
    assert prepare.count("job.status in ('completed', 'failed')") >= 4
    assert prepare.index("delete from public.calculation_results") < prepare.index(
        "delete from public.calculation_jobs"
    )
    assert prepare.index("delete from public.calculation_jobs") < prepare.index(
        "delete from public.models model_row"
    )
    assert "delete from pgmq.a_calculation_jobs" in prepare
    assert "analysis_storage_ownership_invalid" in prepare
    assert "analysis_delete_receipt_conflict" in prepare
    assert "resource_type, resource_id, owner_model_id,\n        storage_bucket, storage_path, storage_status\n    )\n    select\n        'analysis'" not in prepare


def test_status_mirrors_terminal_integrity_and_protection_classification():
    status = SQL[SQL.index("create or replace function public.get_persistent_delete_status"):]
    for marker in (
        "analysis_terminal_shape_invalid",
        "queue_state', 'unsettled",
        "analysis_results_protected",
        "analysis_storage_ownership_invalid",
    ):
        assert marker in status
    assert "'not_committed'::text" in status
    assert "'blocked_protected'::text" in status
    assert "'blocked_in_use'::text" in status


def test_privileged_rpc_acl_and_path_validation_remain_fail_closed():
    for signature in (
        "public.prepare_model_persistent_delete(uuid)",
        "public.get_persistent_delete_status(text, uuid)",
    ):
        assert f"revoke all on function {signature}" in SQL
        assert f"grant execute on function {signature}" in SQL
    assert "security definer" in SQL
    assert "set search_path = ''" in SQL
    assert "public.is_valid_pnl_storage_path" in SQL
    assert "models/%s/source.xlsx" in SQL
    assert "models/%s/jobs/%s/result.xlsx" in SQL
