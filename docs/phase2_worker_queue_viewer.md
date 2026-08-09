# Phase 2: trusted Streamlit bridge, durable worker, and completed-result viewer

## V1 runtime boundary

The V1 operating path is Option A. The browser submits the existing Viewer/Admin
access code only to the trusted Streamlit server. No Supabase login screen, API
key, service-role credential, Storage credential, or signed-upload token is sent
to browser JavaScript or stored in the user session.

1. The Streamlit server rechecks the Admin role, calls the narrow model/job init
   RPC, uploads Excel bytes server-side to the returned canonical private Storage
   path, and calls the upload-completed RPC. These DB and Storage operations form
   a saga, not one transaction: pending-job TTL cleanup, idempotent retry, and
   orphan-object cleanup are required.
2. The upload callback verifies the canonical object and atomically enqueues one
   `calculation_jobs` message in the private basic pgmq queue.
3. `python -m forecast.worker_cli --backend supabase` runs independently from
   Streamlit. It reads with a visibility timeout, renews the job lease and pgmq
   VT, runs Excel preflight/Anchor validation, and invokes the unchanged
   deterministic comparison engine.
4. Completion stores immutable JSONB/provenance and archives the queue message in
   one transaction. It always creates an unpublished, non-default result.
   Publication/default selection is a separate Admin-only RPC; worker completion
   never honors `analysis_request.publish` or `make_default` as authorization.
5. A Viewer reads only a published completed result whose model/job provenance
   and mapping version/hash match published `app_config`, then renders the stored
   `analysis_view`. It never opens Excel or rebuilds effects.

Migration `202608090003_phase2_publication_boundary.sql` keeps the two legacy
completion booleans only for upgrade ABI compatibility and ignores their values;
the insert is hard-coded to `false/false/null`. The separate
`set_calculation_result_publication` RPC checks completed status, job/model
binding, and published mapping provenance, serializes default changes, and can
update publication metadata only. Execution is revoked from public/anon/
authenticated and granted server-side only. `AdminResultPublicationGateway`
rechecks the Streamlit Admin capability on every call because a Supabase secret
key itself bypasses RLS.

The worker stores `engine_version`, `mapping_version`, `mapping_hash`,
`result_schema_version`, backend-produced `fx_total`,
`raw_material_excl_fx`, product-group-only Mix, a Fact Pack, and both preflight
reports. SKU-internal variance is not a V1 Mix effect and remains a residual
analysis item.

Fixed calculation contracts are:

- `residual = operating_profit_delta - effects_total`
- `effects_total + residual = operating_profit_delta`
- `inventory_realization_rate = COGS / current_period_manufacturing_input`
  without a cap; values above 100% may produce a warning only.

## Optional future JWT Edge path

The existing JWT Edge gateway and signed-upload flow are optional only if a
future Supabase Auth client is introduced. They are not the V1 Streamlit upload
or authorization path. No worker claim/complete/fail execution endpoint is
reintroduced at Edge.

## Deployment readiness

1. Apply `202608090002_phase2_queue_worker.sql` only after the Phase 1 migration.
   It enables `pgmq`/`pg_cron`, creates the durable queue, installs narrow guarded
   lifecycle RPCs, and schedules stale-job cleanup.
2. Keep `pgmq_public` out of exposed schemas. Streamlit and the worker each use a
   server-only Supabase secret (`SUPABASE_SECRET_KEY`, with legacy
   `SUPABASE_SERVICE_ROLE_KEY` as compatibility fallback). Separate keys improve
   rotation and auditability but do not create database privilege isolation;
   secret keys bypass RLS.
3. Deploy `pnl-gateway` only if the optional JWT client path is retained.
4. Run at least one independent worker with server-only credentials.
5. Validate Option A with a Streamlit-backend upload/auth-bridge live harness.
   `SignedUploadE2EHarness` validates only the optional Edge path.

No live deployment or credential connection is part of this phase.
