# Golden-aligned Google Cloud staging redeployment

Date: 2026-08-13 KST

Project: `pnl-dashboard-staging` (`498160536475`)

Region: `asia-southeast1`

This record covers the approved staging redeployment only. No production
resource, custom domain, DNS record, Supabase migration, company workbook,
Git push, merge, rebase, or reset was used.

## Source and delta

- Frozen accepted branch: `agent/golden-business-acceptance`
- Accepted source: `1e478b68b4f73dc6b41e2681cb6238a87d1e0427`
- Accepted commit: `fix(analysis): close golden business acceptance`
- Redeployment branch: `agent/golden-aligned-staging-redeploy`
- Redeployment base and starting HEAD: the exact accepted source above
- Previous staging source: `e3a3ec1aad50bb7abe940de715f1d0db0001eb43`

The accepted delta contains one production business-code change in
`forecast/analysis/sga_effects.py`: SG&A source rows are aggregated before the
existing variable/fixed classification, so duplicate account labels in the
selling and general/administrative sections cannot overwrite an earlier row.
The remaining delta is its regression coverage, Golden validation tooling, and
business-acceptance documentation. There is no deployment-configuration delta
and no `supabase/migrations` delta.

`NEW SUPABASE MIGRATION = NONE`. No migration or manual SQL patch was run.

## Clean build and Artifact Registry

The clean accepted worktree built an immutable `linux/amd64` release tagged
`golden-1e478b68b4f7`. Build contexts excluded Git metadata, environment files,
DPAPI material, secrets, generated evidence, and company workbooks.

| Image | OCI index digest | Linux/amd64 manifest | Compressed bytes |
|---|---|---|---:|
| `pnl-web` | `sha256:36502f01eed08012e2c0efb5f4756212c72b1373a390b5ed9bb78e59741d8330` | `sha256:2f2ecd574f75422451be0571a068b308c533e49653ccbe4f8db491ade292582a` | 38,536,604 |
| `pnl-runtime` | `sha256:4121d8f3fe25b555ea30355110008c4b6e5ac9cb2ecbc065f164bde2cd5ce485` | `sha256:73413f3befa22cdff1a042e5e053d37d067946315db9cd73df3563c72bb358f5` | 191,367,294 |

Both resource labels and deployment evidence pin
`source-commit=1e478b68b4f73dc6b41e2681cb6238a87d1e0427`,
`release-stage=golden-aligned-staging`, and `business-gate=passed`.

## Rollback snapshot

Before mutation, the public Web revision was `pnl-web-00006-h64`, the private
Controller revision was `pnl-worker-controller-00003-vss`, the Worker Pool was
generation 13 at manual count zero, and Maintenance was generation 3. The old
Web OCI index digests were `sha256:91d8f69c4f1e30f3036c595b1ed3c4976f10199cda311c84c07f36bd6b5eae35`
and `sha256:3f78a0fca1a1ccba17091ffc5053c30d336efc88021129dc7e25d6c60a6b8915`.
The old Ready revisions and old registry images remain present. No rollback was
required.

## Canary, promotion, and deployed-code alignment

`pnl-web-golden-1e478b6` was first created at zero traffic with a dedicated
tagged URL. Its live and ready probes, React static response, localhost BFF
connectivity, and UID 10001 memory-volume canary passed before promotion. The
canonical staging URL then moved to 100% of this revision.

The Controller used the same zero-traffic canary sequence. Its private live and
worker-status endpoints passed with authenticated invocation before promotion.
The Worker Pool image was changed while actual/manual count remained zero.
Maintenance was updated without changing its one-task, retry-zero, 900-second,
default-dry-run contract.

