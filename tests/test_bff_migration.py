from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "supabase/migrations/202608090005_bff_foundation.sql"
SQL = MIGRATION.read_text(encoding="utf-8").lower()


def section(start: str, end: str) -> str:
    return SQL.split(start, 1)[1].split(end, 1)[0]


def test_migration_chain_is_additive_through_slice3_persistent_delete():
    assert [path.name for path in sorted(MIGRATION.parent.glob("*.sql"))] == [
        "202608090001_phase1_foundation.sql",
        "202608090002_phase2_queue_worker.sql",
        "202608090003_phase2_publication_boundary.sql",
        "202608090004_phase25_analysis_inputs.sql",
        "202608090005_bff_foundation.sql",
        "202608090006_react_core_vertical_slice.sql",
        "202608090007_model_ingestion_vertical_slice.sql",
        "202608090008_evidence_history_vertical_slice.sql",
        "202608090009_analysis_presentation_vertical_slice.sql",
        "202608090010_pnl_dashboard_vertical_slice.sql",
        "202608090011_forecast_react_vertical_slice.sql",
        "202608090012_production_hardening_foundation.sql",
        "20260811085901_revoke_audit_trigger_rpc_013.sql",
        "20260811091516_fix_shared_lockout_null_014.sql",
        "20260811145917_fix_analysis_month_series_pg17.sql",
        "20260811150705_align_pnl_dashboard_viewer_contract.sql",
        "20260811151052_restore_pnl_dashboard_default_contract.sql",
        "202608120001_demand_only_worker_lifecycle.sql",
        "20260815023857_persistent_delete_slice3.sql",
        "20260815050758_persistent_delete_recovery_slice3a.sql",
        "20260815053855_persistent_delete_status_classification_slice3a.sql",
        "20260815055055_persistent_delete_storage_requirement_slice3a.sql",
        "202608190001_pnl_reporting_persistence_slice_b.sql",
        "202608190002_pnl_reporting_viewer_read_slice_c.sql",
        "202608190003_pnl_reporting_viewer_year_bootstrap.sql",
        "202608210001_forecast_tariff_metadata_finalize_v11.sql",
        "202608210002_analysis_monthly_fx_idempotent_v11.sql",
    ]
    assert SQL.startswith("-- trusted bff foundation")
    assert "begin;" in SQL and SQL.rstrip().endswith("commit;")


def test_actor_scoped_idempotency_replaces_global_key_and_preserves_legacy_nulls():
    assert "drop constraint if exists calculation_jobs_idempotency_key_key" in SQL
    assert "add column if not exists idempotency_actor text" in SQL
    assert "add column if not exists request_fingerprint jsonb" in SQL
    assert "uq_calculation_jobs_idempotency_actor_key" in SQL
    assert "(idempotency_actor, idempotency_key)" in SQL
    assert "where idempotency_actor is not null and idempotency_key is not null" in SQL
    assert "jsonb_typeof(request_fingerprint) = 'object'" in SQL


def test_idempotent_creation_is_lock_serialized_and_detects_payload_collision():
    creation = section(
        "create or replace function public.create_durable_calculation_job_idempotent",
        "create or replace function public.get_calculation_job_status_by_id",
    )
    lock_at = creation.index("pg_advisory_xact_lock")
    lookup_at = creation.index("existing_job.idempotency_actor")
    insert_at = creation.index("insert into public.calculation_jobs")
    assert lock_at < lookup_at < insert_at
    assert "hashtextextended" in creation
    assert "idempotency_conflict" in creation
    assert "v_existing.request_fingerprint is distinct from v_fingerprint" in creation
    assert "jsonb_build_object" in creation
    for field in (
        "baseline_model_id", "comparison_model_id", "start_month", "end_month",
        "baseline_sales_fx", "comparison_sales_fx", "engine_version",
        "mapping_version", "mapping_hash", "result_schema_version", "max_attempts",
    ):
        assert f"'{field}'" in creation
    assert "perform public.enqueue_calculation_job(v_job.id)" in creation
    assert "return query select v_existing.id, v_existing.status, true" in creation
    assert "return query select v_job.id, v_job.status, false" in creation


