# Slice 3 — Supabase Persistent Delete Contract

Baseline: `f83ce3175dd3db430ee820471e8e4c9afc1bfd48`.

## Ownership graph

| Parent | Child/reference | Actual FK / delete behavior | Ownership | Delete policy |
|---|---|---|---|---|
| `models.id` | `calculation_jobs.model_id`, `baseline_model_id`, `comparison_model_id` | `ON DELETE RESTRICT` | Shared analysis input | Any row blocks Model delete |
| `models.id` | `calculation_results.model_id`, `baseline_model_id`, `comparison_model_id` | `ON DELETE RESTRICT` | Shared result provenance | Any row blocks Model delete |
| `models.id` | `forecast_generation_requests.base_model_id` | `ON DELETE RESTRICT` | Shared Forecast source | Any row blocks Model delete |
| `models.id` | `models.source_model_id` | `ON DELETE RESTRICT` | Generated Model provenance | Any derived Model blocks source delete |
| `forecast_generation_requests.id` | `models.forecast_generation_id` | `ON DELETE RESTRICT` | Generated Model creation metadata | Deleted only with its generated Model after status/link validation |
| Model UUID | `model_ingestion_requests.model_id` | No FK; UUID is unique | Uploaded Model creation metadata | Completed row is deleted with Model; other states block |
| Model UUID | `forecast_generation_requests.model_id` | No FK; UUID is unique | Generated Model creation metadata | Completed matching row is deleted with Model; other states block |
| Model | `storage.objects` private source | No FK; bucket `pnl-models`, key `models/<model_id>/source.xlsx` | Model-owned | Storage API deletion after DB preflight/delete |
| `calculation_jobs.id` | `calculation_results.job_id` | Unique, `ON DELETE RESTRICT` | Analysis-owned | Result is deleted before terminal Job |
| Analysis Job | optional result workbook | No FK; `models/<comparison_model_id>/jobs/<job_id>/result.xlsx` | Analysis-owned | Storage API deletion; Models are preserved |
| Analysis Job | `pgmq.a_calculation_jobs.msg_id` | No FK | Analysis-owned archived queue metadata | Removed only after `queue_archived_at` proves settlement |
| Any domain row | `audit_logs`, `bff_audit_events` | Generic immutable audit identity | Shared audit trail | Always retained |

There is no standalone analysis-history table. The Admin history function joins
`calculation_jobs`, its optional unique `calculation_results` row, and the two
shared Models. The delete identifier is therefore `job_id`, including failed
jobs that have no `result_id`. There are no persistent evidence/export tables;
Evidence is generated from the result workbook. The optional result workbook is
the analysis-owned evidence/export artifact.

## Backend and authorization boundary

React sends only UUID lists to the Admin BFF:

- `POST /api/admin/models/delete`
- `POST /api/admin/calculation-history/delete`
- `GET /api/admin/models/delete/recovery`
- `POST /api/admin/models/delete/retry`
- `GET /api/admin/calculation-history/delete/recovery`
- `POST /api/admin/calculation-history/delete/retry`

Both routes require the existing Admin session and CSRF guard. The trusted BFF
uses the server-only Supabase 2.31.0 client/service credential. No privileged
credential, bucket, object path, table name, or delete policy is exposed to the
browser. RLS remains enabled; direct table access remains revoked. The new RPCs
are `SECURITY DEFINER`, have `search_path=''`, and are executable only by
`service_role`.

## Model delete policy

`prepare_model_persistent_delete` takes an advisory lock and Model row lock,
validates the exact canonical source path, locks creation-saga metadata, and
counts every actual analysis/result/baseline/comparison/Forecast/derived-model
reference. A reference or non-completed creation saga returns
`BLOCKED_IN_USE`/`MODEL_IN_USE`; no DB or Storage object is deleted. Otherwise
the transaction records a durable receipt, deletes the Model, and deletes only
its completed creation metadata. It never cascades to analysis or another
Model.

Models with `is_default`, `is_published`, or the synchronized legacy
`confirmed` flag remain protected. The database trigger blocks physical delete
without mutating publication state; the BFF reports
`BLOCKED_PROTECTED`/`DELETE_PROTECTED_RESOURCE`.

## Analysis-history delete policy

Only authoritative terminal states `completed` and `failed` are eligible.
`pending` and `processing` return `BLOCKED_NON_TERMINAL`; an unsettled queue or
invalid Job/Result shape fails closed. The transaction captures the canonical
result artifact, deletes the optional owned Result, removes the settled archived
queue row, and deletes the Job. Baseline, comparison, source, and generated
Models are never deleted.
Results with `is_default` or `is_published` are protected by the same fail-closed
policy. Users must use the existing publication workflow first.

