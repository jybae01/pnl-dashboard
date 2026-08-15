from pathlib import Path


MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "supabase/migrations/20260815050758_persistent_delete_recovery_slice3a.sql"
)
SQL = MIGRATION.read_text(encoding="utf-8").lower()


def test_recovery_rpc_is_bounded_service_role_only_and_rls_table_stays_private():
    assert "create or replace function public.get_persistent_delete_status" in SQL
    assert "create or replace function public.list_persistent_delete_recovery" in SQL
    assert "p_limit integer default 100" in SQL
    assert "p_limit > 100" in SQL
    assert "limit p_limit" in SQL
    for signature in (
        "public.get_persistent_delete_status(text, uuid)",
        "public.list_persistent_delete_recovery(text, integer)",
    ):
        assert f"revoke all on function {signature}" in SQL
        assert f"grant execute on function {signature}" in SQL
    assert "to service_role" in SQL
    assert "to authenticated" not in SQL
    assert "create policy" not in SQL


def test_status_lookup_serializes_with_prepare_and_preserves_canonical_provenance():
    assert "pg_advisory_xact_lock" in SQL
    assert "'persistent-delete:' || p_resource_type" in SQL
    assert "from public.persistent_delete_receipts" in SQL
    assert "then 'deleted' else 'cleanup_required'" in SQL
    assert "'not_committed'" in SQL
    assert "'prepare_uncertain'" in SQL
    assert "receipt.storage_bucket" in SQL
    assert "receipt.storage_path" in SQL
    assert "receipt.owner_model_id" in SQL


def test_default_and_published_models_and_results_are_fail_closed():
    assert "before delete on public.models" in SQL
    assert "before delete on public.calculation_results" in SQL
    assert "old.is_default or old.is_published or old.confirmed" in SQL
    assert "old.is_default or old.is_published" in SQL
    assert "delete_protected_resource" in SQL
    assert "'blocked_protected'" in SQL
    assert "update public.models" not in SQL
    assert "update public.calculation_results" not in SQL


def test_recovery_migration_does_not_weaken_delete_or_storage_boundaries():
    assert "on delete cascade" not in SQL
    assert "delete from storage.objects" not in SQL
    assert "delete from public.models" not in SQL
    assert "delete from public.calculation_results" not in SQL
    assert "storage.remove" not in SQL
