from pathlib import Path


MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "supabase/migrations/20260815055055_persistent_delete_storage_requirement_slice3a.sql"
)
SQL = MIGRATION.read_text(encoding="utf-8").lower()


def test_storage_requirement_is_receipt_anchored_and_serialized_with_prepare():
    assert "persistent_delete_storage_required" in SQL
    assert "pg_advisory_xact_lock" in SQL
    assert "'persistent-delete:' || p_resource_type" in SQL
    assert "from public.persistent_delete_receipts" in SQL
    assert "receipt.storage_path is not null" in SQL
    assert "persistent delete receipt not found" in SQL


def test_storage_requirement_rpc_is_service_role_only():
    signature = "public.persistent_delete_storage_required(text, uuid)"
    assert f"revoke all on function {signature}" in SQL
    assert f"grant execute on function {signature}" in SQL
    assert "to service_role" in SQL
    assert "to authenticated" not in SQL
    assert "security definer" in SQL
    assert "set search_path = ''" in SQL
    assert "delete from storage.objects" not in SQL