## DB/Storage sequencing, partial failure, and retry

Supabase Database and Storage do not share a transaction. The implementation:

1. captures and validates the authoritative DB path and references;
2. writes `persistent_delete_receipts` and performs ordered DB hard deletion in
   one RPC transaction;
3. calls Storage `remove([exact_object_key])` from the trusted server;
4. lists the canonical parent with exact-name search, validates and paginates
   the response, and requires exact-object absence;
5. marks the durable receipt complete.

A Storage or verification failure returns `CLEANUP_REQUIRED` with
`DB_DELETED_STORAGE_CLEANUP_REQUIRED`. If prepare transport or response parsing
fails, the BFF serializes with the original advisory lock and queries the
authoritative receipt. A pending receipt resumes cleanup; a complete receipt is
an idempotent success; an authoritative existing domain row means the prepare
did not commit. If receipt lookup is unavailable, the item is
`PREPARE_UNCERTAIN`, never a permanent prepare failure.

The recovery GET endpoints list at most 100 incomplete receipts by resource
type without returning bucket/path/owner data. This makes reload recovery
possible without a manually discovered receipt ID. The retry POST reads only
receipt provenance and never repeats domain delete. An already completed
receipt returns `DELETED`/`ALREADY_DELETED`; an unknown ID on the normal delete
path returns `NOT_FOUND`. There is no new background queue or Worker
cancellation architecture in this Slice.

## Batch and UI behavior

The maximum batch is 100 unique UUIDs. Every item is processed independently;
the response reports requested/deleted/cleanup-required/blocked/uncertain/failed counts plus per-item
status, reason, safe reference counts, and replay state. Both active Admin views
reuse their existing tables, add checkbox selection and an irreversible-delete
confirmation, show partial results, and refetch the authoritative server list.

## Migration and security notes

Migrations `20260815023857_persistent_delete_slice3.sql`,
`20260815050758_persistent_delete_recovery_slice3a.sql`, and
`20260815053855_persistent_delete_status_classification_slice3a.sql`, and
`20260815055055_persistent_delete_storage_requirement_slice3a.sql` are
additive. They add no
`CASCADE`, blanket RLS policy, public privileged RPC, or browser Storage write.
Delete events reuse the immutable row audit plus BFF operation audit with actor,
session reference, correlation ID, resource type/ID, outcome, and error code.
The audit tables and shared configuration/mapping resources are never deleted.

## Staging acceptance (2026-08-15)

All four persistent-delete migrations were applied to the active
`pnl-dashboard-staging-clean` project, whose remote history now contains all 22
repository migrations. The original rollback-only synthetic SQL smoke proved:

- a Model with a synthetic analysis Job returns `BLOCKED_IN_USE` and remains;
- deleting a synthetic terminal failed Job removes only that Job;
- both synthetic source Models remain after history deletion;
- after the reference is removed, the comparison Model becomes eligible;
- rollback restored the original 15 Models, 15 Jobs, and zero receipts.

Catalog acceptance confirmed RLS enabled; no direct receipt-table delete for
`authenticated` or `service_role`; no delete-RPC execute for `authenticated`;
all privileged persistent-delete RPCs are `SECURITY DEFINER` with empty search path and are
executable by `service_role` only. Security Advisor reported only the intended
INFO notice for RLS-with-no-policy on the server-only receipt table, consistent
with the existing server-private tables.

Slice 3A rollback-only checks additionally confirmed that default and published
Models and Results return `BLOCKED_PROTECTED`, leave the original rows intact,
and that both recovery RPCs remain service-role-only. The database returned to
15 Models, 15 Jobs, and zero receipts after the checks.
The final status-classification migration also preserved that row count and ACL,
returned `BLOCKED_PROTECTED` for the staging default Model, and made recovery
lookup mirror prepare locks and blocked/integrity classifications.

The connected management interface cannot upload/delete a Storage test object
and no server secret exists in the local environment. Therefore a real private
object before/after smoke remains `Supabase Storage Acceptance Pending`; no
production or pre-existing staging object was used as test data. Repository
tests cover SDK `remove([path])`, exact-object absence verification,
cross-object preservation, cleanup failure, uncertain prepare recovery, reload
status discovery, protected publication state, and receipt-only retry.
