# Production Hardening Foundation

## Core functional integration gate

The reachable React routes use the trusted BFF for Login/Session, Model upload,
management/publication, Analysis submission/polling/stored Result presentation,
Evidence, History, P&L Dashboard and Forecast generation. Timer-based polling is
transport polling only. The legacy `DataManagementView`/`ModelUploadArea` mocks
remain unreachable compatibility UI and are not imported by the canonical App
route. No reachable browser module imports a Supabase client or service-role key.

`CORE APPLICATION FUNCTIONAL INTEGRATION = READY` is a code-route judgement; it
does not assert production infrastructure or Golden workbook acceptance.

## Boundary inventory

| Boundary | Classification | Code boundary |
|---|---|---|
| Opaque access-code session | PRODUCTION-SAFE (code) | `bff.auth.AccessCodeSessionService` + `SupabaseSessionStore`; only SHA-256 token digest is persisted |
| Multi-instance logout/revocation | PRODUCTION-SAFE (new requests) | `get_bff_session` rejects expired/revoked rows; in-flight operations are not cancelled |
| Login failure/lockout | PRODUCTION-SAFE (code) | atomic `record_bff_login_failure`, advisory-lock clear, DB time authoritative |
| Client identity | PRODUCTION-SAFE (code) | `TrustedProxyPolicy`; direct/trusted mode must be explicit |
| Principal audit | PRODUCTION-SAFE (code) | credential principal + role + digest-derived session ref + correlation/operation identity |
| Human attribution | INTENTIONALLY-DEFERRED | shared access code is not a person identity |
| Cookie/CORS/CSRF | PRODUCTION-SAFE (code) | Secure/HttpOnly/SameSite, explicit http(s) origins, Origin + HMAC double-submit checks |
| Forecast synchronous execution | BLOCKED-BY-DEPLOYMENT | production startup requires `BFF_FORECAST_SYNC_APPROVED=true` after staging/private-workbook benchmark |
| Forecast global concurrency | PRODUCTION-SAFE for bounded runs; deployment watchdog required | DB permit, idempotent acquire, lease/renew/release, DB-owned global maximum; a hung engine call is not preempted in-process |
| XLSX parser containment | PRODUCTION-SAFE on Linux code path | spawned process, timeout, ZIP caps, RLIMIT_AS/RLIMIT_CPU on POSIX |
| Windows parser memory cap | BLOCKED-BY-DEPLOYMENT | process/timeout containment exists; stdlib hard memory cap does not |
| Temp root/quota | PROCESS-LOCAL guard + deployment quota required | owned 0700 root, bounded prefixes, fail-closed checks, intermediate Forecast deletion; multipart spool files and concurrent replicas require filesystem/container quota |
| Orphan/recovery sweep | PRODUCTION-SAFE command; BLOCKED-BY-DEPLOYMENT scheduling | `python -m forecast.maintenance cleanup` dry-run default, atomic DB recovery claim before Storage deletion |
| Health/readiness | PRODUCTION-SAFE (code) | liveness plus published mapping/private bucket readiness; live connectivity verified next goal |
| Live permissions/RLS | BLOCKED-BY-DEPLOYMENT verification | Migration 012 hardens new RPCs and public schema creation; live pg_catalog/grant audit is next goal |

## Shared session and lockout

The browser holds a random bearer cookie. The database stores only its SHA-256
digest, an opaque `session-v1:` reference, credential principal, role, timestamps
and revocation state. Database time decides expiry. Separate BFF instances use
the same narrow service-role-only RPCs.

Login rate-limit keys are SHA-256 digests of a server-resolved client address.
Forwarded headers are ignored unless the socket peer is in the configured trusted
CIDR chain. Uvicorn/reverse-proxy `forwarded-allow-ips` must match this policy.

## Forecast decision and benchmark

`python -m forecast.benchmark --workbook ...` records 1/6/12-month wall time,
Python peak allocation, input/output size and peak temp bytes. Synthetic/fixture
measurements are labelled separately from private company workbooks. This source
tree has no private Golden workbook, so synchronous production approval is not
claimed. Until the staging benchmark demonstrates margin below proxy timeout,
the production composition fails closed without explicit benchmark approval.

Every operation freezes the already provenance-validated mapping JSON, uses that
snapshot for every monthly `ForecastEngine`, deletes prior intermediates, enforces
the request/execution/50MiB boundaries, and holds a shared execution permit.
The synchronous call cannot forcibly preempt a single hung engine step; staging
must validate the request watchdog/container kill boundary before approval.

## Temp and maintenance contract

| Owner prefix | Bound/lifetime | Cleanup |
|---|---|---|
| `pnl-model-` | upload <=50MiB; one request | endpoint `finally`; orphan sweep after configured age |
| `pnl-parser-` / parser process | source bounded by upload ZIP policy; configured timeout | process terminate/kill and handle close |
| `pnl-forecast-` | at most current source+destination+mapping; generated <=50MiB | `TemporaryDirectory`; orphan sweep |
| `pnl-evidence-` | stored Result <=25MiB; output <=100MiB | FileResponse background cleanup; orphan sweep |
| `pnl-forecast-benchmark-` | operator-only | temporary directory / orphan sweep |

The maintenance command derives only `models/{uuid}/source.xlsx`, atomically
claims an eligible recovery row before deletion, verifies object absence, and
then completes the claim. Repeated dry-runs and cleanup of already-absent objects
are safe. Scheduling is an external staging/deployment responsibility.

## Supabase security matrix

| Capability | Browser roles | service_role | SECURITY DEFINER/search path |
|---|---|---|---|
| shared sessions/lockout | revoked | execute RPC only | yes / empty |
| BFF audit append | revoked | execute RPC only | yes / empty |
| Forecast permit/runtime limit | revoked | execute RPC only | yes / empty |
| recovery claim/complete | revoked | execute RPC only | yes / empty |
| readiness/auth cleanup | revoked | execute RPC only | yes / empty |

Migration 012 revokes untrusted `CREATE` on `public`, preventing shadow objects
for legacy definer functions, removes direct service-role audit-log insertion,
redacts claim/error/request fields from generic row audit, and leaves existing
business/publication/provenance migrations unchanged. Existing service-role model
and worker grants remain deliberately trusted-server capabilities; a separate
BFF database role is a future least-privilege option after live compatibility
testing.

## Production configuration

Required/validated production inputs include explicit Supabase backend and its
server credentials, Viewer/Admin credentials, actor/CSRF secrets, Secure cookie,
explicit frontend origins, direct/trusted proxy mode, absolute temp root/quota,
published mapping/release, Forecast execution/permit budgets and explicit sync
benchmark approval. Secret presence never selects the repository backend.

## Operational limitations carried to Live Staging E2E

- Run Migration 001 through 012 and inspect effective `pg_proc`, grants, RLS and
  private Storage policies using real roles.
- Configure one authoritative reverse-proxy body/idle/request timeout, temp-volume
  filesystem quota, Uvicorn forwarded-IP policy and maintenance schedule.
- Size parser slots globally as replicas x workers x per-child memory; the Python
  semaphore is intentionally process-local.
- Run 1/6/12-month benchmark with a representative private company workbook.
- Validate Linux parser RLIMIT behavior and container memory/CPU kill semantics.
- Exercise audit sink outage/recovery and choose retention for append-only audit.
- Human/person attribution remains explicitly outside access-code V1.
