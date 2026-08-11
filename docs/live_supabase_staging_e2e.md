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
- The initial empty-project application through Migration 012 installed
  `pgmq 1.5.1`, `pg_cron 1.6.4`, and `pgcrypto 1.3`. This is not a substitute
  for the still-blocked final disposable 001--017 replay.
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
- Full Python suite: 298 passed, 18 skipped. Fifteen retain the existing
  private-Golden-workbook absence reason and three retain the existing missing
  Golden structural-fixture reason.
- Python `compileall` over `forecast` and `tests`: passed.
- React/Vitest: 7 files and 22 tests passed.
- Frontend production build: passed (1,813 modules transformed).
- Frontend lint: exit 0 with existing unused-symbol warnings.
- Frontend dependency audit: 0 vulnerabilities reported.
- `git diff --check`: passed; only line-ending notices and inaccessible pytest
  temporary-directory warnings were emitted.

These local checks complement the now-completed credential-dependent Phase A
journey; they do not close the remaining company-workbook or Phase B gates.

## Release integration verification (2026-08-12)

### Repository baseline and protection

The release verification started by running the required repository commands.
The observed branch was `agent/live-supabase-staging-e2e` and the starting HEAD
was `6df05d2d87769b8e520aebc069bf2468d52f423e`. The dirty worktree contained the
completed but uncommitted Phase A migrations, tests, and this evidence file; it
was reviewed without reset or rebase. Migration-focused pre-commit regression
was 34 passed, and the reviewed Phase A change was fixed on the same branch as
commit `118d4272b002319dcf4fdf71250eb57a03c282a3`. No push was performed.

`.codex/` is now explicitly ignored. No `.codex` file, secret configuration,
XLSX, log, or temporary file was staged. Two ignored synthetic download-cache
XLSX files and four stale pytest temporary directories were removed by exact,
repository-bounded paths after their location was verified. The remote staging
objects that support the completed Phase A lifecycle were not removed.

### Gate 0: disposable clean replay

The final 001--017 sequence has **not** been replayed into a newly empty,
disposable database during this release-verification run:

- the repository has no disposable migration harness or `supabase/config.toml`;
- Docker, Podman, `psql`, `pg_ctl`, and a global Supabase CLI are unavailable;
- the accessible project inventory contains the excluded non-staging project,
  the successful clean staging target, and the retained inactive 001--003
  failure-evidence project; none is an already-approved disposable target;
- the Supabase development-branch listing operation did not return a usable
  branch, and no paid branch/project was created;
- `ysatkswhhajicfgbrtpv` was not reset or otherwise used destructively.

Static SQL equality, migration tests, and final live-catalog checks below are
strong incremental/final-state evidence, but they do not replace an empty-DB
replay. Therefore:

`MIGRATION 001->017 CLEAN REPRODUCIBILITY = BLOCKED_NO_DISPOSABLE_CLEAN_DB`

### Migration 001--017 inventory

