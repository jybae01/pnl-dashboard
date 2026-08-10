from pathlib import Path


SQL = (Path(__file__).resolve().parents[1] / "supabase" / "migrations" / "202608090003_phase2_publication_boundary.sql").read_text(encoding="utf-8").lower()
FOUNDATION = (Path(__file__).resolve().parents[1] / "supabase" / "migrations" / "202608090001_phase1_foundation.sql").read_text(encoding="utf-8").lower()


def test_migration_order_is_phase1_then_queue_then_publication():
    migration_dir = Path(__file__).resolve().parents[1] / "supabase" / "migrations"
    assert [path.name for path in sorted(migration_dir.glob("*.sql"))] == [
        "202608090001_phase1_foundation.sql",
        "202608090002_phase2_queue_worker.sql",
        "202608090003_phase2_publication_boundary.sql",
        "202608090004_phase25_analysis_inputs.sql",
    ]


def test_worker_completion_legacy_flags_have_no_publication_authority():
    completion = SQL.split("create or replace function public.complete_calculation_job", 1)[1].split("create or replace function public.set_calculation_result_publication", 1)[0]
    assert "deprecated abi compatibility only" in completion
    assert "p_workbook_path, false, false, null" in completion
    assert "p_workbook_path, p_is_published" not in completion


def test_admin_publication_rpc_is_narrow_and_service_role_only():
    assert "only a completed calculation result can be published" in SQL
    assert "if p_is_default and not p_is_published" in SQL
    assert "set is_default = false" in SQL
    assert "grant execute on function public.set_calculation_result_publication" in SQL
    assert "from public, anon, authenticated" in SQL
    assert "set search_path = public, pg_temp" in SQL
    assert "result mapping provenance is not published" in SQL
    assert "job.model_id = result_row.model_id" in SQL
    assert SQL.index("where id = p_result_id") < SQL.index("for update of result_row")
    assert SQL.index("from public.models where id = v_model_id for update") < SQL.index(
        "for update of result_row"
    )


def test_viewer_rpc_and_rls_require_completed_model_match_and_published_mapping():
    viewer = SQL.split(
        "create or replace function public.get_published_calculation_result", 1
    )[1]
    assert "job.model_id = result_row.model_id" in viewer
    assert "job.status = 'completed'" in viewer
    assert "config.status = 'published'" in viewer
    assert "config.version = result_row.mapping_version" in viewer
    assert "config.content_hash = result_row.mapping_hash" in viewer
    assert "from public, anon, authenticated" in viewer
    assert "grant execute on function public.get_published_calculation_result() to service_role" in viewer
    assert "create policy calculation_results_read_policy" in SQL
    assert "create policy pnl_storage_read_policy" in SQL


def test_publication_update_does_not_mutate_payload_or_provenance():
    publication = SQL.split("create or replace function public.set_calculation_result_publication", 1)[1]
    update = publication.split("update public.calculation_results", 2)[2].split("where id", 1)[0]
    for immutable in ("result =", "engine_version =", "mapping_version =", "mapping_hash =", "result_schema_version ="):
        assert immutable not in update


def test_publication_updates_are_audited_and_audit_log_remains_append_only():
    assert "calculation_results_audit after insert or update or delete" in FOUNDATION
    assert "before update or delete or truncate on public.audit_logs" in FOUNDATION
