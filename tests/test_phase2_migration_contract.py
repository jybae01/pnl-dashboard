from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SQL = (ROOT / "supabase" / "migrations" / "202608090002_phase2_queue_worker.sql").read_text(
    encoding="utf-8"
).lower()
EDGE = (ROOT / "supabase" / "functions" / "pnl-gateway" / "index.ts").read_text(
    encoding="utf-8"
)


def test_queue_is_durable_and_never_uses_pop():
    for operation in ("pgmq.read", "pgmq.set_vt", "pgmq.archive"):
        assert operation in SQL
    assert "pgmq.pop" not in SQL
    assert "create extension if not exists pg_cron" in SQL
    assert "cron.schedule" in SQL


def test_queue_rpcs_are_service_role_only_and_request_is_immutable():
    assert "new.analysis_request" in SQL
    assert "revoke all on function public.claim_calculation_job" in SQL
    assert "grant execute on function public.claim_calculation_job" in SQL
    assert "to service_role" in SQL


def test_phase1_provenance_and_viewer_boundaries_survive_phase2_redefinition():
    assert "mapping provenance is not published" in SQL
    assert "job.status = 'completed'" in SQL
    assert "is_published and exists" in SQL
    assert "revoke insert, update, delete, truncate on table public.calculation_results" in SQL


def test_edge_is_upload_and_status_gateway_not_worker_executor():
    assert "createSignedUploadUrl" in EDGE
    assert "p_analysis_request" in EDGE
    assert "claim_calculation_job" not in EDGE
    assert "openpyxl" not in EDGE
    assert "pandas" not in EDGE
