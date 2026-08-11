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

The current adapter does not evict distinct cached model IDs. The controlled
Local Phase B probe uses one existing model pair, but a long-running production
Worker needs an explicit cache-eviction/recycling policy before this 256 MiB
boundary is treated as an availability guarantee. Container recreation clears
the private cache; maintenance cannot sweep another container's tmpfs.

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

## Verification state

The repository and local Docker checks currently establish:

- pinned Python, Node, and Caddy image builds;
- Compose and both Caddy configuration validations;
- non-root edge, frontend, BFF, Worker, and maintenance images;
- CA-verified HTTPS delivery of the React production build at the local edge;
- explicit CPU, memory, process, read-only-root, and bounded tmpfs controls;
- secret-file mounts with no server secret in image layers or Compose
  environment metadata;
- Forecast-disabled startup composition without a Forecast service or Forecast
  runtime RPC, sync scope `1..6`, and fail-closed rejection of `7`;
- Forecast-disabled BFF process startup and `/health/live` under a read-only
  root using validation-only local placeholders (no remote readiness claim);
- the Python regression suite and the focused deployment-policy tests.

The remote Supabase server secret was not available during this verification.
Consequently BFF A/B readiness, shared session/logout, distributed lockout,
independent Worker processing, maintenance against durable state, and the full
canonical journey have not yet been executed in the Docker topology. Until that
controlled follow-up run completes, the honest topology result is
`BLOCKED_MISSING_SUPABASE_SERVER_SECRET`, not Local Phase B PASS. No company
workbook was copied, committed, or uploaded.

The generated CA was trusted explicitly by the controlled HTTP client, without
changing the host trust store. The in-app browser correctly refused that local
CA as untrusted, so the real browser journey also remains pending. A later
browser run requires a separately approved temporary trust method or a browser
context configured to trust only this generated CA; no certificate warning is
bypassed as Phase B evidence.

The follow-up needs only an out-of-repository `supabase_secret_key` file. Run
the preparation command above, then the build/start, probe, and maintenance
commands. The probe emits only safe PASS labels and identifiers; it does not
print access codes, tokens, or workbook contents.
