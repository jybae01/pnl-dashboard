# Demand-only Worker operating policy

V1 has one policy in every timezone and on every day:

`WORKER OPERATING POLICY = DEMAND_ONLY`

`pnl-worker` is created with `manualInstanceCount=0`. Only a validated,
idempotent Analysis submission that has committed both its Job row and pgmq
message requests a transition to one instance. Login, logout, ordinary API
traffic, dashboards, History, Result, Presentation, Evidence XLSX, model upload,
Storage/SHA, publication, synchronous Forecast, health, and maintenance never
wake this pool. Forecast remains synchronous in the BFF with the six-consecutive-
month ceiling. Maintenance remains a separate Cloud Run Job.

## Correctness boundary

The Analysis RPC inserts and enqueues in one Supabase transaction. The BFF calls
the private controller only after that RPC returns:

```text
authorize -> validate -> idempotency -> Job -> pgmq -> COMMIT
                                                    -> ensure desired=1
```

A failed Google API call therefore leaves durable queued work. The Supabase
singleton lifecycle row is changed by a `calculation_jobs` trigger on enqueue,
claim, heartbeat, lease/retry, and completion. Its monotonically increasing
generation closes the sleep/enqueue race: a controller result is accepted only
for the generation it read. A late sleep patch detects the new generation and
reconverges to one. The five-minute reconciler is the independent recovery net.

The reconciler sets one when pgmq or active Job/lease/recovery state contains
work. It sets zero only after all those counters are zero and 1,800 continuous
seconds have elapsed since the last worker-required activity. Browser activity
does not update that timestamp. Multiple BFF/controller requests are harmless:
the only legal counts are zero and one, and identical patches converge.

## Components and IAM

- `pnl-web` calls `pnl-worker-controller` with a metadata-server ID token. Its
  runtime account receives `roles/run.invoker` only on that private service.
- `pnl-worker-controller` is request-based, min zero/max one. Its custom role
  contains only `run.workerpools.get` and `run.workerpools.update`, bound to the
  `pnl-worker` resource at the narrowest supported scope. It has Secret Accessor
  only on the Supabase server secret.
- `pnl-worker-reconciler` is one Cloud Scheduler HTTP job (`*/5 * * * *`) using
  OIDC. Its service account has Invoker only on the controller.
- `pnl-worker` retains the independent pgmq consumer, lease, heartbeat, retry,
  deterministic calculation, and unpublished/non-default completion contract.

No runtime identity receives Owner, Editor, Cloud Run Admin, worker-pool create,
delete, list, IAM-policy, Artifact Registry, or service-account-key permission.
Cloud Run IAM authenticates the controller before the container receives a
request. The browser never receives its URL or a Google credential.

## Reconciler and observations

Schedule only reconciliation; there is no weekday, weekend, or working-hours
schedule. The endpoint is `POST /v1/worker/reconcile`. It logs only desired and
observed/configured counts, queue/processing/lease/recovery counts, generation,
idle duration, and an allowlisted result/error code. It never logs a secret,
cookie, access code, request body, workbook data, Storage URL, or job payload.

Cloud Run exposes the configured manual count and reconciliation state rather
than a live process counter. `actual_instance_count` is therefore reported only
after `observedGeneration == generation`, reconciliation is false, and the
terminal condition is ready; otherwise it is `null`/`reconciling`. Staging must
measure wake-to-ready and wake-to-first-claim latency before any UI SLA is added.

## Emergency recovery

Level 1 is automatic reconciliation: pending work with zero configured instances
becomes one; an all-clear worker idle for at least 30 minutes becomes zero.

Level 2 is the application Admin panel. Server-side Admin authorization protects
status, Emergency wake, and Safe stop. Emergency wake still follows ordinary
30-minute auto-sleep. Safe stop rejects pgmq work, PROCESSING, an active lease or
heartbeat, or retry/recovery work with `WORKER_BUSY`. V1 has no force-stop or
always-on mode.

Level 3 is break-glass when the application/controller is unavailable:

```powershell
gcloud run worker-pools describe pnl-worker --region=asia-southeast1
gcloud run worker-pools update pnl-worker --region=asia-southeast1 --instances=1
# After confirming queue=0, PROCESSING=0, lease=0, recovery=0:
gcloud run worker-pools update pnl-worker --region=asia-southeast1 --instances=0
```

The Console equivalent is Cloud Run -> Worker pools -> `pnl-worker` -> manual
instance count 0/1. This is break-glass only. Never stop at one while a Job or
lease is active. After a manual wake, automation still returns it to zero.

## Demand cost model (USD/month)

Planning uses the selected Singapore Worker Pool rate: $0.000013493 per vCPU-
second plus $0.000001482 per GiB-second for 1 vCPU/1 GiB. Until the cloud canary
provides Worker-specific duration, each independent wake session conservatively
uses the existing 50.7-second six-month compute benchmark plus a conservative
2,100-second billed tail. The database threshold is exactly 1,800 seconds; the
five-minute Scheduler cadence can observe that threshold just under 300 seconds
later. Jobs inside the same 30-minute window share one tail.

| Wake sessions | Billed hours | Raw Worker compute | Worker after free allowance | Estimated total before $10 credit | After $10 credit |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 10 | 5.97 | $0.32 | $0.00 | about $0.00-$0.10 | about $0.00 |
| 25 | 14.94 | $0.81 | $0.00 | about $0.00-$0.10 | about $0.00 |
| 50 | 29.87 | $1.61 | $0.00 | about $0.00-$0.10 | about $0.00 |
| 100 | 59.74 | $3.22 | $0.00 | about $0.00-$0.10 | about $0.00 |

All four cases consume at most 215,070 vCPU-seconds and 215,070 GiB-seconds,
below the documented Worker Pool free allowances (384,204 vCPU-seconds and
728,744 GiB-seconds per billing account, valued using us-central1 rates). Low
internal web/controller traffic is expected inside Cloud Run request-based free
usage. One Scheduler job is inside the account-level three-job allowance. Five
active secret versions and low accesses fit the six-version/10,000-access Secret
Manager allowance. Low logs and occasional maintenance executions are expected
inside their allowances. Artifact storage is free through 0.5 GB, then $0.10 per
GB-month; the table reserves up to roughly $0.10 for small excess storage.

These are planning estimates, not a spend cap or a cloud measurement. They
exclude tax, currency conversion, external egress surprises, and other projects'
use of account-level allowances. The Free Trial is not counted. The separate
Google AI Pro $10 monthly Cloud credit covers the residual planning range if the
benefit applies to these SKUs. Configure a billing budget/alerts, max counts, log
retention, and Artifact Registry cleanup before provisioning.

Official references:

- https://cloud.google.com/run/pricing
- https://docs.cloud.google.com/run/docs/configuring/workerpools/manual-scaling
- https://docs.cloud.google.com/run/docs/reference/rest/v2/projects.locations.workerPools
- https://docs.cloud.google.com/run/docs/authenticating/service-to-service
- https://docs.cloud.google.com/scheduler/docs/http-target-auth
- https://cloud.google.com/scheduler/pricing
- https://cloud.google.com/artifact-registry/pricing
- https://cloud.google.com/secret-manager/pricing
