# Google Cloud deployment readiness record

Date: 2026-08-12

This is the pre-provisioning readiness snapshot. The subsequently approved and
executed staging deployment is recorded in `docs/google_cloud_staging_e2e.md`;
its live verdict supersedes the `NOT_YET_EXECUTED` boundary below without
rewriting this historical checkpoint.

## Provenance and recovery

- Frozen Phase B branch: `agent/local-docker-phase-b`
- Frozen Phase B HEAD: `d3feb30e08379e72ba199932e1b371478df59d75`
- Readiness branch: `agent/google-cloud-deployment-readiness`
- Exact readiness base: frozen Phase B HEAD above, not `main`
- No OCI/deployment-readiness worktree or branch existed to recover. All known
  registered worktrees were inspected without reset, rebase, restore, clean, or
  deletion. One older worktree contains preserved untracked pytest temp artifacts.
- Unreachable objects were inspected and were superseded earlier feature commits,
  not interrupted OCI/readiness implementation.

Provider-neutral work reused from Phase B:

- digest-pinned non-root Docker images;
- Linux `_FILE` secret adapter;
- bounded temp/cache volumes, application quota, and cleanup command;
- log limits, restart/process semantics, health/readiness endpoints;
- shared Supabase sessions/lockout/audit/permits and independent pgmq Worker;
- images compatible with local amd64/arm64 builds (Cloud Run output is explicitly
  built as `linux/amd64` because that is the platform contract).

No OCI-specific implementation was found or deleted. OCI is recorded only as:

- `OCI VCN = CREATED BY USER`
- `OCI VM = BLOCKED_OCI_FREE_CAPACITY`
- `OCI DEPLOYMENT PRIORITY = SECONDARY / DEFERRED`

## Frozen Phase B evidence

`LOCAL PRODUCTION-LIKE PHASE B = PASS`

The live path passed managed-style HTTPS/React/BFF A+B, shared session/logout,
distributed lockout, synthetic Model upload, private Storage SHA, publication,
Analysis/pgmq/independent Worker/Result/Admin/Viewer, Presentation/History,
Evidence XLSX/P&L Dashboard, audit/correlation, and controlled maintenance.
Company workbooks were not uploaded. Secret cleanup and exact-secret scans passed.

Forecast policy remains `sync`, explicit approval `true`, maximum six consecutive
months. One and six months entered execution; seven and twelve months failed
closed before reservation. The zero synthetic fixture could not produce a final
successful Forecast Result, but prior actual-company-workbook local Engine
benchmarks passed at approximately 7.7 seconds (one month) and 50.7 seconds /
328.6 MiB sampled RSS (six months). This does not reverse Phase B.

## Google mapping and non-regressions

The deployment artifact is `deploy/gcp/`. Supabase remains the external managed
Database, private Storage, session/lockout/audit authority, Forecast permit store,
and pgmq queue. No PostgreSQL, Storage, queue, or Auth migration is proposed.

The Browser has one Google-managed HTTPS origin. React and the API are not split
into public cross-origin services. FastAPI has no independently reachable URL.
Worker execution stays outside the request service. Maintenance stays a manual,
default-dry-run one-shot.

No business formula, mapping, DTO, publication, Viewer, Evidence, Forecast scope,
or Engine code is changed by readiness. The following invariants remain source
contracts and regression-test obligations: LC 4-inch, FS LENGTH/m, finished PCS,
no PCS+LENGTH aggregation, `effects_total + residual = OP_delta`, no residual
plug, direct KRW/JPY without `/100`, no separate MCM RM effect, customer freight
once, Tariff separate, no V1 same-group SKU Mix claim, no Viewer Excel reopen or
Engine rerun, Worker completion unpublished/non-default, published-only defaults,
Base/Comparison identity and SHA pinning, no Pending Result fabrication, no
browser secret key, server-side Admin auth, explicit `PNL_REPOSITORY_BACKEND`,
and Forecast maximum six consecutive months.

## Evidence gaps and final readiness boundaries

The minimal non-business Forecast-valid synthetic fixture is not added in this
readiness slice. Constructing one without weakening workbook validation requires
additional formula-complete fixture design. It remains a small local evidence gap,
not a cloud provisioning blocker. It must not use or upload a company workbook.

Worker Pool architecture fit is PASS, but the approximately-zero incremental cash
target is FAIL for a continuous one-instance worker. See
`deploy/gcp/cost-model.md`. Real cloud resource behavior, latency, IAM, secret
mounts, and cost are not validated until a separately approved deployment goal.
Phase B did not capture a worker-only RSS sample; the selected 1 GiB limit reuses
the passing container ceiling and must be measured during the cloud canary before
any attempted reduction.

## Verification and final review

- Full Python: 360 passed, 18 skipped. The skips are the existing private Golden
  fixture cases; no new unexplained skip was added.
- Google Cloud contract slice: 11 passed, including same-origin routing, direct
  proxy spoof resistance, secret-file mounts, Worker Pool/Job/resource/timeout
  limits, build contexts, and business/overclaim boundaries.
- React: 22 passed; standalone TypeScript build, production Vite build, and lint
  completed. Lint reported only existing unused-symbol warnings in untouched UI
  files. `npm audit` reported zero vulnerabilities.
- Both web and runtime images built for `linux/amd64`. The non-root web image
  served the SPA, Caddy validated its HTTP-only configuration, and the runtime
  image executed Worker and maintenance CLIs through its entrypoint. This exposed
  and fixed Windows CRLF corruption of the Linux entrypoint during image build.
- Three offline-rendered manifests parsed as YAML. `compileall`, Docker/image
  sensitive-file inspection, repository secret scan, tracked artifact scan, and
  staged `git diff --check` passed.
- The required single Luna Max read-only call was attempted after implementation,
  regression, and cost analysis. The explicit model override was initially
  rejected; the user approved a retry through the fixed Luna worker role, and
  that review completed read-only. Sol corrected bootstrap IAM prerequisites,
  raised the gen2 edge minimum to 512 MiB, clarified header handling, and added
  mandatory UID 10001 volume-write canaries. Real cloud validation remains
  explicitly deferred.

Target status at readiness implementation time:

- `PHASE B EVIDENCE = FROZEN`
- `INTERRUPTED READINESS WORK = RECOVERED`
- `GOOGLE CLOUD DEPLOYMENT TOPOLOGY = READY`
- `GOOGLE CLOUD SAME-ORIGIN AUTH CONTRACT = PASS`
- `CLOUD RUN WEB CONFIG = READY`
- `CLOUD RUN WORKER POOL FIT = PASS`
- `CLOUD RUN MAINTENANCE JOB FIT = PASS`
- `GOOGLE SECRET MANAGER CONTRACT = READY`
- `GOOGLE CLOUD RESOURCE FIT = PASS`
- `WORKER OPERATING POLICY = DEMAND_ONLY`
- `WORKER DEFAULT STATE = ZERO`
- `GOOGLE CLOUD COST FIT = PASS_FOR_TARGET_BUDGET`
- `STEADY-STATE EXPECTED ADDITIONAL CASH COST = approximately $0 at 10/25/50/100 demand sessions under documented allowance assumptions`
- `REAL GOOGLE CLOUD DEPLOYMENT = NOT_YET_EXECUTED`
- `REAL CLOUD DEPLOYMENT TOPOLOGY = NOT_YET_VALIDATED`
- `GOLDEN BUSINESS GATE = BLOCKED_NO_EXCEL_CALCULATED_PAIR`
- `FULL 12-MONTH FORECAST = DEFERRED_UNVERIFIED`
