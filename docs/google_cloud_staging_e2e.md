# Google Cloud staging live E2E record

Date: 2026-08-12

This record covers the approved staging deployment only. The exact Google Cloud
project is `pnl-dashboard-staging` (project number `498160536475`), the region is
`asia-southeast1`, and the external Supabase project ref is
`ysatkswhhajicfgbrtpv`. No production project, forbidden Supabase ref, company
workbook, custom domain, Git push, merge, rebase, or reset was used.

## Provisioned staging topology

- Public same-origin Cloud Run service `pnl-web`: Google-managed HTTPS, Caddy
  static React edge, and a localhost-only FastAPI sidecar. The service is min
  zero/max two, concurrency four, and request timeout 180 seconds.
- Cloud Run Worker Pool `pnl-worker`: independent pgmq consumer, one vCPU, one
  GiB, manual instance count constrained by policy to zero or one.
- Private request-based Cloud Run service `pnl-worker-controller`: min zero/max
  one. Only the web and reconciler identities can invoke it.
- Cloud Scheduler job `pnl-worker-reconcile`: every five minutes, OIDC, attempt
  deadline 30 seconds, three bounded retries, and two-minute retry duration.
- Cloud Run Job `pnl-maintenance`: one task, no retry, 900-second timeout, and
  default dry-run arguments.
- Regional immutable-tag Artifact Registry repository `pnl-staging`, five
  Secret Manager secrets with one active version each, and role-specific
  runtime service accounts.

The deployed images are digest-pinned `linux/amd64` artifacts. Both runtime
containers execute as UID 10001. Startup canaries wrote, read, and deleted files
under the configured BFF, Worker, and maintenance memory volumes. The web
service exposes only the edge port; the BFF binds on localhost port 8000.

## IAM and secret boundary

The controller has only pool-scoped `run.workerpools.get` and
`run.workerpools.update`, project-scoped `run.operations.get`, and
`iam.serviceAccounts.actAs` on the `pnl-worker` service account. The reconciler
has Invoker only on the private controller. Runtime identities have no Owner,
Editor, or broad Cloud Run Admin role.

Supabase and application secrets were registered through no-echo input or
process memory. Values were never placed in the repository, rendered manifests,
Docker build args/layers, frontend bundle, command arguments, or tracked env
files. Exact-value and credential-pattern scans passed over the repository,
rendered configuration, image history/content, exported live configuration, and
recent logs.

## Supabase migration and storage

The target project was healthy and the demand-only lifecycle migration was
applied once. Its table, RPCs, trigger, RLS boundary, and service-role-only
execution were verified. Model-upload placeholder rows without a durable queue
receipt are excluded from Worker-required activity.

Two non-business, all-zero test-generated workbooks were uploaded through the
real Admin API, stored in the private `pnl-models` bucket, SHA-verified against
the exact local bytes, and published without becoming defaults. Upload and
publication did not change Worker activity state. No company workbook was used.

## Live web and security canaries

- `/health/live` and `/health/ready`: HTTPS 200.
- Admin and Viewer login: 200. Cookies were `HttpOnly`, `Secure`, and
  `SameSite=Strict`; logout was 200 with a valid CSRF token.
- Wrong Origin/CSRF: 403. Viewer access to Worker administration and Viewer
  state-changing emergency wake: 403.
- Distributed lockout: attempts one through four returned 401, five and six
  returned 429, and a valid code remained blocked during the window. After the
  configured five-minute window, valid login and session lookup both returned
  200.
- A session remained valid across a deliberately created web revision and the
  subsequent manifest cleanup revision, confirming Supabase-backed shared
  session semantics across Cloud Run instances/revisions.
- Admin/Viewer Result and Presentation, Admin History, Admin/Viewer Evidence
  XLSX, and Viewer P&L Dashboard returned 200 for the existing published
  synthetic default. Admin and Viewer Evidence returned the same byte length;
  the bytes were hashed in memory and were not persisted locally.

## Forecast policy

The live service kept synchronous Forecast mode and the approved maximum of six
consecutive months. One- and six-month canonical zero-fixture requests entered
the Engine and then failed business validation with 422, as expected for this
fixture. Seven- and twelve-month requests failed closed with 403 before creating
a reservation. No Forecast permit or recovery row remained. This preserves:

- `FORECAST SYNC POLICY = APPROVED_FOR_MAX_6_CONSECUTIVE_MONTHS`
- `FULL 12-MONTH FORECAST = DEFERRED_UNVERIFIED`
- `GOLDEN BUSINESS GATE = BLOCKED_NO_EXCEL_CALCULATED_PAIR`

## Maintenance and recovery

The default maintenance dry-run completed successfully. A separate argument
override canary also completed and proved UID 10001 volume writes. Maintenance
did not wake or reset the Worker lifecycle.

An early Worker control request durably recorded desired state one but could not
scale because Cloud Run revalidated `iam.serviceAccounts.actAs`; a second live
finding showed that Worker Pool LRO observation needs project-scoped
`run.operations.get`. IAM was narrowed to those exact requirements. The next
Scheduler reconcile recovered the desired-one state, the Worker became Ready,
and its startup volume canary passed. This is live evidence that a transient
wake/control failure does not erase durable lifecycle intent.

## Demand-only Worker lifecycle

