# Live Supabase Staging E2E Evidence

## Safety gate

Remote writes are prohibited until the project owner confirms the exact project
reference is a dedicated non-production staging target.

Read-only discovery on 2026-08-11 found:

| Field | Observed value |
|---|---|
| project name | `pnl_dashboard` |
| project ref | `sarwbkxukyexgioirpaa` |
| region | `ap-southeast-1` |
| project status | `ACTIVE_HEALTHY` |
| PostgreSQL platform version | `17.6.1.147` |
| migration history | none |
| application `public` tables/routines | 0 / 0 |
| existing Storage | one public `mis-dashboard-data` bucket, two objects |
| organization plan | free |

The project name and Management API metadata do not contain a staging label.
Because unrelated Storage data already exists, this is not enough evidence to
classify the target as dedicated staging. `STAGING TARGET SAFETY` remains open.

No migration, queue, bucket, object, table, policy, or data write was performed.

The owner subsequently excluded `sarwbkxukyexgioirpaa` from this goal. It is
not a staging target and remains read-only and untouched.

## PostgreSQL 17 migration-failure evidence

The first dedicated non-production staging project was created solely for the
clean migration trial:

| Field | Observed value |
|---|---|
| project name | `pnl-dashboard-staging` |
| project ref | `vfplhknqovdvsmjbvvax` |
| region | `ap-southeast-1` |
| project status before pause | `ACTIVE_HEALTHY` |
| PostgreSQL platform version | `17.6.1.155` |
| successful migration history | `phase1_foundation_001`, `phase2_queue_worker_002`, `phase2_publication_boundary_003` |
| failed migration | `phase25_analysis_inputs_004` |
| persisted state after failure | Migration 004 transaction rolled back; history remains at 001--003 |
| application artifacts | models 0, jobs 0, results 0, Storage objects 0, queue messages 0 |
| Storage bucket | one empty `pnl-models` bucket created by Migration 001 |

PostgreSQL reported `column reference "name" is ambiguous` while compiling the
Migration 004 `pnl_storage_read_policy`. The policy joined multiple relations
having a `name` column while referring to the outer `storage.objects.name`
without a relation qualifier.

The owner authorized one compatibility-only exception in Migration 004. The
six removed expressions and six replacements qualify only the existing outer
Storage references as `storage.objects.name` and
`storage.objects.bucket_id`. The boolean predicates, joins, roles, RLS intent,
and lifecycle conditions are unchanged. `git diff --check` passes. No other
Migration 001--012 content was changed.

This project is retained as failure evidence and will be paused to free the
Free Plan active-project slot. After pause, it receives no further migration,
Storage, Queue, schema, or data writes.

## Clean staging target

The failure-evidence project reached `INACTIVE` before the replacement project
was created. The active Live E2E target is now:

| Field | Observed value |
|---|---|
| project name | `pnl-dashboard-staging-clean` |
| project ref | `ysatkswhhajicfgbrtpv` |
| region | `ap-southeast-1` |
| project status at safety gate | `ACTIVE_HEALTHY` |
| PostgreSQL platform version | `17.6.1.155` (PostgreSQL 17 GA) |
| initial migration history | empty |
| initial application schema | public tables 0, public routines 0 |
| initial Storage | buckets 0, objects 0 |
| initial Queue state | pgmq not installed |

`STAGING TARGET SAFETY = PASS` was recorded before the first write. Migrations
001 through 012 then applied in order without a failure or manual SQL patch.
The installed extension versions are `pgmq 1.5.1`, `pg_cron 1.6.4`, and
`pgcrypto 1.3`; queue `calculation_jobs` exists.

The post-migration Supabase Security Advisor found one browser-callable
`SECURITY DEFINER` function: trigger implementation
`append_row_audit_log()`. Additive Migration 013 revokes direct EXECUTE from
PUBLIC, anon, and authenticated. Trigger execution continues without exposing
this trigger implementation as a callable browser RPC. The live catalog now
reports anon and authenticated EXECUTE false, and the advisor has no remaining
WARN findings.
The remaining `RLS enabled, no policy` INFO notices are intentional deny-all
boundaries on internal hardening/audit tables; those tables also have no anon
or authenticated DML grants.

