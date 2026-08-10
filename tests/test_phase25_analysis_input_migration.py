from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "supabase/migrations/202608090004_phase25_analysis_inputs.sql"
SQL = MIGRATION.read_text(encoding="utf-8").lower()


def section(start: str, end: str) -> str:
    return SQL.split(start, 1)[1].split(end, 1)[0]


def test_legacy_comparison_identity_is_explicitly_backfilled():
    assert "set comparison_model_id = model_id" in SQL
    assert "where comparison_model_id is null" in SQL
    assert "check (model_id = comparison_model_id)" in SQL


def test_baseline_recovery_priority_uses_request_then_completed_result_only():
    request = SQL.index("analysis_request ->> 'baseline_model_id'")
    completed = SQL.index("result_row.result -> 'comparison_result' -> 'baseline' ->> 'id'")
    assert request < completed
    result_recovery = section("with result_baselines as", "-- result backfill")
    assert "job.status = 'completed'" in result_recovery
    assert "candidate.baseline_model_id <> job.comparison_model_id" in SQL
    assert "baseline_model.model_year = comparison_model.model_year" in SQL
    backfill = section("-- model_id has always identified", "create or replace function public.guard_model_workbook_sha256")
    assert "is_default" not in backfill
    assert "get_default" not in backfill


def test_unresolved_active_legacy_jobs_are_detected_without_status_rewrite():
    unresolved = section(
        "create or replace function public.get_unresolved_active_calculation_jobs",
        "create or replace function public.enqueue_calculation_job",
    )
    assert "status in ('pending', 'processing')" in unresolved
    assert "baseline_model_id is null" in unresolved
    assert "baseline_workbook_sha256 is null" in unresolved
    assert "update public.calculation_jobs" not in unresolved
    assert "input_provenance_unresolved" in SQL


def test_claim_does_not_execute_or_archive_unresolved_active_legacy_jobs():
    claim = section(
        "create or replace function public.claim_calculation_job",
        "create or replace function public.create_durable_calculation_job",
    )
    unresolved = claim.split("-- preserve the receipt", 1)[1].split("perform 1", 1)[0]
    assert "job.status in ('pending', 'processing')" in unresolved
    assert "pgmq.set_vt" in unresolved
    assert "pgmq.archive" not in unresolved
    assert "update public.calculation_jobs" not in unresolved


def test_legacy_signed_upload_job_creator_is_explicitly_retired():
    assert "phase 2 signed-upload initializer" in SQL
    assert "revoke execute on function public.initialize_calculation_upload" in SQL
    assert "revoke execute on function public.mark_calculation_upload_completed" in SQL
    assert "from service_role" in SQL


def test_new_job_contract_requires_both_models_year_hash_and_mapping():
    creation = section(
        "create or replace function public.create_durable_calculation_job",
        "create or replace function public.complete_calculation_job",
    )
    assert "baseline_model_id is required" in creation
    assert "comparison_model_id is required" in creation
    assert "baseline and comparison models must be different" in creation
    assert "v_baseline.model_year <> v_comparison.model_year" in creation
    assert "both models must have recorded workbook sha-256 values" in creation
    assert "config.status = 'published'" in creation
    assert "v_baseline.workbook_sha256, v_comparison.workbook_sha256" in creation
    assert "p_comparison_model_id, p_baseline_model_id, p_comparison_model_id" in creation


def test_job_snapshot_is_immutable_after_default_or_model_state_changes():
    guard = section(
        "create or replace function public.guard_job_immutable_fields",
        "create or replace function public.guard_calculation_result_fields",
    )
    for field in (
        "baseline_model_id",
        "comparison_model_id",
        "model_id",
        "baseline_workbook_sha256",
        "comparison_workbook_sha256",
        "engine_version",
        "mapping_version",
        "mapping_hash",
        "result_schema_version",
    ):
        assert f"new.{field}" in guard
        assert f"old.{field}" in guard


def test_complete_rpc_copies_result_provenance_from_locked_job():
    completion = section(
        "create or replace function public.complete_calculation_job",
        "create or replace function public.set_calculation_result_publication",
    )
    assert "where id = p_job_id\n     for update" in completion
    assert "v_job.baseline_model_id, v_job.comparison_model_id" in completion
    assert "v_job.baseline_workbook_sha256, v_job.comparison_workbook_sha256" in completion
    assert "v_job.engine_version, v_job.mapping_version, v_job.mapping_hash" in completion
    insert_values = completion.split(") values (", 1)[1].split(") returning id", 1)[0]
    assert "p_engine_version" not in insert_values
    assert "p_mapping_version" not in insert_values
    assert "p_mapping_hash" not in insert_values
    assert "p_result_schema_version" not in insert_values


def test_result_payload_and_full_provenance_are_immutable():
    guard = section(
        "create or replace function public.guard_calculation_result_fields",
        "-- deployment precheck",
    )
    for field in (
        "baseline_model_id",
        "comparison_model_id",
        "baseline_workbook_sha256",
        "comparison_workbook_sha256",
        "result",
        "engine_version",
        "mapping_version",
        "mapping_hash",
        "result_schema_version",
    ):
        assert f"new.{field}" in guard
        assert f"old.{field}" in guard


def test_publication_requires_complete_matching_inputs_and_both_published_models():
    publication = section(
        "create or replace function public.set_calculation_result_publication",
        "create or replace function public.get_published_calculation_result",
    )
    assert "job.status = 'completed'" in publication
    assert "result_row.baseline_model_id = job.baseline_model_id" in publication
    assert "result_row.comparison_model_id = job.comparison_model_id" in publication
    assert "result_row.model_id = result_row.comparison_model_id" in publication
    assert "result_row.baseline_workbook_sha256 = job.baseline_workbook_sha256" in publication
    assert "result_row.comparison_workbook_sha256 = job.comparison_workbook_sha256" in publication
    assert "baseline_model.is_published" in publication
    assert "comparison_model.is_published" in publication
    assert "baseline_model.workbook_sha256 = v_result.baseline_workbook_sha256" in publication
    assert "comparison_model.workbook_sha256 = v_result.comparison_workbook_sha256" in publication
    assert "result input provenance does not match completed job" in publication
    assert "create policy pnl_storage_read_policy" in SQL


def test_migration_contract_is_001_through_004():
    assert [path.name for path in sorted(MIGRATION.parent.glob("*.sql"))] == [
        "202608090001_phase1_foundation.sql",
        "202608090002_phase2_queue_worker.sql",
        "202608090003_phase2_publication_boundary.sql",
        "202608090004_phase25_analysis_inputs.sql",
    ]
