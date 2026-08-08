# Phase 1: Supabase foundation

## Runtime boundary

```text
Streamlit --JWT--> Edge gateway --signed token--> private Storage
                           |
                           +--> models + pending calculation_jobs

independent Python worker --claim/heartbeat/complete/fail RPCs--> Postgres
                           |
                           +--> existing deterministic engine (Phase 2 wiring)

Streamlit/viewers <-- completed calculation_results JSONB
```

The Edge Function is a security/control gateway. It never receives workbook
bytes and contains no calculation logic. The Python `WorkerJobControl` is only
the lifecycle interface; it does not start a thread, task, poll loop or engine.

## Tables

- `models`: immutable workbook object reference and compatibility metadata.
  `confirmed` remains writable during migration and is synchronized with
  `is_published`. A partial unique index permits only one `is_default` model.
- `calculation_jobs`: `pending -> processing -> completed|failed`, with worker
  claim token, heartbeat/lease, attempt/max-attempt and structured error fields.
  `expire_stale_calculation_jobs` prepares the one-hour abandoned-upload and
  exhausted-lease cleanup transition; scheduling it belongs to deployment.
- `calculation_results`: JSONB Fact Pack plus `engine_version`,
  `mapping_version`, `mapping_hash` and `result_schema_version` captured from
  the claimed job. Completion is atomic with the terminal job update.
- `app_config`: versioned config content with only
  `draft -> validated -> published` transitions and one published default per
  config key. `model_mapping` is the initial key.
- `audit_logs`: row-change audit for the four mutable tables. UPDATE, DELETE and
  TRUNCATE are revoked and also rejected by an append-only trigger.

## Storage

The private `pnl-models` bucket accepts the canonical paths documented in
`supabase/storage/README.md`. The upload initializer generates UUIDs and the
object path itself, creates a non-upsert signed URL, then calls one DB RPC that
atomically inserts the model and pending job. The original user filename is
stored only as metadata.

## Repository migration

`ModelRegistry` and `ResultStore` remain unchanged entry points for existing
callers, with additive compatibility fields/methods. Streamlit uses
`LocalModelRepositoryAdapter` and `LocalResultRepositoryAdapter`; no existing
local data is deleted. `create_repository_bundle(..., backend="supabase")`
provides the DB/Storage adapters for Phase 2. The default backend is explicitly
`local`, even if Supabase secrets happen to exist.

## Mapping and result provenance

`config/mapping_registry.json` records the current published mapping version
and canonical SHA-256 hash. New versions are created as drafts, validated, and
then published; a published version cannot move backward. A worker must return
the exact provenance captured when it claimed the job or completion fails.

## Deployment order

1. Review and apply `202608090001_phase1_foundation.sql` to a non-production
   Supabase project.
2. Insert the current `config/model_mapping.json` as an `app_config` draft,
   validate it, then publish it as the default `model_mapping` version.
3. Configure the Edge secrets listed in its README and deploy `pnl-gateway`.
4. Exercise signed upload and status reads with a test administrator JWT.
5. Do not enable `PNL_REPOSITORY_BACKEND=supabase` for the Streamlit app until
   the Phase 2 worker executor and upload UI integration are deployed.