The live `pgmq 1.5.1` queue accepted one controlled probe, returned it with
`read_ct=1` under a visibility timeout, and archived it. The probe was then
removed; both live and archive queue counts returned to zero. Browser roles
have no `pgmq` schema USAGE and no queue-table DML grants.

An older temporary workbook outside this branch passed structural preflight,
but its provenance showed that it had been derived from a separate prior
workbook. It is therefore excluded from this goal and was not uploaded. A new
non-business synthetic workbook still needs an approved authoring runtime; the
workspace artifact-tool loader is currently unavailable, and no alternate
spreadsheet library was used to bypass that boundary.

The owner later authorized the repository's existing openpyxl test-fixture
generators for this Live E2E only. A pure infrastructure synthetic pair was
generated by retaining the preflight fixture's existing zero numeric inputs
and overlaying only non-empty text markers/account labels from the existing
analysis fixture. No company workbook was read, no business number was copied,
and no new business formula was introduced. Base and Comparison both pass XLSX
package validation, 2026/12-month preflight, the canonical analysis engine,
all nine effect codes, reconciliation, analysis view, fact pack, and the
seven-block P&L Dashboard mapper. They live only in a workspace sibling
staging-artifact directory and are not part of Git. Each is 8,145 bytes and
has SHA-256
`093e6e87f84e5e44853f6789a1d490a3135a29bf74da711f968b49d3edcad40a`.
The identical hashes intentionally represent a zero-delta transport fixture;
they do not satisfy the distinct Base/Comparison Golden-pair gate and cannot
substantiate an analytical contrast. The generated XLSX package contains no
formula cells, so these checks exercise the canonical zero paths only, not
formula evaluation or nonzero P&L propagation.

The same infrastructure Base lets the existing ForecastEngine finish a one-month
smoke run, but the generated output loses required Golden markers and fails
re-ingestion preflight/analysis. The failed output was deleted. This fixture is
therefore valid for upload and Base/Comparison Analysis infrastructure tests,
but it is not evidence for Forecast-generated-Model analysis, production
Forecast performance, or Golden business correctness. No Engine/business
logic was changed to accommodate the fixture.

Live shared-auth substrate checks created a session through the service-only
RPC, resolved it from a separate request, revoked it, and then observed zero
rows from the original validation path. The controlled session row was removed.
Direct anon and authenticated reads of `bff_sessions` fail with PostgreSQL
`42501`, as do direct calls to `append_row_audit_log()`.

The first distributed-lockout probe exposed a PostgreSQL NULL-contract bug:
an unlocked row returned `allowed = NULL`, which the BFF maps fail-closed to
false. Additive Migration 014 changes only that return expression to
`not coalesce(locked_until > now(), false)`. Live retest now returns true for
failures one and two, false with an authoritative Retry-After at threshold
three, and true after the service-only clear RPC. The probe row was removed.

The private bucket is live with `public=false`, a 50 MiB object limit, and only
the XLSX MIME type. Before mapping publication, the service-role readiness RPC
correctly returned false. The canonical mapping was then created as a draft,
validated, and published as the default with the registry version/hash; the
readiness RPC now returns true.

Live Phase A used two local development BFF processes with separate HTTP
sessions against this same Supabase database. The Base upload through BFF A was
visible through BFF B, and the Comparison upload through BFF B was visible
through BFF A. Both private Storage downloads match the local synthetic bytes
and their persisted Model SHA-256 exactly. Both Models were published; the
Comparison Model was deliberately made the global default through the
Admin+CSRF publication boundary for the canonical Dashboard context.

The first 12-month Analysis enqueue exposed PostgreSQL 17 SQLSTATE `42725`:
`generate_series(smallint, smallint)` was ambiguous in the idempotent enqueue
RPC. Additive Migration 015 redefines that RPC with explicit integer arguments
to `pg_catalog.generate_series` and otherwise preserves its signature,
idempotency, provenance, queue, search-path, and service-role-only contract.
The retry created one pending Job, and an independent Worker claimed and
completed it. Replaying the identical HTTP request returns the same completed
Job with `idempotency_replayed=true`.

