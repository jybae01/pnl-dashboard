from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "supabase/migrations/202608090007_model_ingestion_vertical_slice.sql"


def sql():
    return MIGRATION.read_text(encoding="utf-8").lower()


def test_ingestion_reservation_is_actor_scoped_race_safe_and_not_sha_deduplicated():
    text = sql()
    assert "unique (idempotency_actor, idempotency_key)" in text
    assert "pg_advisory_xact_lock" in text
    assert "idempotency_conflict" in text
    assert "unique (workbook_sha256)" not in text
    assert "if v_existing.status = 'reserved' then" in text
    assert "interval '15 minutes'" not in text


def test_finalization_forces_private_canonical_draft_and_published_mapping():
    text = sql()
    finalize = text.split("create or replace function public.finalize_model_ingestion", 1)[1]
    assert "'pnl-models'" in finalize
    assert "format('models/%s/source.xlsx'" in finalize
    assert "false, false, false" in finalize
    assert "config.status = 'published'" in finalize
    assert "v_request.workbook_sha256" in finalize


def test_cleanup_state_is_durable_audited_and_no_browser_or_direct_table_capability_exists():
    text = sql()
    assert "cleanup_required" in text
    assert "record_model_ingestion_failure" in text
    assert "model_ingestion_requests_audit" in text
    assert "revoke all on table public.model_ingestion_requests from service_role" in text
    assert "grant select on table public.model_ingestion_requests to service_role" not in text
    assert "from public, anon, authenticated" in text
    assert "to service_role" in text
    assert "get_model_ingestion_recovery_queue" in text
    assert "get_completed_model_ingestion" in text
    assert "acknowledge_model_ingestion_cleanup" in text
    assert "p_storage_cleanup_confirmed" in text
    assert "interval '1 hour'" in text


def test_publication_keeps_existing_abi_and_checks_sha_path_and_mapping():
    text = sql()
    publication = text.split("create or replace function public.set_model_publication", 1)[1]
    assert "workbook_sha256" in publication
    assert "models/%s/source.xlsx" in publication
    assert "mapping_status <> 'published'" in publication
    assert "config.status = 'published'" in publication
    assert "a default model must be published" in publication


def test_earlier_migrations_are_untouched_and_007_is_transactional():
    text = sql().strip()
    assert text.startswith("-- trusted-bff")
    assert "\nbegin;" in text[:300]
    assert text.endswith("commit;")
