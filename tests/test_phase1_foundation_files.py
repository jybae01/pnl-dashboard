from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "supabase" / "migrations" / "202608090001_phase1_foundation.sql"
EDGE = ROOT / "supabase" / "functions" / "pnl-gateway" / "index.ts"


class Phase1FoundationFileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sql = MIGRATION.read_text(encoding="utf-8").lower()
        cls.edge = EDGE.read_text(encoding="utf-8")

    def test_required_tables_and_job_states_are_declared(self):
        for table in ("models", "calculation_jobs", "calculation_results", "app_config", "audit_logs"):
            self.assertIn(f"create table if not exists public.{table}", self.sql)
        for status in ("pending", "processing", "completed", "failed"):
            self.assertIn(f"'{status}'", self.sql)
        for field in ("heartbeat_at", "attempt", "max_attempts", "error_code", "error_message", "error_detail"):
            self.assertIn(field, self.sql)
        self.assertIn("upload_completed_at", self.sql)

    def test_result_provenance_and_mapping_lifecycle_are_db_fields(self):
        for field in ("engine_version", "mapping_version", "mapping_hash", "result_schema_version"):
            self.assertIn(field, self.sql)
        self.assertIn("draft -> validated", self.sql)
        self.assertIn("validated -> published", self.sql)
        self.assertIn("idx_calc_model_year", self.sql)

    def test_audit_log_is_defended_by_privileges_and_trigger(self):
        self.assertIn("prevent_audit_log_mutation", self.sql)
        self.assertIn("before update or delete or truncate on public.audit_logs", self.sql)
        self.assertIn("revoke update, delete, truncate on table public.audit_logs", self.sql)

    def test_storage_paths_are_bound_to_their_model_and_job_ids(self):
        for guard in (
            "guard_model_storage_binding",
            "guard_job_storage_binding",
            "guard_result_storage_binding",
        ):
            self.assertIn(guard, self.sql)
        self.assertIn("models/%s/source.xlsx", self.sql)
        self.assertIn("models/%s/jobs/%s/result.xlsx", self.sql)
        self.assertIn("new.workbook_bucket is null and new.workbook_path is null", self.sql)
        self.assertIn("if new.workbook_bucket is null", self.sql)

    def test_service_role_writes_use_narrow_rpcs_and_mapping_starts_as_draft(self):
        self.assertIn("guard_app_config_insert", self.sql)
        self.assertIn("mapping config must be created as a draft", self.sql)
        self.assertIn(
            "revoke update, delete, truncate on table public.models, public.calculation_jobs",
            self.sql,
        )
        self.assertIn("grant select on table public.calculation_results to service_role", self.sql)
        self.assertIn("mapping provenance is not published", self.sql)

    def test_claim_complete_and_fail_are_guarded_rpc_contracts(self):
        for function in (
            "claim_calculation_job",
            "heartbeat_calculation_job",
            "complete_calculation_job",
            "fail_calculation_job",
            "initialize_calculation_upload",
            "mark_calculation_upload_completed",
            "expire_stale_calculation_jobs",
        ):
            self.assertIn(f"function public.{function}", self.sql)
        self.assertIn("for update skip locked", self.sql)

    def test_edge_is_signed_upload_gateway_without_excel_calculation(self):
        self.assertIn("createSignedUploadUrl", self.edge)
        self.assertIn("initialize_calculation_upload", self.edge)
        # Phase 2 hardens the runtime boundary: workers consume pgmq through
        # service-role-only database RPCs, never through the Edge gateway.
        self.assertNotIn("claim_calculation_job", self.edge)
        self.assertNotIn("complete_calculation_job", self.edge)
        for forbidden in ("openpyxl", "pandas", "ForecastEngine", "Decimal"):
            self.assertNotIn(forbidden, self.edge)


if __name__ == "__main__":
    unittest.main()
