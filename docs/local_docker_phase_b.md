# Local Docker Phase B

This topology is a local, production-like verification environment. It is not
an internet-facing or cloud deployment.

## V1 Forecast contract

- `BFF_FORECAST_MODE=disabled` and explicit approval `false` starts the full
  production BFF without constructing the Forecast service. The Forecast route
  remains authenticated and fails closed with `FORECAST_SCOPE_NOT_APPROVED`.
- `BFF_FORECAST_MODE=sync` requires explicit approval `true` and
  `BFF_FORECAST_SYNC_MAX_MONTHS=1..6`.
- The lower-level application factory also defaults Forecast to disabled;
  direct dependency-injection composition must opt in explicitly and is not a
  substitute for the production environment policy gate.
- The BFF rejects a request spanning more than the configured consecutive-month
  limit before any reservation, Storage write, or `ForecastEngine` execution.
- Full 12-month synchronous Forecast remains `DEFERRED_UNVERIFIED`; a six-month
  result is never doubled or extrapolated.

## Topology and boundaries

`compose.phase-b.yaml` starts one host-facing Caddy edge at
`https://phase-b.localhost:8443`, a static React frontend, two identical BFF
containers, and an independent Worker. Maintenance and the verification probe
are one-shot profile services. Only the edge publishes a host port. BFF
containers share Supabase state but no filesystem or sticky session.

The edge owns `172.30.0.10` on the explicit `172.30.0.0/24` bridge. BFF trusted
proxy configuration permits only `172.30.0.10/32`; Uvicorn does not consume
forwarded headers, so the application policy remains the single client-identity
authority. Caddy is the first proxy and replaces attacker-supplied forwarding
identity before sending its own chain.

Each BFF is limited to 1.5 GiB and one CPU. The isolated parser concurrency is
one per BFF, with a 768 MiB child limit. The Worker is limited to 1 GiB and one
CPU. The two BFFs use separate 512 MiB tmpfs filesystems at
`BFF_TEMP_ROOT=/var/tmp/pnl`, matching the application quota. These limits leave
headroom within the observed Docker Desktop allocation. Sizing uses the prior
controlled local six-month company-workbook peak as evidence, not as a
12-month estimate or as a guarantee for unmeasured concurrency.

The BFF execution budget is 120 seconds and the local edge response-header
timeout is 180 seconds, leaving an explicit proxy margin above the BFF cutoff
and the prior approximately 50.7-second six-month mean. This configuration is
local sizing evidence only; sync-mode deployed execution remains pending.

BFF, Worker, and maintenance containers also receive separate 256 MiB tmpfs
filesystems at `/app/data`. This is the bounded writable location used by the
Supabase adapter's per-container model cache; it is not shared session state and
is discarded with the container.

The independent Worker clears its private downloaded-model cache at startup and
after every settled claimed job, including failed or retryable jobs. A cleanup
failure terminates the Worker instead of silently weakening the filesystem
boundary; container restart retries startup cleanup. BFF caches remain separate
and bounded by their tmpfs and container lifecycle because deleting a live BFF
cache could race concurrent requests. Maintenance cannot sweep another
container's private tmpfs.

## Secrets and local CA

Set `PHASE_B_SECRETS_DIR` to an absolute directory outside the repository with
five files named `supabase_secret_key`, `viewer_code`, `admin_code`,
`actor_namespace_secret`, and `csrf_secret`. Each contains one value and is
mounted read-only under `/run/secrets`. Secret values are loaded by the runtime
entrypoint and are absent from image layers and Compose environment metadata.
After placing only `supabase_secret_key` in the controlled directory, generate
the other four values without printing them:

```powershell
python scripts/prepare_phase_b_secrets.py --directory C:\controlled\phase-b-secrets
```

Caddy creates a local internal CA in the `edge_data` named volume. No certificate
or private key is committed and the host trust store is not modified. The probe
mounts the volume read-only and verifies HTTPS using the generated root CA.

## Commands

Validate without starting containers:

```powershell
$env:PHASE_B_SECRETS_DIR='C:\controlled\phase-b-secrets'
docker compose -f compose.phase-b.yaml config --quiet
```

Build and start Forecast-disabled infrastructure:

