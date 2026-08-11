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

## Current platform evidence

- Supabase CLI was not installed globally. The official package was invoked
  read-only through `npx`; version `2.113.0` reported its command help.
- PostgreSQL reports `17.6` on Linux.
- `pgmq` is available at platform default `1.5.1`, but is not installed.
- Installed relevant extensions include `pgcrypto 1.3`,
  `pg_stat_statements 1.11`, `uuid-ossp 1.1`, and `supabase_vault 0.3.1`.
- Security and performance advisors returned no findings before application
  migrations. This is not evidence about the post-migration schema.
- The existing public Storage bucket has no custom `storage.objects` policies.
  Base Storage table grants exist for platform roles; RLS remains the row access
  boundary. The unrelated public bucket is outside this application's intended
  private `pnl-models` boundary.

Current Supabase documentation says new Queues use the platform-default `pgmq`
extension and queue tables are not exposed to the Data API unless explicitly
configured. The application migrations create `pgmq` without a version clause
and do not create `pgmq_public`, matching that server-only contract.

## Environment blockers

- Dedicated staging identity has not been confirmed by the project owner.
- No service-role credential or BFF production secrets are present in the local
  process environment. Secrets must be provisioned through an environment or
  secret store, never pasted into this document.
- No controlled company workbook is available for upload and 1/6/12-month
  Forecast performance benchmarking.
- Docker is unavailable, so clean migration replay cannot be substituted with a
  local Supabase stack.
- Reverse proxy/container/temp-volume topology is not available for Phase B.

## Write authorization checklist

Before the first remote write, record all of the following:

1. Project owner confirmation that the exact ref is dedicated staging.
2. Authorization to preserve the unrelated public bucket while adding the
   application's private bucket and schema.
3. A clean migration history check immediately before Migration 001.
4. Server credentials supplied outside source control/chat.
5. Controlled test-data ownership and cleanup boundaries.

After authorization, apply immutable migrations 001 through 012 in order. Any
platform correction must be additive Migration 013 or later and must be replayed
from a clean staging database before a PASS judgement.
