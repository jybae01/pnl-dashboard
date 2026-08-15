from pathlib import Path


MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "supabase/migrations/20260815053855_persistent_delete_status_classification_slice3a.sql"
)
SQL = MIGRATION.read_text(encoding="utf-8").lower()


def test_status_lookup_mirrors_prepare_locks_and_blocking_classifications():
    assert "create or replace function public.get_persistent_delete_status" in SQL
    assert "from public.models model_row" in SQL
    assert "from public.calculation_jobs job" in SQL
    assert "from public.calculation_results result_row" in SQL
    assert SQL.count("for update;") >= 5
    assert "'blocked_non_terminal'" in SQL
    assert "'blocked_in_use'" in SQL
    assert "'blocked_protected'" in SQL
    assert "'not_committed'" in SQL
    assert "'prepare_uncertain'" in SQL


def test_status_lookup_mirrors_queue_integrity_and_reference_checks():
    assert "queue_archived_at is null" in SQL
    assert "'queue_state', 'unsettled'" in SQL
    assert "'completed_result_missing'" in SQL
    assert "'failed_result_present'" in SQL
    assert "'model_storage_ownership_invalid'" in SQL
    assert "'analysis_storage_ownership_invalid'" in SQL
    for reference in (
        "analysis_jobs",
        "analysis_results",
        "forecast_generations",
        "derived_models",
    ):
        assert f"'{reference}'" in SQL


def test_status_lookup_remains_service_role_only_and_path_safe():
    signature = "public.get_persistent_delete_status(text, uuid)"
    assert f"revoke all on function {signature}" in SQL
    assert f"grant execute on function {signature}" in SQL
    assert "to service_role" in SQL
    assert "to authenticated" not in SQL
    assert "security definer" in SQL
    assert "set search_path = ''" in SQL
    assert "delete from storage.objects" not in SQL
    assert "on delete cascade" not in SQL