```powershell
docker compose -f compose.phase-b.yaml build
docker compose -f compose.phase-b.yaml up -d edge frontend bff-a bff-b worker
docker compose -f compose.phase-b.yaml --profile probe run --rm probe
```

Run the maintenance dry-run; add `--apply` only for an explicitly authorized
recovery operation:

```powershell
docker compose -f compose.phase-b.yaml --profile maintenance run --rm maintenance
```

An authorized apply run must spell out the overridden service command:

```powershell
docker compose -f compose.phase-b.yaml --profile maintenance run --rm maintenance python -m forecast.maintenance cleanup --apply
```

Stop the local topology without deleting its named CA volumes:

```powershell
docker compose -f compose.phase-b.yaml down
```

The maintenance container can process durable Supabase recovery, Storage, and
auth-retention state. Its private tmpfs cannot sweep another container's local
tmpfs; container removal is the ownership boundary for those artifacts.

## Frozen verification state

The repository and local Docker checks establish:

- pinned Python, Node, and Caddy image builds;
- Compose and both Caddy configuration validations;
- non-root edge, frontend, BFF, Worker, and maintenance images;
- CA-verified HTTPS delivery of the React production build at the local edge;
- explicit CPU, memory, process, read-only-root, and bounded tmpfs controls;
- secret-file mounts with no server secret in image layers or Compose
  environment metadata;
- Forecast-disabled startup composition without a Forecast service or Forecast
  runtime RPC;
- Forecast-disabled and approved synchronous-mode BFF startup under read-only
  roots;
- the Python regression suite and the focused deployment-policy tests.

The controlled live follow-up ran on 2026-08-12 against the dedicated
`pnl-dashboard-staging-clean` Supabase project. The temporary server credential
was passed only to the backend runtime and was not added to the repository,
Compose environment metadata, an image layer, the frontend, or a tracked env
file. The live topology established:

- managed local HTTPS to the React production build and BFF readiness;
- two BFF replicas with a shared server-side session, cross-replica logout, and
  distributed lockout;
- canonical synthetic Model upload, exact local/persisted/private-Storage SHA
  agreement, and Model publication;
- Analysis submission, pgmq delivery, independent Worker execution, stored
  Result, Admin/Viewer reads, Presentation, History, Evidence XLSX, and the P&L
  Dashboard;
- durable BFF audit events and HTTP correlation identifiers;
- maintenance dry-runs before and after Forecast policy probes, with no pending
  recovery item, active Forecast permit, or visible queue message afterward.

The approved synchronous Forecast runtime used `mode=sync`, explicit approval
`true`, and a maximum of six consecutive months. Valid canonical requests for
one and six months passed the scope gate, created durable reservations, and
entered Forecast execution. They settled as `FORECAST_GENERATION_FAILED`
because the non-business zero fixture is not a Forecast-valid generated-Model
fixture. Valid seven- and twelve-month requests returned
`FORECAST_SCOPE_NOT_APPROVED` and created no durable reservation, proving that
they were blocked before execution. This preserves the separate company-
workbook Engine benchmark evidence (approximately 7.7 seconds for one month,
50.7 seconds and 328.6 MiB sampled RSS for six months) without uploading that
workbook remotely.

The final cleanup removed all Phase B containers and temporary secret
directories. Exact-value and high-risk-pattern scans of repository content,
frontend content, container metadata, image configuration/history, and Docker
logs passed. No company workbook was copied, committed, or uploaded.

Frozen verdict:

- `LOCAL PRODUCTION-LIKE PHASE B = PASS`
- `FORECAST SYNC POLICY = APPROVED_FOR_MAX_6_CONSECUTIVE_MONTHS`
- `FULL 12-MONTH FORECAST SYNC = DEFERRED_UNVERIFIED`
- `REAL CLOUD DEPLOYMENT TOPOLOGY = NOT_VALIDATED`
- `GOLDEN BUSINESS GATE = BLOCKED_NO_EXCEL_CALCULATED_PAIR`

The generated CA was trusted explicitly by controlled HTTP clients without
changing the host trust store. Cloud readiness must use the target platform's
managed HTTPS contract instead of treating this local CA as a deployable cloud
artifact.