def test_new_submit_validates_model_pair_hash_mapping_period_fx_and_release():
    creation = section(
        "create or replace function public.create_durable_calculation_job_idempotent",
        "create or replace function public.get_calculation_job_status_by_id",
    )
    assert "baseline and comparison models must be different" in creation
    assert "invalid analysis month range" in creation
    assert "sales fx values must be positive" in creation
    assert "'nan'::numeric" in creation
    assert "baseline and comparison models must have the same year" in creation
    assert "both models must have recorded workbook sha-256 values" in creation
    assert "config.status = 'published'" in creation
    assert "invalid release provenance" in creation
    assert "p_comparison_model_id, p_baseline_model_id, p_comparison_model_id" in creation


def test_job_idempotency_and_request_are_immutable():
    guard = section(
        "create or replace function public.guard_job_immutable_fields",
        "create or replace function public.create_durable_calculation_job_idempotent",
    )
    for field in ("idempotency_actor", "idempotency_key", "request_fingerprint"):
        assert f"new.{field}" in guard and f"old.{field}" in guard
    assert "new.analysis_request" in guard and "old.analysis_request" in guard


def test_job_by_id_rpc_is_explicit_and_has_no_worker_internal_fields():
    job = section(
        "create or replace function public.get_calculation_job_status_by_id",
        "create or replace function public.get_calculation_result_admin_preview_by_id",
    )
    for field in (
        "job_id uuid", "status text", "baseline_model_id uuid",
        "comparison_model_id uuid", "start_month smallint", "end_month smallint",
        "attempt integer", "max_attempts integer", "heartbeat_at timestamptz",
        "completed_at timestamptz", "result_id uuid", "error_code text",
        "error_message text",
    ):
        assert field in job
    for internal in ("claim_token", "claimed_by", "queue_message_id", "storage_path"):
        assert internal not in job


def test_admin_preview_allows_unpublished_but_requires_completed_matching_provenance():
    preview = section(
        "create or replace function public.get_calculation_result_admin_preview_by_id",
        "create or replace function public.validate_calculation_result_availability",
    )
    assert "job.status = 'completed'" in preview
    assert "result_row.baseline_model_id = job.baseline_model_id" in preview
    assert "result_row.comparison_model_id = job.comparison_model_id" in preview
    assert "result_row.mapping_hash = job.mapping_hash" in preview
    where_clause = preview.split("where result_row.id = p_result_id", 1)[1]
    assert "and result_row.is_published" not in where_clause


def test_viewer_availability_is_one_query_and_enforces_every_predicate():
    availability = section(
        "create or replace function public.validate_calculation_result_availability",
        "create or replace function public.get_available_calculation_result_by_id",
    )
    for predicate in (
        "result_row.is_published",
        "job.status = 'completed'",
        "baseline_model.is_published",
        "comparison_model.is_published",
        "baseline_model.workbook_sha256 = result_row.baseline_workbook_sha256",
        "comparison_model.workbook_sha256 = result_row.comparison_workbook_sha256",
        "result_row.baseline_model_id = job.baseline_model_id",
        "result_row.comparison_model_id = job.comparison_model_id",
        "result_row.engine_version = job.engine_version",
        "result_row.mapping_version = job.mapping_version",
        "result_row.mapping_hash = job.mapping_hash",
        "result_row.result_schema_version = job.result_schema_version",
        "result_row.result_schema_version = any(p_supported_result_schema_versions)",
        "config.status = 'published'",
        "config.content_hash = result_row.mapping_hash",
    ):
        assert predicate in availability
    viewer = section(
        "create or replace function public.get_available_calculation_result_by_id",
        "revoke all on function public.create_durable_calculation_job_idempotent",
    )
    assert "public.validate_calculation_result_availability" in viewer
    assert "result_row.result -> 'analysis_view'" in viewer


def test_every_bff_rpc_is_service_role_only_with_fixed_search_path():
    functions = (
        "create_durable_calculation_job_idempotent",
        "get_calculation_job_status_by_id",
        "get_calculation_result_admin_preview_by_id",
        "validate_calculation_result_availability",
        "get_available_calculation_result_by_id",
    )
    for name in functions:
        body = SQL.split(f"create or replace function public.{name}", 1)[1]
        assert "security definer" in body.split("$$;", 1)[0]
        assert "set search_path = ''" in body.split("$$;", 1)[0]
        assert f"revoke all on function public.{name}" in SQL
        assert f"grant execute on function public.{name}" in SQL
    grants = SQL.split("revoke all on function public.create_durable", 1)[1]
    assert "from public, anon, authenticated" in grants
    assert "to service_role" in grants
    assert " to anon" not in grants and " to authenticated" not in grants
