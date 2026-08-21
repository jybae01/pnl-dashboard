from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "supabase/migrations/202608090006_react_core_vertical_slice.sql"
SQL = MIGRATION.read_text(encoding="utf-8").lower()


def test_migration_006_is_additive_and_guards_published_model_snapshots():
    assert MIGRATION.exists()
    assert SQL.startswith("begin;") and SQL.rstrip().endswith("commit;")
    assert "create or replace function public.guard_bff_job_model_publication" in SQL
    assert "new.idempotency_actor is null" in SQL
    assert "order by model_row.id" in SQL and "for share" in SQL
    assert "analysis models must be published" in SQL
    assert "analysis model sha-256 snapshot mismatch" in SQL
    assert "before insert on public.calculation_jobs" in SQL
    assert "revoke all on function public.guard_bff_job_model_publication() from service_role" in SQL


def test_migration_chain_is_001_through_006_without_editing_prior_files():
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