| No. | Purpose and dependency | Main objects / policy change | SECURITY DEFINER | Expected caller |
|---|---|---|---:|---|
| 001 | Phase 1 foundation; Supabase Auth/Storage substrate | `models`, jobs, results, config, audit; lifecycle guards/RPCs; core RLS and private `pnl-models` policy | 12 | service-role lifecycle; narrowly authenticated legacy reads |
| 002 | Durable queue/Worker; depends on 001 and `pgmq`/`pg_cron` | queue metadata, enqueue/claim/heartbeat/settle/complete/fail/expiry; read policies hardened | 9 | independent service-role Worker |
| 003 | Publication boundary; depends on 002 | completed-result write/publication/read RPCs; Result/Storage read policy | 3 | service-role publisher and Viewer gateway |
| 004 | Pinned Base/Comparison provenance; depends on 003 | model/job/result SHA and IDs, immutable guards, durable-job RPCs, RLS/Storage policy | 6 | service-role BFF/Worker; constrained authenticated policy path |
| 005 | Trusted BFF foundation; depends on 004 | actor-scoped idempotency, submit/status/admin/viewer-by-ID RPCs | 5 | service-role BFF only |
| 006 | React published-input boundary; depends on 005 | job-insert publication trigger/guard | 1 | internal trigger; service-role submit path |
| 007 | Model ingestion/publication saga; depends on 001/005/006 | ingestion request table, reserve/finalize/fail/recover/cleanup/publication RPCs | 7 | service-role BFF only |
| 008 | Evidence and history; depends on stored Result contract | admin/viewer evidence and bounded history RPCs | 3 | service-role BFF only |
| 009 | Analysis presentation; depends on stored Result contract | admin/viewer presentation RPCs | 2 | service-role BFF only |
| 010 | P&L Dashboard snapshot reader; depends on 009 | `get_pnl_dashboard_viewer`, initially availability/latest ordered | 1 | service-role BFF only |
| 011 | Forecast orchestration and canonical Dashboard default; depends on 007/010 | forecast request saga RPCs, generated-model linkage, strict default Dashboard selector | 7 | service-role BFF only |
| 012 | Production hardening; depends on all vertical slices | shared sessions, distributed lockout, audit, Forecast permits, readiness, cleanup/lease guards; broad privilege revocation | 25 | service-role BFF/maintenance; internal triggers |
| 013 | Live advisor correction; depends on 012 | revokes browser/PUBLIC EXECUTE from `append_row_audit_log()` | 0 | trigger only |
| 014 | Live distributed-lockout NULL correction; depends on 012 | redefines `record_bff_login_failure`; no new object/policy/grant | 1 | existing service-role BFF grant |
| 015 | PostgreSQL 17 month-series correction; depends on 005 | redefines idempotent durable-job RPC and reasserts service-role-only grant | 1 | service-role BFF only |
| 016 | Live diagnostic Dashboard alignment; depends on 010/015 | redefines only the existing Dashboard RPC to the Migration 010 selector | 1 | service-role BFF only |
| 017 | Canonical default-contract restoration; depends on 011/016 | redefines only the same Dashboard RPC and reasserts service-role-only grant | 1 | service-role BFF only |

Migrations 013--017 are the additive live-validation corrections. Migration
016 creates no table, policy, trigger, grant target, or additional function;
017 replaces the same single function body. The final catalog contains exactly
one `get_pnl_dashboard_viewer(text[])` function.

### Migration 004 approved exception

The entire tracked delta to Migration 004 is exactly six PostgreSQL 17
qualification replacements: three `bucket_id` references become
`storage.objects.bucket_id`, and three `name` references become
`storage.objects.name`. No predicate, relation, join, role, policy name,
lifecycle RPC, provenance column, Model/Job/Result state transition, or business
schema meaning changed. Focused tests assert both the count and the surrounding
Storage/RLS relationships. This compatibility exception is not treated as
general permission to mutate Migration 004.

### Migration 015 PostgreSQL 17 semantics

The failing call was the unqualified
`generate_series(p_start_month, p_end_month)` where both parameters are
`smallint`. On live PostgreSQL 17 it failed with SQLSTATE `42725` because no
unique overload could be selected. Migration 015 changes only executable code
for that expression to
`pg_catalog.generate_series(p_start_month::integer, p_end_month::integer)`;
after comments are removed, the recreated function equals Migration 005 with
only that replacement. Signature, validation, fingerprint, pinned provenance,
advisory locking, insertion, enqueue, search path, and grants are unchanged.

Live boundary queries confirmed integer series `[1]`, `[6]`, `[12]`, and the
ordered full-year `[1..12]`. This is semantically equivalent for the already
validated month domain 1--12 and removes the PostgreSQL 17 overload ambiguity.

### Migration 016/017 and final Dashboard contract

Normalized function-body comparison proves Migration 016 is byte-for-byte
equivalent to Migration 010 after whitespace normalization, while Migration
017 is equivalently identical to Migration 011. Migration 016 temporarily
selected any available snapshot ordered by Result default/latest. Migration
017 restores the canonical final rule:

`published default Result + published global default Comparison Model`, else
`EMPTY`.

The live function contains both `available.is_default` and the published/default
Comparison Model existence check and does not contain the Migration 010 latest
fallback ordering. The live default Result joins to one published/default
Comparison Model. The Python mapper calls only this RPC and validates the stored
snapshot; the active React route does no default inference.

### Release feature inventory

