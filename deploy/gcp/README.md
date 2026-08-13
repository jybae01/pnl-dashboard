# Google Cloud staging deployment runbook

This directory prepares but does not create Google Cloud resources. All commands
under **Provisioning (next approved goal only)** are intentionally deferred.

## Architecture

```text
Browser (one managed HTTPS origin)
  -> Cloud Run service `pnl-web` (min 0, max 2, concurrency 4, timeout 180s)
       -> ingress `edge`: Caddy HTTP :$PORT, React static, /api reverse proxy
       -> sidecar `bff`: FastAPI localhost:8000, 1 vCPU/2 GiB
  -> external Supabase staging: Database, Auth state, private Storage, pgmq

Cloud Run Worker Pool `pnl-worker` (demand-only 0/1, 1 vCPU/1 GiB)
  -> pgmq claim/lease/heartbeat/retry -> unpublished Result

Private Cloud Run service `pnl-worker-controller` (min 0, max 1)
  -> Worker Pool get/update only; five-minute Scheduler reconciliation

Cloud Run Job `pnl-maintenance` (manual, default dry-run, 1 task)
  -> controlled cleanup/recovery RPCs
```

Cloud Run terminates TLS. The edge image listens on plaintext HTTP `$PORT` and
does not reuse the local Caddy CA/TLS configuration. The BFF sidecar has no
Cloud Run container port and no public URL. React uses an empty
`VITE_BFF_BASE_URL`, so cookies, CSRF, login/logout, Admin/Viewer, and every API
call remain same-origin.

All instances use Supabase as authoritative shared state. Scaling the service
therefore preserves Phase B BFF replica semantics without naming physical
`bff-a`/`bff-b` services. Session, logout, lockout, audit, Forecast permits,
published defaults, model identity/SHA, Storage, and pgmq remain unchanged.

## Resource rationale

Cloud Run assigns one fixed limit per container rather than changing resources
per endpoint. The selected BFF limit covers these distinct load classes:

| Load class | Evidence / boundary | Configuration consequence |
| --- | --- | --- |
| Idle | min instances 0; no availability requirement for a warm web instance | request-based billing and cold starts accepted |
| Normal API/auth | mostly I/O and shared Supabase state | service concurrency 4 |
| Upload/parser | isolated parser can reserve 768 MiB; owned temp is capped at 512 MiB | parser concurrency 1 and 2 GiB BFF limit |
| Evidence XLSX | generated file output remains inside the same bounded temp path | no separate unbounded disk path |
| Forecast six months | approximately 50.7 seconds and 328.6 MiB sampled RSS | application 120s ceiling and service 180s timeout |

- Web edge: 1 vCPU/512 MiB. Its workload needs far less CPU and memory. Cloud Run
  supports sidecars in either execution generation, but this profile deliberately
  selects gen2 for full Linux compatibility and sustained parser/Forecast work.
  Gen2 requires at least 512 MiB, while a sub-1-vCPU container would require gen1
  and service concurrency 1. The selected limits preserve concurrency 4 and are
  the smallest compatible with this chosen profile. Request-based billing
  prevents idle CPU charges with min instances 0.
- BFF: 1 vCPU/2 GiB; Phase B six-month Forecast sampled approximately 328.6 MiB
  RSS and 50.7 seconds, while parser isolation can reserve 768 MiB and bounded
  temp/cache volumes can consume memory. Concurrency 4 permits normal I/O while
  parser concurrency and global Forecast concurrency stay at 1.
- Request timeout: 180 seconds at both Cloud Run and edge, with the application
  Forecast ceiling kept at 120 seconds. This admits the proven six-month run
  with cleanup margin and does not approve more than six consecutive months.
- Worker: 1 vCPU/1 GiB when awake, matching the Phase B passing container ceiling. Phase B
  did not capture a worker-process-only RSS sample, so 1 GiB is a conservative
  proven ceiling rather than a measured minimum; record CPU/RSS during the cloud
  canary before considering a reduction. It is a continuous non-HTTP pgmq
  consumer and is not moved into the BFF, Scheduler, or Streamlit.
- Maintenance: 1 vCPU/1 GiB, 15-minute task timeout, no retries, one task. The
  stored command is dry-run; `--apply` is an explicit per-execution override.