The production-intended 1,800-second idle policy was exercised without reducing
the timeout. An emergency wake set the last Worker-required activity at
13:54:21.310368 UTC. At exactly 1,740 seconds (29:00) the durable desired and
observed counts were still one. Scheduler requested sleep at 14:25:05.720934,
the controller recorded scaling at 14:25:07.203117, and at 14:25:12 the durable
and real Worker Pool counts were zero. Observed convergence was therefore
30 minutes 46 seconds at the scaling record and 30 minutes 51 seconds at the
follow-up observation, inside the planned 30-35 minute range.

From a confirmed zero pool, an actual Analysis request created and enqueued Job
`293ae4c9-9154-49ee-8c2c-777e1378d070` at 14:26:06.585370 UTC. Cloud Audit Logs
recorded the controller's Worker Pool update at 14:26:07.036537, 451 ms after the
durable enqueue timestamp. The API returned queued after 11.035 seconds; an
immediate safe-stop attempt returned 409 while work was active. The Worker
claimed the pgmq message and completed the deterministic Analysis on attempt one
at 14:26:18.996435. Result `5274a22e-b875-4247-8449-d38456b2a6a3` was created
unpublished and non-default. Admin could read it; Viewer received 404.

Two truly concurrent submissions with one new idempotency key both returned
200, converged on Job `422836bf-9d45-4de2-957c-873014b0249e`, and returned one
false and one true replay flag. The database contained one Job and one completed
Result for the operation; the Worker Pool never exceeded one instance.

For the sleep/enqueue race, Admin safe-stop and a new Analysis enqueue were sent
concurrently. Enqueue won the durable-state lock, safe-stop returned 409, Job
`eed6d4cb-a48f-46d2-b4d4-8125a62f8b80` completed, and the final state converged
to desired one/actual one with queue depth zero. No Job was stranded. After all
canaries, all seven staging Jobs were completed, pending and processing counts
were zero, and all three new Results were unpublished and non-default.

The documented Level-3 CLI break-glass equivalent then changed the pool from
zero to one under the authenticated human principal at 14:30:04.734339 UTC.
The automatic reconciler restored count zero at 14:30:05.923084, and durable
desired/observed counts finished at zero with no scaling error. This exercises
the same Worker Pool manual-instance control used by the Cloud Console while
leaving the UI procedure documented in `deploy/gcp/worker-lifecycle.md`.

With the pool back at zero, Admin Model list and History plus Viewer P&L and
Presentation were read again over the public HTTPS origin. All returned 200 and
the lifecycle remained desired zero/observed zero, queue depth zero. Earlier
Model upload/publication, Forecast, maintenance, login, logout, Result, Evidence,
and navigation canaries likewise left the Worker activity timestamp unchanged.

## Cost evidence

The live Artifact Registry currently reports 49 stored files and approximately
0.215 GiB, below the published 0.5 GiB-month storage allowance. One Scheduler
job fits its three-job billing-account allowance, and five active secret
versions fit the six-version allowance. Demand-session estimates retain a
conservative 35-minute Worker tail: 30 continuous idle minutes plus up to one
five-minute reconciliation interval. See `deploy/gcp/cost-model.md`.

Google Cloud budgets are alerts, not hard spend caps. A monthly 15,000 KRW
alerts-only budget exists at 50%, 80%, and 100%; web/controller/Worker ceilings,
immutable images, and dry-run cleanup policy provide the actual runtime bounds.

## Validation boundary

The repository and container regression suite remained green after the staging
fixes:

- full Python: 387 passed, 18 existing private-Golden skips;
- lifecycle/readiness slice: 37 passed;
- React: 24 passed; TypeScript, production build, lint, and npm audit passed
  (zero vulnerabilities; existing lint warnings only);
- compileall, four rendered YAML parses, Docker builds/image inspection,
  `linux/amd64` verification, secret scans, and `git diff --check` passed.

Live deployment and lifecycle evidence is now complete for the synthetic
staging path. It does not validate an Excel-calculated Golden pair, a successful
Forecast Result from a formula-complete fixture, a twelve-month Forecast, a
custom domain, or production traffic. The test-generated spreadsheet workspace
was removed after the live canaries; no downloaded Evidence workbook or secret
plaintext artifact was retained.

## Final staging verdict

- `REAL GOOGLE CLOUD DEPLOYMENT = PASS`
- `REAL CLOUD DEPLOYMENT TOPOLOGY = VALIDATED`
- `REAL CLOUD WORKER LIFECYCLE = PASS`
- `DEMAND WAKE = PASS`
- `NON-WORKER NO-WAKE = PASS`
- `30-MINUTE AUTO SLEEP = PASS`
- `RECONCILER RECOVERY = PASS`
- `ADMIN EMERGENCY MODE = PASS`
- `CONSOLE BREAK-GLASS = PASS` (the documented CLI-equivalent control was
  exercised; the Console UI procedure uses the same manual instance field)
- `GOOGLE CLOUD COST FIT = PASS_FOR_TARGET_BUDGET`
- `PRODUCTION CODE / CLOUD TOPOLOGY CANDIDATE = READY`
- `GOLDEN BUSINESS GATE = BLOCKED_NO_EXCEL_CALCULATED_PAIR`
- `FULL 12-MONTH FORECAST = DEFERRED_UNVERIFIED`
- `V1 BUSINESS RELEASE READY = NO`