Dashboard diagnosis briefly applied Migration 016's older Migration 010
fallback selector. Repository history then confirmed that Migration 011 had
intentionally strengthened the contract to require both a default Result and
a published default Comparison Model. Migration 017 immediately restores that
latest contract. After the canonical Model/Result default publications, Admin
Result, Viewer Result, Admin/Viewer Presentation, Calculation History,
Admin/Viewer Evidence XLSX, and Viewer P&L Dashboard all return successfully.
The pre-publication Viewer Result path returned not-available as required.

The live catalog contains 63 `SECURITY DEFINER` functions. All have an explicit
function search path; anon and authenticated can execute none of them. Public
and pgmq schema CREATE are denied to anon, authenticated, and service_role.
These CREATE/USAGE results are observations of this project's effective live
ACLs, not guarantees inferred solely from the migration text; they must be
rechecked after a clean replay or platform change.

Forecast global-permit checks used three controlled operation IDs with the DB
limit set to one. Acquire succeeded, same-operation replay returned the same
lease token, a competing operation failed with
`FORECAST_CAPACITY_EXHAUSTED`, renewal succeeded, and explicit release admitted
the next operation. A separate 30-second lease was allowed to expire; the next
acquire removed the expired permit and succeeded. Final permit count is zero.

## Current platform evidence

- Supabase CLI was not installed globally. The official package was invoked
  read-only through `npx`; version `2.113.0` reported its command help.
- The clean staging target reports PostgreSQL `17.6` on Linux and platform
  version `17.6.1.155`.
- Clean replay installed `pgmq 1.5.1`, `pg_cron 1.6.4`, and `pgcrypto 1.3`.
- Migration history is sequential from 001 through additive corrections 013
  through 017. Migration 015 is the PostgreSQL 17 Analysis month-series fix;
  Migration 017 restores the intentional Migration 011 Dashboard-default
  contract after the temporary diagnostic Migration 016.
- The post-migration Security Advisor has no WARN finding. Its remaining INFO
  findings are intentional RLS-with-no-policy deny-all internal tables.
- The clean target contains the private `pnl-models` bucket only; it is not
  public and accepts the canonical XLSX MIME type within the 50 MiB limit.

Current Supabase documentation says new Queues use the platform-default `pgmq`
extension and queue tables are not exposed to the Data API unless explicitly
configured. The application migrations create `pgmq` without a version clause
and do not create `pgmq_public`, matching that server-only contract.

## Remaining gates

- A dedicated staging identity is confirmed and its safety gate passed.
- The required clean-project server credential and BFF secrets were present in
  the process environment and used without printing, logging, committing, or
  recording their values. The Supabase URL, repository backend, and direct
  proxy configuration matched the clean staging contract.
- No controlled company workbook is available for upload and 1/6/12-month
  Forecast performance benchmarking.
- Reverse proxy/container/temp-volume topology is not available for Phase B.

## Live Phase A result

The credential-dependent canonical HTTP/Storage lifecycle is complete:

1. two local BFF processes used the same shared DB and observed each other's
   durable Model writes;
2. both approved infrastructure workbooks uploaded through canonical HTTP;
3. independent private Storage downloads matched local and Model SHA-256;
4. mapping/Model/Result publication, Analysis enqueue, independent Worker,
   Result, Viewer, Presentation, History, Evidence, and P&L Dashboard passed.

`BFF_FORECAST_SYNC_APPROVED=false` remained in force, and no Forecast HTTP
request ran. The synthetic pair does not close the company-workbook benchmark,
Forecast-generated-Model gate, or Phase B production proxy/container gate.

## Offline regression after live corrections

- Focused live-schema and affected-contract tests: 42 passed.
- Full Python suite: 298 passed, 18 skipped. The 18 skips retain the existing
  private-Golden-workbook absence reason.
- Python `compileall` over `forecast` and `tests`: passed.
- React/Vitest: 7 files and 22 tests passed.
- Frontend production build: passed (1,813 modules transformed).
- Frontend lint: exit 0 with existing unused-symbol warnings.
- Frontend dependency audit: 0 vulnerabilities reported.
- `git diff --check`: passed; only line-ending notices and inaccessible pytest
  temporary-directory warnings were emitted.

These local checks complement the now-completed credential-dependent Phase A
journey; they do not close the remaining company-workbook or Phase B gates.
