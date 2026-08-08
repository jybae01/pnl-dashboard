from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SQL = (ROOT / "supabase/migrations/202608090002_phase2_queue_worker.sql").read_text(
    encoding="utf-8"
)
EDGE = (ROOT / "supabase/functions/pnl-gateway/index.ts").read_text(encoding="utf-8")


def test_pgmq_is_private_durable_pull_with_explicit_settlement():
    lowered = SQL.lower()
    assert "create extension if not exists pgmq" in lowered
    assert "pgmq.read('calculation_jobs'" in lowered
    assert "pgmq.set_vt" in lowered
    assert "pgmq.archive" in lowered
    assert "pgmq.pop" not in lowered
    assert "pgmq_public." not in lowered
    assert "revoke usage on schema pgmq from anon, authenticated" in lowered


def test_uploaded_callback_is_idempotently_enqueued_once():
    assert "if v_job.queue_message_id is not null" in SQL
    assert "return v_job.queue_message_id" in SQL
    assert "perform public.enqueue_calculation_job(v_job.id)" in SQL
    assert "if v_job.upload_completed_at is null" in SQL
    assert "if v_job.queue_message_id is null" in SQL


def test_queue_security_cron_and_poison_message_guards_are_present():
    lowered = SQL.lower()
    assert "create extension if not exists pg_cron" in lowered
    assert "pnl-stale-job-cleanup" in lowered
    assert "new.analysis_request" in lowered
    assert "new.queue_name" in lowered
    assert "any mismatched/orphan receipt is poisoned" in lowered
    assert "grant select on table public.models" in lowered
    assert "to authenticated" in lowered


def test_edge_is_upload_status_gateway_not_worker_or_calculation_runtime():
    assert "p_analysis_request" in EDGE
    assert "baselineModelId" in EDGE
    assert "queueMessageId" in EDGE
    assert "/jobs/claim" not in EDGE
    assert "WORKER_GATEWAY_TOKEN" not in EDGE
    assert "complete_calculation_job" not in EDGE
    assert "pandas" not in EDGE.lower()
