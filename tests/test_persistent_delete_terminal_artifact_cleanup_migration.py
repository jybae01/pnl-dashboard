from pathlib import Path


MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "supabase/migrations/202608240002_model_delete_terminal_artifact_cleanup.sql"
)
SQL = MIGRATION.read_text(encoding="utf-8").lower()


def test_terminal_artifact_cleanup_is_forward_only_and_service_role_only():
    assert "create or replace function public.list_model_terminal_analysis_dependencies" in SQL
    assert "create or replace function public.complete_model_terminal_analysis_dependency" in SQL
    assert "security definer" in SQL
    assert "set search_path = ''" in SQL
    assert "alter table" not in SQL
    assert "create table" not in SQL
    assert "on delete cascade" not in SQL
    assert "delete from storage.objects" not in SQL
    assert "storage.remove" not in SQL
    assert "grant execute on function public.list_model_terminal_analysis_dependencies(uuid)" in SQL
    assert "grant execute on function public.complete_model_terminal_analysis_dependency(uuid, uuid, text, text)" in SQL
    assert "to authenticated" not in SQL


def test_list_rpc_exposes_only_locked_terminal_owned_result_paths():
    listing = SQL[
        SQL.index("create or replace function public.list_model_terminal_analysis_dependencies") :
        SQL.index("create or replace function public.complete_model_terminal_analysis_dependency")
    ]
    for marker in (
        "assert_model_terminal_analysis_cleanup_safe",
        "for update of job",
        "for update",
        "job.status in ('completed', 'failed')",
        "terminal analysis shape is invalid",
        "terminal analysis queue state is unsettled",
        "terminal analysis result is protected",
        "terminal analysis storage ownership is invalid",
        "result_row.workbook_path is not null",
        "public.is_valid_pnl_storage_path",
        "models/%s/jobs/%s/result.xlsx",
    ):
        assert marker in listing


def test_completion_rpc_rechecks_target_binding_and_deletes_fk_rows_in_order():
    completion = SQL[SQL.index("create or replace function public.complete_model_terminal_analysis_dependency") :]
    for marker in (
        "assert_model_terminal_analysis_cleanup_safe",
        "for update",
        "terminal analysis does not reference target model",
        "terminal analysis queue state is unsettled",
        "terminal analysis result is protected",
        "terminal analysis storage binding changed",
        "public.is_valid_pnl_storage_path",
        "delete from public.calculation_results",
        "delete from pgmq.a_calculation_jobs",
        "delete from public.calculation_jobs",
    ):
        assert marker in completion
    assert completion.index("delete from public.calculation_results") < completion.index(
        "delete from pgmq.a_calculation_jobs"
    )
    assert completion.index("delete from pgmq.a_calculation_jobs") < completion.index(
        "delete from public.calculation_jobs"
    )