| Runtime resource | Revision/generation | Pinned image |
|---|---|---|
| `pnl-web` edge | `pnl-web-golden-1e478b6` | `pnl-web@sha256:36502f01eed08012e2c0efb5f4756212c72b1373a390b5ed9bb78e59741d8330` |
| `pnl-web` BFF | `pnl-web-golden-1e478b6` | `pnl-runtime@sha256:4121d8f3fe25b555ea30355110008c4b6e5ac9cb2ecbc065f164bde2cd5ce485` |
| `pnl-worker` | generation 18 after lifecycle/emergency smokes | `pnl-runtime@sha256:4121d8f3fe25b555ea30355110008c4b6e5ac9cb2ecbc065f164bde2cd5ce485` |
| `pnl-worker-controller` | `pnl-worker-controller-golden-1e478b6` | `pnl-runtime@sha256:4121d8f3fe25b555ea30355110008c4b6e5ac9cb2ecbc065f164bde2cd5ce485` |
| `pnl-maintenance` | generation 4 | `pnl-runtime@sha256:4121d8f3fe25b555ea30355110008c4b6e5ac9cb2ecbc065f164bde2cd5ce485` |

`STAGING DEPLOYED CODE ALIGNMENT = PASS`.

## Actual HTTPS and security smoke

The canonical URL is
`https://pnl-web-498160536475.asia-southeast1.run.app`.

- HTTPS live, ready, and React static routes returned 200.
- An unauthenticated session lookup returned the expected 401.
- Admin and Viewer login and session read returned 200.
- Session cookies retained `HttpOnly`, `Secure`, and `SameSite=Strict`; the
  readable CSRF cookie was separate.
- A mutation without the CSRF token returned 403; a valid CSRF logout returned
  200.
- Viewer access to Worker administration returned 403.
- Web, Worker, and Maintenance all logged `volume_canary=pass uid=10001` for
  their two writable memory paths.

Dashboard, Model list, History, Result, Presentation, P&L Dashboard, and
Evidence download were exercised one by one from a zero Worker state. Every
operation succeeded and every following Worker observation remained desired
zero, actual zero, and queue depth zero. Evidence had the expected XLSX MIME,
safe disposition, valid ZIP structure, 16 package entries, and no retained
temporary file. An existing unpublished Result returned Viewer 404.

## Synthetic Model, private Storage, and Analysis

The repository's existing non-business test generators produced a new
8,146-byte zero-delta infrastructure pair. No company workbook was read or
uploaded. Both files passed local 2026/12-month preflight and the deterministic
Engine reconciliation before upload; they intentionally had the same synthetic
SHA-256.

Both Models were uploaded through the real Admin HTTPS boundary. Each began
unpublished and non-default. Private `pnl-models` Storage downloads were read
server-side and matched the local exact bytes and persisted SHA. Model
publication did not make either Model a default.

From confirmed Worker zero, Job `807bc45e-3bc7-44d8-a5bb-2a485fc14e9c` was
durably created and given pgmq receipt 9 at 23:26:54.039946 UTC. Cloud Audit
Logs recorded the Controller's Worker Pool update at 23:26:54.250216 UTC,
approximately 210 ms later. This directly proves enqueue/commit before wake.

The API first reported `PENDING/QUEUED`. The pool converged only to one instance,
the Worker volume canary passed, and the job completed on attempt one in about
21 seconds. Exactly one Result was stored. It began unpublished and non-default;
Admin preview returned 200 while Viewer returned 404. A controlled server-side
publication kept it non-default, after which Viewer Result, Presentation, and
Evidence all returned 200 and History contained the Job/Result pair.

This live pipeline, together with the accepted Golden PASS, the duplicate-SG&A
targeted regression, and exact clean-build provenance, closes staging evidence
for the accepted SG&A fix without remotely uploading company data.

The Analysis response correlation ID was also present in the new BFF revision's
structured request log for the exact `POST /api/analyses` 200. Immediately
before that request completion, the same revision logged a 204 response from
the append-only Supabase audit RPC. Edge access logs redact the session cookie.
This preserves request correlation and audit evidence without exposing access
codes, session tokens, workbook content, or secrets.

## Worker lifecycle and emergency controls