Worker Pools are a direct fit for the non-HTTP consumer, but do not demand-scale
themselves. The manifest starts at zero. Only a committed pgmq-backed Analysis
request asks the private controller for one instance; a five-minute reconciler
repairs wake failures and returns an all-clear pool to zero after 30 continuous
minutes without worker-required activity. See `worker-lifecycle.md` for the
generation-based sleep/enqueue race contract, emergency recovery, IAM, and cost.
Platform restart plus durable pgmq leases/heartbeats/retries remain the processing
correctness mechanism. Deployment success is not workload health, so logs and a
queue canary are mandatory.

The BFF temp root is a 512 MiB size-limited in-memory volume and also enforces
the application 512 MiB quota. Cloud Run's writable root filesystem is otherwise
memory-backed and has no exact per-path hard limit, so all application-owned
workbook/temp/cache paths are redirected to bounded volumes. The BFF container
limit is the final fail-closed ceiling. This is equivalent for owned temp data,
not a claim that Cloud Run makes the whole root filesystem read-only.

## Proxy and auth trust contract

The initial staging service uses `BFF_PROXY_MODE=direct` and no trusted proxy
CIDRs. The BFF sees only its localhost edge peer and ignores `Forwarded`,
`X-Forwarded-For`, and `X-Real-IP`. The edge removes inbound values for those
headers as defense in depth; proxy-generated forwarding metadata, if any, is
still ignored by the BFF.
This yields one conservative, shared Supabase lockout bucket across all staging
clients. It cannot be bypassed by spoofed forwarding headers, but one abusive
client can lock out all users for the configured window. Per-client IP lockout
requires a later approved external load balancer/trusted identity design; it is
not inferred from undocumented Cloud Run proxy addresses.

Cookies remain `Secure`, `HttpOnly`, and `SameSite=Strict`. Production CORS has
one exact Cloud Run origin. Because a new service URL is learned only after its
first creation, bootstrap with `https://bootstrap.invalid`, read the generated
URI, immediately render a second revision with that exact origin, and do not run
login acceptance until the second revision is serving.

## Region decision

Both `asia-northeast3` (Seoul) and `asia-southeast1` (Singapore) provide Cloud
Run services, Worker Pools, Jobs, Artifact Registry, and Secret Manager and are
Tier 2. The existing Supabase staging project is in AWS `ap-southeast-1`.
Database, Storage, Auth/session, lockout, queue, and Worker traffic cross that
boundary repeatedly, so co-locating the Google workload in Singapore is the
lower-latency default even though Seoul is closer to Korean users.

`GOOGLE CLOUD RECOMMENDED REGION = asia-southeast1`

This is a recommendation, not a provisioned choice. Confirm it immediately
before deployment with a small HTTPS latency probe from each candidate if the
user wants empirical comparison.

## Build strategy

Selected: local Docker Buildx -> Artifact Registry. This reuses the tested local
Docker workflow, requires no GitHub push, and uploads images rather than the
source tree. Build `linux/amd64`; Cloud Run requires an amd64-compatible image.
The source Dockerfile remains multi-platform-capable for local Linux, but ARM64
alone is not a valid Cloud Run artifact.

Two images are sufficient:

- `pnl-web`: React build plus HTTP-only Caddy ingress.
- `pnl-runtime`: the existing Python image reused by BFF, Worker, and Job with
  different runtime arguments.

Cloud Build is a valid fallback after `.gcloudignore` inspection, but is not
selected. GitHub-connected builds remain excluded until push is separately
approved. Deploy only digest-pinned references; never deploy mutable tags.

## Render and offline validation

`render.ps1` only validates inputs and renders ignored manifests. It never calls
Google Cloud.

```powershell
./deploy/gcp/render.ps1 `
  -ProjectId 'exact-project-id' `
  -ProjectNumber '123456789012' `
  -Region 'asia-southeast1' `
  -SupabaseUrl 'https://project-ref.supabase.co' `
  -CloudRunOrigin 'https://bootstrap.invalid' `
  -WorkerControllerUrl 'https://controller-bootstrap.invalid' `
  -WebImage 'asia-southeast1-docker.pkg.dev/exact-project-id/pnl-staging/pnl-web@sha256:<64-hex>' `
  -RuntimeImage 'asia-southeast1-docker.pkg.dev/exact-project-id/pnl-staging/pnl-runtime@sha256:<64-hex>' `
  -SourceCommit '1e478b68b4f73dc6b41e2681cb6238a87d1e0427' `
  -ReleaseStage 'v1-production-pilot' `
  -BusinessGate 'passed'
