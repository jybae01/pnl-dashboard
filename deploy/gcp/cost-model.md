# Google Cloud staging cost model

Estimate date: 2026-08-12. Currency: USD. This is a planning estimate, not a
quote. Billing-account allowances may be consumed by other projects first.

The former continuous/working-hours Worker estimate is retired. V1 starts
`pnl-worker` at zero and creates a wake session only for committed asynchronous
Analysis demand. A session includes the measured 50.7-second six-month compute
proxy plus a conservative 35-minute billed tail: the exact durable eligibility
threshold is 30 minutes and the five-minute reconciler can observe it just under
five minutes later. Jobs less than 30 minutes apart share one tail rather than
duplicating it.

| Sessions/month | Worker hours | Raw 1 vCPU/1 GiB Singapore cost | After Worker free allowance | Total before AI Pro credit | Cash after $10 credit |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 10 | 5.97 | $0.32 | $0.00 | about $0.00-$0.10 | about $0.00 |
| 25 | 14.94 | $0.81 | $0.00 | about $0.00-$0.10 | about $0.00 |
| 50 | 29.87 | $1.61 | $0.00 | about $0.00-$0.10 | about $0.00 |
| 100 | 59.74 | $3.22 | $0.00 | about $0.00-$0.10 | about $0.00 |

Raw Worker cost uses official Singapore rates of $0.000013493/vCPU-second and
$0.000001482/GiB-second. Even 100 separate wake sessions use 215,070 seconds of
each resource, below the published Worker Pool allowances of 384,204 vCPU-
seconds and 728,744 GiB-seconds. This assumes the account allowance remains.

| Other component | Low-internal-use gross planning range | After published allowance |
| --- | ---: | ---: |
| Web (min 0, request-based) | $0-$1.00 | approximately $0 |
| Controller (min 0; Analysis + 5-minute calls) | below request/compute allowances | approximately $0 |
| Artifact Registry (live staging: about 0.215 GiB) | $0.00 at current size | $0.00 within first 0.5 GiB |
| Scheduler (one job) | $0.10 list price | $0 within three-job allowance |
| Secret Manager (five active versions) | $0.30 list price plus low access | $0 within six versions/10,000 accesses |
| Maintenance Job | a few minutes of CPU/RAM when manually run | approximately $0 |
| Cloud Logging | low volume | approximately $0 within ingestion allowance |

Low internal web and controller traffic (min zero), the five-minute reconciler,
rare maintenance, and low logs are planned inside applicable free usage. One
Scheduler job fits the three-job account allowance. Five secret versions and
low access fit Secret Manager's six versions and 10,000 accesses. Artifact
Registry is free through 0.5 GiB then $0.10/GiB-month. The live repository
reported 230.554 MB (approximately 0.215 GiB) after the iterative staging
builds, so current stored artifact cost is $0; a small contingency remains
appropriate if later revisions cross the allowance. Cloud Build remains unused.

`GOOGLE CLOUD COST FIT = PASS_FOR_TARGET_BUDGET`

`EXPECTED STEADY-STATE CASH COST = APPROXIMATELY $0`

The reported Google AI Pro $10 monthly Cloud credit is a separate offset. Free
Trial credit is excluded. Taxes, currency conversion, network egress, other
projects' allowance use, and actual canary durations can change the bill.

Before provisioning: capture a project-specific calculator result, create
budget alerts, keep web max two/controller max one/Worker Pool zero-or-one,
retain the five-minute cost-leak reconciler, dry-run Artifact Registry cleanup,
and bound log retention. See `worker-lifecycle.md` for formulas and sources.