| Capability | Primary implementation evidence | Regression evidence |
|---|---|---|
| BFF foundation and Auth | `forecast/bff/http.py`, `application.py`, `auth.py`, `gateway.py` | BFF/Auth/application/HTTP/gateway suites |
| React login and core flow | `frontend/src/App.tsx`, `integration/LoginView.tsx`, `CoreAnalysisView.tsx`, `client.ts` | Login/Core vertical-slice Vitest |
| Model ingestion/publication | `forecast/bff/model_ingestion.py`, ingestion gateway, Migration 007 | ingestion Python/HTTP/migration and React tests |
| Analysis submit and polling | BFF application/HTTP/gateway plus `CoreAnalysisView` polling | BFF and Core vertical-slice tests |
| pgmq and independent Worker | Migrations 002/004, `forecast/worker_cli.py`, `worker_runtime.py`, Supabase persistence | queue/lease/runtime/input-integrity tests |
| Result persistence/publication | completion/publication RPCs in 003/004 | publication/worker/viewer tests |
| Presentation | `forecast/bff/analysis_presentation.py` | Python and React presentation tests |
| Calculation History/Evidence | `forecast/bff/evidence_history.py` | Python and React evidence/history tests |
| P&L Dashboard | `forecast/presentation/pnl_dashboard.py`, `forecast/bff/pnl_dashboard.py` | Python and React Dashboard tests |
| Forecast | `forecast/engine.py`, `forecast/bff/forecast_orchestration.py` | offline Forecast/orchestration and React tests |
| Production hardening | `forecast/bff/production.py`, `http_factory.py`, Migration 012 | production-hardening/Auth/BFF tests |
| Live compatibility/security | approved 004 exception and additive 013--017 | live migration tests plus catalog/advisor checks |

The active `App.tsx` routes use the BFF integration client. Older mock services
and prototype views remain in the source tree but are not imported by the
release route; they are not evidence and do not perform the active business
calculation.

### Business, effect, Viewer, and Worker regression

The canonical engine and presentation tests reconfirm:

- LC means 4-inch LC; FS uses LENGTH/metres and all other finished goods use
  PCS. PCS and LENGTH denominators are never summed;
- Delta is Comparison minus Base and positive means operating-profit
  improvement;
- `effects_total + residual = operating_profit_delta`; residual remains a
  separately classified value and is never fabricated as a plug;
- JPY is KRW/JPY with no `/100` conversion;
- customer freight is included exactly once, tariff is a separate effect,
  same-product-group SKU composition is distinct from V1 Mix, and MCM does not
  create a separate generic raw-material effect;
- the canonical presentation order is Quantity, Mix, Price, Sales FX,
  Material, Manufacturing, Variable SG&A, Fixed SG&A, Tariff, then Residual;
- `manufacturing_realized` already includes variable and fixed manufacturing
  occurrence after inventory realization, so no separate Fixed Manufacturing
  effect is introduced.

Admin/Viewer presentation and Dashboard paths map stored Result payloads only.
Evidence writes a bounded workbook from the stored Result and pinned provenance;
it does not reopen source Excel or rerun an evaluator/engine. The Supabase
Worker CLI is independent of Streamlit, claims pgmq work with a visibility
lease/heartbeat/retry contract, and uses pinned Base/Comparison IDs, workbook
SHA values, mapping hash, and result schema. Its `get_default()` reference is
reachable only in an explicitly enabled local legacy compatibility branch;
the Supabase CLI sets that flag false and durable jobs always take the pinned
branch. Result rows are inserted atomically only by completion RPCs; live
catalog checks found zero Results attached to non-completed Jobs.

### Live evidence consistency and security final review

The live migration history contains 17 sequential records through 017. Current
catalog/advisor results are:

| Check | Result |
|---|---|
| Security Advisor WARN/ERROR | 0 / 0 |
| public application tables without RLS | 0 |
| SECURITY DEFINER without fixed search path | 0 |
| anon/authenticated SECURITY DEFINER EXECUTE | 0 / 0 |
| browser grants/policies on internal session/lockout/audit/permit tables | 0 / 0 |
| direct browser audit-trigger EXECUTE | 0 |
| private `pnl-models` bucket | PASS |
| pgmq queue present / visible messages after journey | 1 / 0 |
| active Forecast permits | 0 |
| strict Dashboard pair | 1 |
| Result attached to non-completed Job | 0 |
| row-audit evidence present | PASS |
| BFF readiness function and published mapping readiness | PASS |

