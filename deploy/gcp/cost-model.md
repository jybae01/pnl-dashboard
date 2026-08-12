# Google Cloud staging cost model

Estimate date: 2026-08-12. Currency: USD. This is a planning estimate, not a
quote. Seoul and Singapore are both Cloud Run Tier 2 regions. Free allowances
are billing-account aggregates, so another project can consume them first.

## Selected configuration

| Resource | Planning assumption | Monthly estimate |
| --- | --- | ---: |
| Cloud Run web | request-based billing, min 0, max 2, low internal traffic; edge 1 vCPU/512 MiB plus BFF 1 vCPU/2 GiB only while active | approximately $0; allow $0-$1 for compute/requests and internet egress |
| Worker Pool | one continuous instance, 1 vCPU/1 GiB | approximately $33.60-$34.13 after the Worker Pool free allowance in Singapore |
| Maintenance Job | manual, rare, 1 vCPU/1 GiB, 15-minute ceiling | approximately $0 under the jobs free allowance |
| Artifact Registry | two digest-pinned images, keep three recent versions, planning storage 1.5 GiB | approximately $0.10 (first 0.5 GiB free, then $0.10/GiB-month) |
| Cloud Build | not used by the selected local-build strategy | $0 |
| Secret Manager | five active versions and fewer than 10,000 accesses | $0 (within six-version/access free allowances) |
| Cloud Logging | low internal volume, default 30-day retention, below 50 GiB/month | $0 |

The official Singapore Worker Pool rates are $0.000013493 per vCPU-second and
$0.000001482 per GiB-second. At one continuously allocated 1 vCPU/1 GiB instance,
raw metered compute is approximately $38.82 for 30 days or $39.35 for 730 hours.
The published Worker Pool free allowance is applied as a spending discount at
Tier 1 rates; its CPU and memory components total approximately $5.22 when the
billing account has not consumed them elsewhere. That yields approximately
$33.60-$34.13 for the Worker Pool. The official 1 vCPU/512 MiB Tier 1 example is
$11.61 after free allowance ($16.83 before it), but is not this deployment's
region or memory size.

Estimated monthly raw metered cost before always-free allowances or user-specific
credits: **approximately $39-$41** at low internal usage. Estimated Google Cloud
charge after published always-free allowances but before the user's credits:
**approximately $34-$36**. Capture an actual project Pricing Calculator/SKU quote
immediately before provisioning because billing-account free allowances can be
consumed by another project.

Google AI Pro monthly Cloud credit: **$10**, treated as a separate monthly
offset because the user reports the benefit active. Estimated steady-state cash
after that credit: **$24-$26/month**, before tax and currency conversion.

Free Trial credit is intentionally excluded from steady-state economics. It can
temporarily cover the bill but is not a durable operating-cost reduction.

## Cost verdict and controls

`GOOGLE CLOUD COST FIT = FAIL` for the desired approximately-zero additional
cash target while a reliable continuous Worker Pool instance is required.
Stopping the worker (`instances=0`) or running it only during office hours would
reduce cost but weakens continuous queue latency/availability, so it is not the
selected production-like topology.

Before provisioning, capture a project-specific Pricing Calculator result for
`asia-southeast1`, create a Cloud Run spend-cap budget if the Preview option is
eligible for the billing account, add alerts at 50/80/100%, retain `maxScale=2`,
retain Worker Pool instances at exactly 1, test Artifact Registry cleanup in
dry-run mode, and keep Cloud Logging at its default 30-day retention. Spend caps
and budgets have enforcement/reporting latency; they are guardrails, not a
guarantee of zero overage.

Official inputs:

- https://cloud.google.com/run/pricing
- https://cloud.google.com/artifact-registry/pricing
- https://cloud.google.com/build/pricing
- https://cloud.google.com/secret-manager/pricing
- https://cloud.google.com/products/observability/pricing
- https://docs.cloud.google.com/billing/docs/how-to/budgets-spend-caps
