from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "supabase/migrations/202608190001_pnl_reporting_persistence_slice_b.sql"


def sql() -> str:
    return MIGRATION.read_text(encoding="utf-8").lower()


def test_reporting_domain_has_three_additive_rls_protected_tables():
    text = sql()
    for table in (
        "pnl_reporting_datasets",
        "pnl_reporting_active_datasets",
        "pnl_reporting_ingestion_requests",
    ):
        assert f"create table public.{table}" in text
        assert f"alter table public.{table} enable row level security" in text
        assert f"revoke all on table public.{table}" in text
    assert "grant select on table public.pnl_reporting" not in text
    assert "grant insert on table public.pnl_reporting" not in text
    assert "grant update on table public.pnl_reporting" not in text
    assert "grant delete on table public.pnl_reporting" not in text


def test_dataset_constraints_cover_type_through_template_sha_and_canonical_identity():
    text = sql()
    dataset = text.split("create table public.pnl_reporting_datasets", 1)[1].split(
        "create table public.pnl_reporting_active_datasets", 1
    )[0]
    assert "dataset_type in ('plan', 'actual')" in dataset
    assert "dataset_type = 'plan' and actual_through_month is null" in dataset
    assert "dataset_type = 'actual'" in dataset
    assert "actual_through_month is not null" in dataset
    assert "actual_through_month between 1 and 12" in dataset
    assert "template_version = 'pnl_reporting_v1'" in dataset
    assert "canonical_schema_version = 'pnl_reporting_canonical_v1'" in dataset
    assert "canonical_payload jsonb not null" in dataset
    assert "canonical_payload ->> 'dataset_type' = dataset_type" in dataset
    assert "canonical_payload ->> 'reporting_year'" in dataset
    assert "source_sha256 ~ '^[0-9a-f]{64}$'" in dataset
    assert "source_path = 'reporting/' || id::text || '/source.xlsx'" in dataset


def test_active_pointer_is_unique_and_composite_fk_enforces_year_type_consistency():
    text = sql()
    active = text.split("create table public.pnl_reporting_active_datasets", 1)[1].split(
        "create table public.pnl_reporting_ingestion_requests", 1
    )[0]
    assert "primary key (reporting_year, dataset_type)" in active
    assert "foreign key (dataset_id, reporting_year, dataset_type)" in active
    assert "references public.pnl_reporting_datasets (id, reporting_year, dataset_type)" in active
    assert "on update restrict on delete restrict" in active


def test_dataset_is_immutable_delete_protected_and_has_no_cascade_business_deletion():
    text = sql()
    assert "guard_pnl_reporting_dataset_immutability" in text
    assert "prevent_pnl_reporting_dataset_delete" in text
    assert "pnl reporting datasets cannot be deleted in v1" in text
    assert "on delete cascade" not in text
    assert "delete from public.pnl_reporting_datasets" not in text
    assert "is_default" not in text
    assert "is_published" not in text


def test_reservation_is_actor_scoped_fingerprinted_and_recovery_safe():
    text = sql()
    assert "unique (idempotency_actor, idempotency_key)" in text
    assert "request_fingerprint ~ '^[0-9a-f]{64}$'" in text
    assert "pg_advisory_xact_lock" in text
    assert "idempotency_conflict" in text
    assert "in_progress" in text
    assert "cleanup_required" in text
    assert "get_completed_pnl_reporting_ingestion" in text
    assert "get_pnl_reporting_ingestion_recovery_queue" in text
    assert "acknowledge_pnl_reporting_ingestion_cleanup" in text
    assert "p_storage_cleanup_confirmed" in text
    ingestion = text.split(
        "create table public.pnl_reporting_ingestion_requests", 1
    )[1].split("create or replace function public.touch_pnl_reporting_updated_at", 1)[0]
    assert "dataset_type = 'actual'" in ingestion
    assert "actual_through_month is not null" in ingestion
    assert "actual_through_month between 1 and 12" in ingestion


def test_finalize_is_one_locked_transaction_for_insert_swap_supersession_and_completion():
    text = sql()
    finalize = text.split(
        "create or replace function public.finalize_pnl_reporting_ingestion", 1
    )[1].split("create or replace function public.get_completed_pnl_reporting_ingestion", 1)[0]
    assert "'pnl-reporting:' || v_request.reporting_year::text" in finalize
    assert "v_activated_at := pg_catalog.clock_timestamp()" in finalize
    assert "insert into public.pnl_reporting_datasets" in finalize
    assert "insert into public.pnl_reporting_active_datasets" in finalize
    assert "on conflict (reporting_year, dataset_type) do update" in finalize
    assert "superseded_by_dataset_id = v_dataset.id" in finalize
    assert "set status = 'completed'" in finalize
    assert "response_payload = v_response" in finalize
    assert "p_canonical_payload -> 'actual_through_month'" in finalize
    assert "is distinct from v_request.actual_through_month" in finalize


def test_security_definer_rpcs_have_empty_search_path_and_service_role_only_execution():
    text = sql()
    assert text.count("security definer\nset search_path = ''") >= 7
    for rpc in (
        "reserve_pnl_reporting_ingestion",
        "heartbeat_pnl_reporting_ingestion",
        "finalize_pnl_reporting_ingestion",
        "get_completed_pnl_reporting_ingestion",
        "record_pnl_reporting_ingestion_failure",
        "get_pnl_reporting_ingestion_recovery_queue",
        "acknowledge_pnl_reporting_ingestion_cleanup",
    ):
        assert f"function public.{rpc}" in text
        assert f"grant execute on function public.{rpc}" in text
    assert "from public, anon, authenticated, service_role" in text
    assert "to service_role" in text


def test_migration_does_not_mutate_legacy_or_forecast_business_tables():
    text = sql()
    forbidden = (
        "calculation_results",
        "sales_effects",
        "inventory_timing",
        "residual",
        "golden",
        "legacy pnl_dashboard",
        "public.models",
    )
    assert all(token not in text for token in forbidden)
    assert text.strip().endswith("commit;")