The Security Advisor retains intentional INFO-only deny-all RLS notices. The
Performance Advisor separately retains one known `auth_rls_initplan` WARN on
the Result read policy plus INFO notices; it is not represented as a Security
Advisor warning. Phase A BFF logs contain successful `/health/live` requests
for both replicas and correlation IDs for the HTTP journey. The live readiness
RPC passed after mapping publication. Audit rows exist, while controlled BFF
session/lockout/permit rows were cleaned up. This consolidates staging safety,
migration history, RLS/ACL/SECURITY DEFINER, private Storage, shared sessions,
distributed lockout, pgmq, Forecast permits, BFF A/B, exact SHA and model/
mapping publication, Analysis/idempotency/Worker/Result, Viewer/Presentation/
History/Evidence/Dashboard, audit, correlation, health, and readiness evidence.

### Synthetic fixture boundary and secret/artifact hygiene

The identical synthetic pair remains a pure non-business, zero-delta,
no-formula infrastructure fixture. It supports upload/preflight/Storage/SHA,
Model/Job/queue/Worker/Result lifecycle, Viewer/Presentation/History/Evidence,
and Dashboard transport only. It is not evidence for Golden business
correctness, nonzero effects, Forecast correctness/performance, or real company
product/mix behavior, and is not promoted to a Golden pair.

Configuration validation checked only presence and contract results: the
Supabase URL matched `ysatkswhhajicfgbrtpv`, a service credential slot and all
required BFF secret slots were present, the repository backend was Supabase,
and `BFF_FORECAST_SYNC_APPROVED` was false. No value was reported. Exact-value
comparison of the configured credential slots against tracked files, current
diff, frontend source/build, and logs found zero matches. Pattern scanning found
zero secrets in the current diff, frontend source/build, or logs; the remaining
tracked high-risk-looking literals are confined to the example secret template
and test fixtures and match none of the configured values. Git tracks zero
`.codex` files and zero XLSX files; the repository currently contains zero
local XLSX artifacts.

### Fresh full test matrix

| Check | Result |
|---|---|
| Full Python suite | 298 passed, 18 skipped, 1 dependency deprecation warning |
| Skip audit | 15 `BLOCKED_NO_PRIVATE_GOLDEN`; 3 `BLOCKED_NO_GOLDEN_STRUCTURAL_FIXTURE`; no new reason |
| Business/effect focused | 51 passed |
| Migration focused | 54 passed |
| Production hardening/Auth/BFF/model ingestion | 92 passed |
| Forecast regression | 6 passed, 15 existing private-Golden skips |
| Analysis/Presentation/Evidence/History/Dashboard | 46 passed |
| React/Vitest | 7 files, 22 tests passed |
| Frontend standalone typecheck | PASS |
| Frontend production build | PASS; 1,813 modules transformed |
| Frontend lint | exit 0; existing unused-symbol warnings in inactive prototype code |
| npm audit | 0 vulnerabilities |
| Python dependency vulnerability scan | UNAVAILABLE: no `pip-audit` or `safety` in the test venv/PATH |
| Python `compileall` | PASS |
| Secret scan | PASS |

### Luna Max final integration review

The required single `luna-worker` review ran read-only with its fixed
`gpt-5.6-luna` model and maximum reasoning setting after Sol completed the
release diff, migration, live-evidence, and regression consolidation. It found
no blocker beyond `BLOCKED_NO_DISPOSABLE_CLEAN_DB` and independently confirmed
the Migration 004 qualifier-only exception, Migration 015 semantic change,
Migration 016/017 restoration, final grants/RLS/search-path/Storage boundaries,
shared lockout/session and pgmq/Worker/Result lifecycle, stored-Result-only
Viewer/Evidence, effect identity, strict Dashboard selection, secret hygiene,
and the non-Golden synthetic boundary.

Two non-blocking wording findings were accepted by Sol: the Dashboard service
docstring now states the strict published-default pair rather than the obsolete
“default-or-latest” wording, and the earlier 18-skip summary now records the
actual 15 private-Golden plus 3 structural-fixture split. Neither correction
changes runtime behavior.

The full offline release regression, live Phase A consistency, security review,
secret hygiene, and Luna review gates pass. Release Integration cannot be
declared PASS until a true empty disposable database replays 001--017
successfully.

Phase B remains `BLOCKED_NO_DEPLOYMENT_TOPOLOGY`, the company Workbook Forecast
benchmark remains `BLOCKED_NO_COMPANY_WORKBOOK`, Forecast Sync remains
`BLOCKED` with approval false, and Golden Business Accepted remains `NO`.
Production Candidate therefore remains `NO` regardless of the offline and
Phase A results.