```

Review every rendered file, confirm no unresolved token, then run the repository
contract tests. The `rendered/` directory is ignored by Git, Docker, and gcloud.

## Provisioning (next approved goal only)

The following steps create or mutate cloud resources. Do not execute them in the
current readiness goal.

Use a dedicated production gcloud configuration or pass
`--project=EXACT_PROJECT_ID` on every write. The staging project may still be
the operator's default, so every mutating step must first assert the production
project ID and number. Ordinary deploy steps should impersonate the scoped
`pnl-deployer` service account; keep project creation, billing attachment, API
enablement, service-account creation, and Scheduler OIDC bootstrap as explicit
human bootstrap operations. Never grant Owner, Editor, or broad Cloud Run Admin
to a runtime or deployer account.

1. Confirm the exact project ID; do not use the display name as evidence:

   ```powershell
   gcloud projects list
   gcloud config set project EXACT_PROJECT_ID
   gcloud config get-value project
   gcloud projects describe EXACT_PROJECT_ID --format='value(projectNumber)'
   ```

2. Obtain explicit approval for `asia-southeast1`, resource creation, and the
   project-specific Pricing Calculator result. Create billing alerts and, if the
   billing account is eligible for the Preview, a Cloud Run spend-cap budget
   below the absolute monthly limit. Spend caps can overshoot due to latency.

3. Enable only required APIs:

   ```powershell
   gcloud services enable run.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com iam.googleapis.com cloudscheduler.googleapis.com
   ```

   The human bootstrap operator must already have
   `serviceusage.services.enable` (normally `roles/serviceusage.serviceUsageAdmin`)
   for this step. This permission is not part of the runtime or deployer identity.

4. Create one regional Docker repository and first apply the cleanup policy in
   dry-run mode:

   ```powershell
   gcloud artifacts repositories create pnl-staging --repository-format=docker --location=asia-southeast1
   gcloud artifacts repositories set-cleanup-policies pnl-staging --location=asia-southeast1 --policy=deploy/gcp/cleanup-policy.json --dry-run
   ```

   Inspect dry-run audit results for at least one policy cycle before using
   `--no-dry-run` in a later controlled change.

5. Create six user-managed service accounts. The human bootstrap operator needs
   `iam.serviceAccounts.create` (normally `roles/iam.serviceAccountCreator`, or a
   separately approved equivalent) for creation; `roles/run.developer` does not
   grant it. Runtime accounts receive no project role:

   ```powershell
   gcloud iam service-accounts create pnl-web --display-name='PNL web runtime'
   gcloud iam service-accounts create pnl-worker --display-name='PNL worker runtime'
   gcloud iam service-accounts create pnl-maintenance --display-name='PNL maintenance runtime'
   gcloud iam service-accounts create pnl-worker-controller --display-name='PNL worker lifecycle controller'
   gcloud iam service-accounts create pnl-worker-reconciler --display-name='PNL worker reconciler caller'
   gcloud iam service-accounts create pnl-deployer --display-name='PNL deployment operator'
   ```

   Service-account creation uses the bootstrap operator permission above; it is
   separate from later deployment permissions. Grant the deployer
   `roles/run.developer` only for application deployment and narrow it after
   creation if supported resource-level permissions still cover updates. Grant
   `roles/artifactregistry.writer` only on
   `pnl-staging`, and
   `roles/iam.serviceAccountUser` on the runtime accounts. Apply those
   grants at the narrowest supported resource scope; do not grant Owner, Editor,
   or service-agent roles. Do not create service-account keys.

6. Create the five secrets named in `secret-contract.md`. Add values only via
   interactive stdin, one at a time:

   ```powershell
   gcloud secrets create SECRET_NAME --replication-policy=automatic
   gcloud secrets versions add SECRET_NAME --data-file=-
   gcloud secrets add-iam-policy-binding SECRET_NAME --member='serviceAccount:RUNTIME_ACCOUNT@EXACT_PROJECT_ID.iam.gserviceaccount.com' --role='roles/secretmanager.secretAccessor'
   ```

   Grant Secret Accessor per secret: web gets all five; worker, maintenance, and
   worker-controller get only `pnl-supabase-secret-key`. The reconciler gets no
   secret. No runtime account receives broad Google API permission.

7. Prefer exact-byte promotion of the Golden-aligned staging indexes into the
   production repository. Grant the promotion principal temporary read access
   to the staging repository and writer access only to the production
   repository, then remove any newly granted staging access. Do not rebuild
   unless exact promotion is technically unavailable:

   ```powershell
   gcloud auth configure-docker asia-southeast1-docker.pkg.dev
   docker buildx imagetools create --prefer-index --tag asia-southeast1-docker.pkg.dev/EXACT_PROJECT_ID/pnl-production/pnl-web:v1.0.0-rc1 asia-southeast1-docker.pkg.dev/pnl-dashboard-staging/pnl-staging/pnl-web@sha256:36502f01eed08012e2c0efb5f4756212c72b1373a390b5ed9bb78e59741d8330
   docker buildx imagetools create --prefer-index --tag asia-southeast1-docker.pkg.dev/EXACT_PROJECT_ID/pnl-production/pnl-runtime:v1.0.0-rc1 asia-southeast1-docker.pkg.dev/pnl-dashboard-staging/pnl-staging/pnl-runtime@sha256:4121d8f3fe25b555ea30355110008c4b6e5ac9cb2ecbc065f164bde2cd5ce485
   gcloud artifacts docker images describe asia-southeast1-docker.pkg.dev/EXACT_PROJECT_ID/pnl-production/pnl-web:v1.0.0-rc1 --format='value(image_summary.digest)'
   gcloud artifacts docker images describe asia-southeast1-docker.pkg.dev/EXACT_PROJECT_ID/pnl-production/pnl-runtime:v1.0.0-rc1 --format='value(image_summary.digest)'
   docker buildx imagetools inspect asia-southeast1-docker.pkg.dev/EXACT_PROJECT_ID/pnl-production/pnl-web:v1.0.0-rc1
   docker buildx imagetools inspect asia-southeast1-docker.pkg.dev/EXACT_PROJECT_ID/pnl-production/pnl-runtime:v1.0.0-rc1
   ```

   The destination OCI index digests must equal the source indexes, and the
   Linux/AMD64 child manifests must remain identical. Deploy the destination
   digest references, never the mutable tags.

8. Render with the two digests, bootstrap origins, and create the zero-instance
   Worker Pool plus private controller first. Create its exact three-permission
   custom role and bind it only on `pnl-worker`; do not grant `allUsers`:

   ```powershell
   gcloud iam roles create pnlWorkerLifecycleController --project=EXACT_PROJECT_ID --file=deploy/gcp/worker-controller-role.yaml
   gcloud iam roles create pnlWorkerLifecycleOperationViewer --project=EXACT_PROJECT_ID --file=deploy/gcp/worker-operation-viewer-role.yaml
   gcloud config set run/region asia-southeast1
   gcloud run worker-pools replace deploy/gcp/rendered/worker-pool.yaml
   gcloud run services replace deploy/gcp/rendered/worker-controller.yaml --region=asia-southeast1
   gcloud run worker-pools add-iam-policy-binding pnl-worker --region=asia-southeast1 --member='serviceAccount:pnl-worker-controller@EXACT_PROJECT_ID.iam.gserviceaccount.com' --role='projects/EXACT_PROJECT_ID/roles/pnlWorkerLifecycleController'
   gcloud projects add-iam-policy-binding EXACT_PROJECT_ID --member='serviceAccount:pnl-worker-controller@EXACT_PROJECT_ID.iam.gserviceaccount.com' --role='projects/EXACT_PROJECT_ID/roles/pnlWorkerLifecycleOperationViewer'
   gcloud iam service-accounts add-iam-policy-binding pnl-worker@EXACT_PROJECT_ID.iam.gserviceaccount.com --member='serviceAccount:pnl-worker-controller@EXACT_PROJECT_ID.iam.gserviceaccount.com' --role=roles/iam.serviceAccountUser
   gcloud run services add-iam-policy-binding pnl-worker-controller --region=asia-southeast1 --member='serviceAccount:pnl-web@EXACT_PROJECT_ID.iam.gserviceaccount.com' --role=roles/run.invoker
   gcloud run services add-iam-policy-binding pnl-worker-controller --region=asia-southeast1 --member='serviceAccount:pnl-worker-reconciler@EXACT_PROJECT_ID.iam.gserviceaccount.com' --role=roles/run.invoker
   $controllerUrl = gcloud run services describe pnl-worker-controller --region=asia-southeast1 --format='value(status.url)'
   ```

9. Render again with `$controllerUrl`, then create the initial Web service while
   it is still private. A brand-new service has no previous revision that can
   retain 100% traffic, so its first revision cannot be treated as a zero-percent
   traffic canary. Invoke that private revision with an operator identity token
   and verify health, SPA, BFF connectivity, labels, and UID volume probes. Do
   not add `allUsers` yet. Verify `source-commit`, `release-stage`, and
   `business-gate` labels on the service, revision, Worker Pool, controller, and
   maintenance Job; do not reuse the staging release-stage label.

   ```powershell
   gcloud run services replace deploy/gcp/rendered/cloud-run-web.yaml --region=asia-southeast1
   $candidateRevision = gcloud run revisions list --service=pnl-web --region=asia-southeast1 --sort-by='~metadata.creationTimestamp' --limit=1 --format='value(metadata.name)'
   $privateUrl = gcloud run services describe pnl-web --region=asia-southeast1 --format='value(status.url)'
   $identityToken = gcloud auth print-identity-token --audiences=$privateUrl
   Invoke-WebRequest -Headers @{ Authorization = "Bearer $identityToken" } -Uri "$privateUrl/health/ready"
   ```

   Render once more with `$privateUrl` as the exact `CloudRunOrigin` and replace
   the service while it is still private. Re-run the authenticated health, SPA,
   BFF, cookie/origin, label, and volume checks against that exact-origin
   revision. Only after those checks pass may the operator add the public
   invoker binding and begin the Access Code smoke. This avoids relying on
   `gcloud run services replace` for an implicit zero-traffic rollout and keeps
   the URL non-public until the final configuration is ready.

   ```powershell
   gcloud run services replace deploy/gcp/rendered/cloud-run-web.yaml --region=asia-southeast1
   $candidateRevision = gcloud run revisions list --service=pnl-web --region=asia-southeast1 --sort-by='~metadata.creationTimestamp' --limit=1 --format='value(metadata.name)'
   $identityToken = gcloud auth print-identity-token --audiences=$privateUrl
   Invoke-WebRequest -Headers @{ Authorization = "Bearer $identityToken" } -Uri "$privateUrl/health/ready"
   gcloud run services add-iam-policy-binding pnl-web --region=asia-southeast1 --member=allUsers --role=roles/run.invoker
   gcloud run services describe pnl-web --region=asia-southeast1 --format='value(status.traffic,status.url)'
   ```

   Verify `/health/live`, `/health/ready`, SPA fallback, and that no separate BFF
   URL or port exists. Before claiming readiness, verify the effective non-root
   identity and create/delete probes under `/var/tmp/pnl` and `/app/data`. Cloud
   Run owns volume creation and the manifests cannot express an `emptyDir`
   UID/GID/mode; a permission failure must block acceptance and trigger a
   documented supported mount strategy, not a root-container fallback. Then test
   login, CSRF mutation, logout, cross-replica session, and distributed lockout.

10. Create the five-minute reconciliation schedule with OIDC; it is not a warm
    schedule and has no weekday/weekend branches:

    The identity running this provisioning step needs
    `iam.serviceAccounts.actAs` on only `pnl-worker-reconciler` (normally a
    resource-level `roles/iam.serviceAccountUser` binding). Verify that the
    Google-managed Cloud Scheduler service agent retains
    `roles/cloudscheduler.serviceAgent`; do not grant that service-agent role to
    a human or runtime account.

    ```powershell
    gcloud iam service-accounts add-iam-policy-binding pnl-worker-reconciler@EXACT_PROJECT_ID.iam.gserviceaccount.com --member='user:BOOTSTRAP_OPERATOR_EMAIL' --role=roles/iam.serviceAccountUser
    gcloud scheduler jobs create http pnl-worker-reconcile --location=asia-southeast1 --schedule='*/5 * * * *' --time-zone=Etc/UTC --http-method=POST --uri="$controllerUrl/v1/worker/reconcile" --oidc-service-account-email='pnl-worker-reconciler@EXACT_PROJECT_ID.iam.gserviceaccount.com' --oidc-token-audience="$controllerUrl" --attempt-deadline=30s --max-retry-attempts=3 --max-retry-duration=2m --min-backoff=5s --max-backoff=30s --max-doublings=2
    gcloud run worker-pools describe pnl-worker --region=asia-southeast1
    gcloud run worker-pools logs read pnl-worker --region=asia-southeast1 --limit=100
    ```

    Confirm zero at rest. Submit one synthetic Analysis and observe durable pgmq
    enqueue before zero-to-one, startup, lease/heartbeat, unpublished completion,
    Admin publication, Result read, and automatic one-to-zero once the durable
    idle clock reaches 30 minutes. With a five-minute reconciler, the control
    request is normally issued between 30 and 35 minutes after last activity;
    the policy threshold remains exactly 30 minutes. Deployment success alone
    is not health evidence.

    The canary must also log `id` and prove create/delete access to `/tmp` and
    `/app/data` as UID 10001 before queue acceptance. Do not infer permissions
    from successful deployment alone.

11. Create the maintenance Job. Its normal execution is dry-run. Review its JSON
    report before a separately authorized apply override:

    ```powershell
    gcloud run jobs replace deploy/gcp/rendered/maintenance-job.yaml --region=asia-southeast1
    gcloud run jobs execute pnl-maintenance --region=asia-southeast1 --wait
    gcloud run jobs execute pnl-maintenance --region=asia-southeast1 --args=python,-m,forecast.maintenance,cleanup,--apply --wait
    ```

    Its first dry-run must prove UID 10001 create/delete access to
    `/var/tmp/pnl` and `/app/data`; otherwise stop before controlled apply.

12. Run the complete staging acceptance path: managed HTTPS, React/BFF, remote
    readiness, login/logout, lockout, synthetic Model upload/private Storage SHA,
    publication, Analysis/pgmq/independent Worker/Result/Admin/Viewer,
    Presentation/History/Evidence XLSX/P&L, audit/correlation, and maintenance.
    Validate Forecast sync mode: 1 and 6 months execute; 7 and 12 fail before
    reservation. Never upload a company workbook.

## Health, operations, rollback, and rotation

- Web readiness is `/health/ready`; liveness is `/health/live`. A 200 readiness
  response includes the remote Supabase dependency check.
- Worker health is proved by process survival, logs, and a synthetic queue canary;
  Google explicitly notes that deployment success alone is not a health check.
- Keep structured INFO logs and correlation IDs. Never log request bodies,
  cookies, codes, secret files, signed Storage URLs, or raw credentials.
- Roll web back by routing traffic to the last known-good immutable revision, or
  replace with the prior digest-pinned manifest. Roll Worker/Job back by replacing
  their prior reviewed digest manifests. Do not use mutable image tags.
- Rotate secrets by adding a version, replacing/restarting all consumers,
  verifying acceptance, and disabling the old version. Destroy only after the
  rollback window.
- Keep unused service revisions without traffic only for the rollback window;
  then delete intentionally. Cloud Run automatically limits revision history,
  but that is not a retention policy.

## Teardown (separate explicit approval)

Teardown is destructive and is never part of readiness or ordinary deployment.
After resolving the exact project and region, disable the Worker Pool first,
export audit evidence, then delete Scheduler job, controller, Job, Worker Pool,
Service, secrets, service
accounts, and finally Artifact Registry. Secret destruction and repository
deletion are irreversible. Supabase and user-owned OCI resources are out of
scope and must not be changed.

Official references:

- https://docs.cloud.google.com/run/docs/deploying
- https://docs.cloud.google.com/run/docs/deploy-worker-pools
- https://docs.cloud.google.com/run/docs/configuring/workerpools/manual-scaling
- https://docs.cloud.google.com/run/docs/authenticating/service-to-service
- https://docs.cloud.google.com/scheduler/docs/http-target-auth
- https://docs.cloud.google.com/run/docs/container-contract
- https://docs.cloud.google.com/run/docs/configuring/request-timeout
- https://docs.cloud.google.com/run/docs/execute/jobs
- https://docs.cloud.google.com/run/docs/configuring/services/secrets
- https://docs.cloud.google.com/run/docs/configuring/workerpools/secrets
- https://docs.cloud.google.com/run/docs/securing/service-identity
