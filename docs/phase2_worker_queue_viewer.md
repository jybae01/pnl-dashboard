# Phase 2: durable worker and completed-result viewer

## Runtime boundary

1. Edge authenticates an administrator, creates model/job metadata and returns
   a non-upsert signed URL. Excel bytes go directly to private Storage.
2. The upload callback verifies the canonical object and atomically sends one
   `calculation_jobs` message to the private basic pgmq queue.
3. `python -m forecast.worker_cli --backend supabase` runs outside Streamlit.
   It uses `read` with a visibility timeout, renews both the job lease and pgmq
   VT, forces Excel pre-flight/Anchor validation, then calls the unchanged
   deterministic comparison engine.
4. Completion commits JSONB/provenance and archives the queue message in one
   transaction. Retryable failure uses `set_vt(..., 0)`; terminal failure is
   archived. `pop` is never used.
5. The Viewer reads only a published row created by a completed job and renders
   its stored `analysis_view`. It does not open Excel or rebuild effects.

The worker stores `engine_version`, `mapping_version`, `mapping_hash` and
`result_schema_version` from the claim. It also stores backend-produced
`fx_total`, `raw_material_excl_fx`, product Mix, a Fact Pack and both pre-flight
reports.

## Deployment

1. Apply `202608090002_phase2_queue_worker.sql` after the Phase 1 migration.
   It enables `pgmq` and `pg_cron`, creates the durable queue, replaces guarded
   lifecycle RPCs and schedules five-minute stale-job cleanup.
2. Keep `pgmq_public` out of exposed schemas. Worker credentials are service
   role secrets and must never be placed in Streamlit/browser code.
3. Deploy `pnl-gateway` with the secrets in its README.
4. Run at least one independent worker process with `SUPABASE_URL` and
   `SUPABASE_SERVICE_ROLE_KEY` set.
5. Exercise the deployed pipeline with `SignedUploadE2EHarness`; real Supabase
   migration, Cron, Storage and Edge execution cannot be validated offline.