The production-intended 1,800-second idle policy and five-minute Scheduler were
not shortened. The post-analysis all-clear state had queue, pending,
processing, active lease, active heartbeat, and recovery counts all zero.

The last Worker-required activity was 23:27:13.943593 UTC. At 29 minutes 44
seconds the pool was still desired one and actual one. The normal Scheduler
recorded sleep scaling at 00:00:06.345400 UTC, 32 minutes 52 seconds after the
last activity, and the 00:00:14 observation showed desired zero and actual
zero. This is inside the planned 30–35 minute bound and was not accelerated by
a manual reconcile.

With the pool back at zero and no work present, the Admin HTTPS emergency-wake
control returned 200 and actual count reached one. The same call as Viewer
returned 403. Admin safe-stop then returned 200 and the final durable and actual
counts converged to zero with queue, processing, lease, and recovery counts all
zero. Emergency wake therefore did not create an always-on override.

The Scheduler remains enabled at `*/5 * * * *` UTC, with OIDC, 30-second
deadline, three retries, 120-second retry duration, five/30-second bounded
backoff, and the stable canonical Controller reconcile URL.

## Maintenance, IAM, and secret hygiene

Maintenance execution `pnl-maintenance-4hfp7` completed successfully in 19.3
seconds with one succeeded task, no retry, no destructive apply, UID 10001
volume writes, and exit zero.

Secret Manager access remains narrow:

- Web: Supabase server secret plus Viewer, Admin, actor namespace, and CSRF
  secrets.
- Worker: Supabase server secret only.
- Maintenance: Supabase server secret only.
- Controller: Supabase server secret only.

Runtime identities have no Owner, Editor, or broad Cloud Run Admin binding.
The accepted repository, built image layers/config, and approximately 1.9 MiB
of recent Web/Worker/Job logs were scanned in memory against the exact five
Secret Manager values: zero matches. The temporary image export was removed.
No secret value is recorded here.

## Verification

- Accepted Golden/business run: PASS.
- Duplicate SG&A account regression and deployment/lifecycle slices: 61 passed.
- Full Python: 391 passed, 18 existing private-Golden skips.
- React: 24 passed; TypeScript, Vite production build, and npm audit passed.
- Lint: passed with pre-existing unused-symbol warnings only.
- Python compileall, Docker builds/smokes, Caddy validation, four rendered YAML
  parses, manifest contracts, secret scan, and `git diff --check`: PASS.
- No new unexplained skip was added.

The secret-free machine-readable live snapshot captured during this run is
committed next to this report as
`docs/evidence/golden_aligned_staging_snapshot.json`. It records the resource
revisions/generations, traffic, digests, source labels, Scheduler contract,
rollback targets, IAM/secret-reference shape, and final zero Worker state. It
contains neither secret values nor workbook content. The ignored rendered
manifests were also refreshed to the new digest pair after Luna review so a
local operator will not accidentally reuse the old staging images; they remain
generated artifacts and are not repository evidence.

## Boundary and current verdict

The accepted Golden pair remains local only. `EXCEL EFFECT ORACLE` remains
`NOT_PRESENT`; the separate independent Effect reference gate remains the
accepted evidence. No production resource has been created or changed.

- `STAGING DEPLOYED CODE ALIGNMENT = PASS`
- `STAGING GOLDEN-ALIGNED REDEPLOYMENT = PASS`
- `STAGING POST-DEPLOY SMOKE = PASS`
- `GOLDEN BUSINESS GATE = PASS`
- `REAL GOOGLE CLOUD STAGING = PASS`
- `V1 TECHNICAL RELEASE CANDIDATE = READY`
- `V1 BUSINESS RELEASE CANDIDATE = READY`
- `V1 PRODUCTION PROVISIONING CANDIDATE = READY`

`REAL PRODUCTION DEPLOYMENT = NOT_EXECUTED` and
`V1 PRODUCTION RELEASE READY = NO` remain unchanged.
