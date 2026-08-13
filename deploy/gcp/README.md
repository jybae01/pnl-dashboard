# Google Cloud staging and isolated Production deployment runbook

This directory prepares but does not create Google Cloud resources. All commands
under **Provisioning (next approved goal only)** are intentionally deferred.

## Architecture

```text
Browser (one managed HTTPS origin)
  -> Cloud Run service `pnl-web` (min 0, max 2, concurrency 4, timeout 180s)
       -> ingress `edge`: Caddy HTTP :$PORT, React static, /api reverse proxy
       -> sidecar `bff`: FastAPI localhost:8000, 1 vCPU/2 GiB
  -> external Supabase environment: Database, Auth state, private Storage, pgmq

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

The Cloud Run service uses `BFF_PROXY_MODE=direct` and no trusted proxy
CIDRs. The BFF sees only its localhost edge peer and ignores `Forwarded`,
`X-Forwarded-For`, and `X-Real-IP`. The edge removes inbound values for those
headers as defense in depth; proxy-generated forwarding metadata, if any, is
still ignored by the BFF.
This yields one conservative, shared Supabase lockout bucket across all
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
  -WebImage 'asia-southeast1-docker.pkg.dev/exact-project-id/pnl-production/pnl-web@sha256:<64-hex>' `
  -RuntimeImage 'asia-southeast1-docker.pkg.dev/exact-project-id/pnl-production/pnl-runtime@sha256:<64-hex>' `
  -SourceCommit '1e478b68b4f73dc6b41e2681cb6238a87d1e0427' `
  -ReleaseStage 'v1-production-pilot' `
  -BusinessGate 'passed' `
  -DeploymentProfile 'production'
```

Review every rendered file, confirm no unresolved token, then run the repository
contract tests. The `rendered/` directory is ignored by Git, Docker, and gcloud.

## Isolated Production Supabase gate

Do not render or create Google runtime resources until a separately authenticated
Free Production organization/project exists and its ref differs from staging and
both legacy refs. Before applying SQL, pin the exact V1 chain:

```powershell
./deploy/gcp/verify-v1-migrations.ps1
```

The verifier requires all 18 files in lexical order and their frozen SHA-256
digests, including `202608120001_demand_only_worker_lifecycle.sql`. Apply that
exact chain once to the new empty Production project through the authenticated
Supabase management channel. Do not use a staging dump, skip a file, edit a
migration, or apply manual SQL. Before any Google deployment, capture remote
migration history proving 18/18 with no gap or duplicate, then verify RLS/ACL,
SECURITY DEFINER search paths, pgmq, private `pnl-models`, shared sessions and
lockout, publication, audit, and Worker lifecycle catalogs. A Security Advisor
warning or remote-history mismatch blocks provisioning.

## Provisioning

The following steps create or mutate cloud resources. Execute them only in an
explicitly approved provisioning goal and only after the isolated Supabase
Production identity exists.

Use a dedicated production gcloud configuration or pass
`--project=EXACT_PROJECT_ID` on every write. The staging project may still be
the operator's default, so every mutating step must first assert the production
project ID and number. Ordinary deploy steps should impersonate the scoped
`pnl-deployer` service account; keep project creation, billing attachment, API
enablement, service-account creation, and Scheduler OIDC bootstrap as explicit
human bootstrap operations. Never grant Owner, Editor, or broad Cloud Run Admin
to a runtime or deployer account.

1. Create the project only after the user selects the exact globally unique
   project ID, parent organization/folder, and billing account. The display name
   is not an ID. The commands below deliberately keep creation and billing link
   outside the future deployer identity:

   ```powershell
   $ProjectId = 'EXACT_PROJECT_ID'
   $ProductionConfiguration = "pnl-production-$ProjectId"
   gcloud config configurations create $ProductionConfiguration
   gcloud projects create $ProjectId --name='PNL Dashboard Production' --organization=EXACT_ORGANIZATION_ID --configuration=$ProductionConfiguration
   gcloud billing projects link $ProjectId --billing-account=EXACT_APPROVED_BILLING_ACCOUNT --configuration=$ProductionConfiguration --project=$ProjectId
   gcloud config set project $ProjectId --configuration=$ProductionConfiguration
   $ProjectNumber = gcloud projects describe $ProjectId --configuration=$ProductionConfiguration --project=$ProjectId --format='value(projectNumber)'
   ./deploy/gcp/assert-production-target.ps1 -ProjectId $ProjectId -ProjectNumber $ProjectNumber -Configuration $ProductionConfiguration

   function Invoke-ProdGcloud {
       & gcloud @args "--configuration=$ProductionConfiguration" "--project=$ProjectId"
       if ($LASTEXITCODE -ne 0) { throw "Production gcloud command failed." }
   }
   ```

   Use `--folder=EXACT_FOLDER_ID` instead of `--organization` only when the user
   explicitly selects that parent. Never infer a parent or billing account. Run
   the assertion again immediately before every mutating phase. Do not use raw
   `gcloud` for ordinary Production resource writes after this point.

2. Obtain explicit approval for `asia-southeast1`, resource creation, and the
   project-specific Pricing Calculator result. Create the approved monthly
   15,000 KRW project-filtered budget with 50%, 80%, and 100% alerts. A budget is
   an alert, not a hard cap. If the billing account is eligible for the Preview,
   a separately approved Cloud Run spend cap may add defense in depth; spend caps
   can still overshoot due to reporting latency.

   ```powershell
   gcloud billing budgets create --billing-account=EXACT_APPROVED_BILLING_ACCOUNT --display-name='pnl-production-monthly-15000-krw' --budget-amount=15000KRW --filter-projects="projects/$ProjectNumber" --threshold-rule=percent=0.5 --threshold-rule=percent=0.8 --threshold-rule=percent=1.0 --configuration=$ProductionConfiguration --project=$ProjectId
   ```

3. Enable only required APIs:

   ```powershell
   Invoke-ProdGcloud services enable run.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com iam.googleapis.com cloudscheduler.googleapis.com
   ```

   The human bootstrap operator must already have
   `serviceusage.services.enable` (normally `roles/serviceusage.serviceUsageAdmin`)
   for this step. This permission is not part of the runtime or deployer identity.

4. Create one regional Docker repository and first apply the cleanup policy in
   dry-run mode:

   ```powershell
   Invoke-ProdGcloud artifacts repositories create pnl-production --repository-format=docker --location=asia-southeast1
   Invoke-ProdGcloud artifacts repositories set-cleanup-policies pnl-production --location=asia-southeast1 --policy=deploy/gcp/cleanup-policy.json --dry-run
   ```

   Inspect dry-run audit results for at least one policy cycle before using
   `--no-dry-run` in a later controlled change.

5. Create six user-managed service accounts. The human bootstrap operator needs
   `iam.serviceAccounts.create` (normally `roles/iam.serviceAccountCreator`, or a
   separately approved equivalent) for creation; `roles/run.developer` does not
   grant it. Runtime accounts receive no project role:

   ```powershell
   Invoke-ProdGcloud iam service-accounts create pnl-web --display-name='PNL web runtime'
   Invoke-ProdGcloud iam service-accounts create pnl-worker --display-name='PNL worker runtime'
   Invoke-ProdGcloud iam service-accounts create pnl-maintenance --display-name='PNL maintenance runtime'
   Invoke-ProdGcloud iam service-accounts create pnl-worker-controller --display-name='PNL worker lifecycle controller'
   Invoke-ProdGcloud iam service-accounts create pnl-worker-reconciler --display-name='PNL worker reconciler caller'
   Invoke-ProdGcloud iam service-accounts create pnl-deployer --display-name='PNL deployment operator'
   ```

   Service-account creation uses the bootstrap operator permission above; it is
   separate from later deployment permissions. Grant the deployer
   `roles/run.developer` only for application deployment and narrow it after
   creation if supported resource-level permissions still cover updates. Grant
   `roles/artifactregistry.writer` only on
   `pnl-production`, and
   `roles/iam.serviceAccountUser` on the runtime accounts. Apply those
   grants at the narrowest supported resource scope; do not grant Owner, Editor,
   or service-agent roles. Do not create service-account keys.

6. Create the five empty secret containers named in `secret-contract.md`, then
   run the Production-only no-echo helper. It checks the exact project ID and
   number, rejects the staging project, refuses an already-enabled version, and
   sends each value to gcloud only through redirected stdin:

   ```powershell
   Invoke-ProdGcloud secrets create SECRET_NAME --replication-policy=automatic
   ./deploy/gcp/register-production-secrets.ps1 -ProjectId $ProjectId -ProjectNumber $ProjectNumber -Configuration $ProductionConfiguration
   Invoke-ProdGcloud secrets add-iam-policy-binding SECRET_NAME --member='serviceAccount:RUNTIME_ACCOUNT@EXACT_PROJECT_ID.iam.gserviceaccount.com' --role='roles/secretmanager.secretAccessor'
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
   gcloud auth configure-docker asia-southeast1-docker.pkg.dev --configuration=$ProductionConfiguration
   $webTag = "asia-southeast1-docker.pkg.dev/$ProjectId/pnl-production/pnl-web:golden-1e478b68b4f7"
   $runtimeTag = "asia-southeast1-docker.pkg.dev/$ProjectId/pnl-production/pnl-runtime:golden-1e478b68b4f7"
   docker buildx imagetools create --prefer-index --tag $webTag asia-southeast1-docker.pkg.dev/pnl-dashboard-staging/pnl-staging/pnl-web@sha256:36502f01eed08012e2c0efb5f4756212c72b1373a390b5ed9bb78e59741d8330
   docker buildx imagetools create --prefer-index --tag $runtimeTag asia-southeast1-docker.pkg.dev/pnl-dashboard-staging/pnl-staging/pnl-runtime@sha256:4121d8f3fe25b555ea30355110008c4b6e5ac9cb2ecbc065f164bde2cd5ce485
   $webDigest = Invoke-ProdGcloud artifacts docker images describe $webTag --format='value(image_summary.digest)'
   $runtimeDigest = Invoke-ProdGcloud artifacts docker images describe $runtimeTag --format='value(image_summary.digest)'
   if ($webDigest -ne 'sha256:36502f01eed08012e2c0efb5f4756212c72b1373a390b5ed9bb78e59741d8330') { throw 'Web index digest changed during promotion.' }
   if ($runtimeDigest -ne 'sha256:4121d8f3fe25b555ea30355110008c4b6e5ac9cb2ecbc065f164bde2cd5ce485') { throw 'Runtime index digest changed during promotion.' }
   docker buildx imagetools inspect "$webTag"
   docker buildx imagetools inspect "$runtimeTag"
   $webImage = "$($webTag.Split(':')[0])@$webDigest"
   $runtimeImage = "$($runtimeTag.Split(':')[0])@$runtimeDigest"
   ```

   The commit-derived tag is audit metadata, not the deployment reference. The
   destination OCI index digests must equal the source indexes, and the
   Linux/AMD64 child manifests must remain identical. Deploy the destination
   digest references, never the mutable tags.

8. Render with the two digests, bootstrap origins, and create the zero-instance
   Worker Pool plus private controller first. Create its exact three-permission
   custom role and bind it only on `pnl-worker`; do not grant `allUsers`:

   ```powershell
   Invoke-ProdGcloud iam roles create pnlWorkerLifecycleController --file=deploy/gcp/worker-controller-role.yaml
   Invoke-ProdGcloud iam roles create pnlWorkerLifecycleOperationViewer --file=deploy/gcp/worker-operation-viewer-role.yaml
   Invoke-ProdGcloud run worker-pools replace deploy/gcp/rendered/worker-pool.yaml --region=asia-southeast1
   Invoke-ProdGcloud run services replace deploy/gcp/rendered/worker-controller.yaml --region=asia-southeast1
   Invoke-ProdGcloud run worker-pools add-iam-policy-binding pnl-worker --region=asia-southeast1 --member='serviceAccount:pnl-worker-controller@EXACT_PROJECT_ID.iam.gserviceaccount.com' --role='projects/EXACT_PROJECT_ID/roles/pnlWorkerLifecycleController'
   Invoke-ProdGcloud projects add-iam-policy-binding $ProjectId --member='serviceAccount:pnl-worker-controller@EXACT_PROJECT_ID.iam.gserviceaccount.com' --role='projects/EXACT_PROJECT_ID/roles/pnlWorkerLifecycleOperationViewer'
   Invoke-ProdGcloud iam service-accounts add-iam-policy-binding pnl-worker@EXACT_PROJECT_ID.iam.gserviceaccount.com --member='serviceAccount:pnl-worker-controller@EXACT_PROJECT_ID.iam.gserviceaccount.com' --role=roles/iam.serviceAccountUser
   Invoke-ProdGcloud run services add-iam-policy-binding pnl-worker-controller --region=asia-southeast1 --member='serviceAccount:pnl-web@EXACT_PROJECT_ID.iam.gserviceaccount.com' --role=roles/run.invoker
   Invoke-ProdGcloud run services add-iam-policy-binding pnl-worker-controller --region=asia-southeast1 --member='serviceAccount:pnl-worker-reconciler@EXACT_PROJECT_ID.iam.gserviceaccount.com' --role=roles/run.invoker
   $controllerUrl = Invoke-ProdGcloud run services describe pnl-worker-controller --region=asia-southeast1 --format='value(status.url)'
   $controllerToken = gcloud auth print-identity-token --audiences=$controllerUrl
   Invoke-WebRequest -Headers @{ Authorization = "Bearer $controllerToken" } -Uri "$controllerUrl/health/live"
   Invoke-WebRequest -Headers @{ Authorization = "Bearer $controllerToken" } -Uri "$controllerUrl/health/ready"
   $controllerStatus = Invoke-RestMethod -Headers @{ Authorization = "Bearer $controllerToken" } -Uri "$controllerUrl/v1/worker/status"
   if ($controllerStatus.desired_instance_count -ne 0 -or $controllerStatus.actual_instance_count -ne 0) { throw 'Controller bootstrap is not at zero.' }
   $controllerToken = $null
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
   Invoke-ProdGcloud run services replace deploy/gcp/rendered/cloud-run-web.yaml --region=asia-southeast1
   $candidateRevision = Invoke-ProdGcloud run revisions list --service=pnl-web --region=asia-southeast1 --sort-by='~metadata.creationTimestamp' --limit=1 --format='value(metadata.name)'
   $privateUrl = Invoke-ProdGcloud run services describe pnl-web --region=asia-southeast1 --format='value(status.url)'
   $identityToken = gcloud auth print-identity-token --audiences=$privateUrl
   Invoke-WebRequest -Headers @{ Authorization = "Bearer $identityToken" } -Uri "$privateUrl/health/ready"
   Invoke-WebRequest -Headers @{ Authorization = "Bearer $identityToken" } -Uri "$privateUrl/health/live"
   Invoke-WebRequest -Headers @{ Authorization = "Bearer $identityToken" } -Uri "$privateUrl/"
   $sessionStatus = try { (Invoke-WebRequest -Headers @{ Authorization = "Bearer $identityToken" } -Uri "$privateUrl/api/session").StatusCode } catch { [int]$_.Exception.Response.StatusCode }
   if ($sessionStatus -ne 401) { throw 'Unauthenticated application session contract failed.' }
   $latestReady = Invoke-ProdGcloud run services describe pnl-web --region=asia-southeast1 --format='value(status.latestReadyRevisionName)'
   if ($candidateRevision -ne $latestReady) { throw 'Private candidate is not the latest Ready revision.' }
   Invoke-ProdGcloud run services describe pnl-web --region=asia-southeast1 --format='yaml(metadata.labels,status.latestReadyRevisionName,status.traffic,spec.template.metadata.labels,spec.template.spec.containers.image)'
   $volumeProof = Invoke-ProdGcloud run services logs read pnl-web --region=asia-southeast1 --limit=100
   if (-not ($volumeProof | Select-String 'volume_canary=pass uid=10001 path_count=2')) { throw 'UID volume canary evidence is missing.' }
   $identityToken = $null
   ```

   Render once more with `$privateUrl` as the exact `CloudRunOrigin` and replace
   the service while it is still private. Re-run the authenticated health, SPA,
   BFF, cookie/origin, label, and volume checks against that exact-origin
   revision. Only after those checks pass may the operator add the public
   invoker binding and begin the Access Code smoke. This avoids relying on
   `gcloud run services replace` for an implicit zero-traffic rollout and keeps
   the URL non-public until the final configuration is ready.

   ```powershell
   Invoke-ProdGcloud run services replace deploy/gcp/rendered/cloud-run-web.yaml --region=asia-southeast1
   $candidateRevision = Invoke-ProdGcloud run revisions list --service=pnl-web --region=asia-southeast1 --sort-by='~metadata.creationTimestamp' --limit=1 --format='value(metadata.name)'
   $identityToken = gcloud auth print-identity-token --audiences=$privateUrl
   Invoke-WebRequest -Headers @{ Authorization = "Bearer $identityToken" } -Uri "$privateUrl/health/ready"
   Invoke-ProdGcloud run services add-iam-policy-binding pnl-web --region=asia-southeast1 --member=allUsers --role=roles/run.invoker
   Invoke-ProdGcloud run services describe pnl-web --region=asia-southeast1 --format='value(status.traffic,status.url)'
   $identityToken = $null
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
    Invoke-ProdGcloud iam service-accounts add-iam-policy-binding pnl-worker-reconciler@EXACT_PROJECT_ID.iam.gserviceaccount.com --member='user:BOOTSTRAP_OPERATOR_EMAIL' --role=roles/iam.serviceAccountUser
    Invoke-ProdGcloud scheduler jobs create http pnl-worker-reconcile --location=asia-southeast1 --schedule='*/5 * * * *' --time-zone=Etc/UTC --http-method=POST --uri="$controllerUrl/v1/worker/reconcile" --oidc-service-account-email='pnl-worker-reconciler@EXACT_PROJECT_ID.iam.gserviceaccount.com' --oidc-token-audience="$controllerUrl" --attempt-deadline=30s --max-retry-attempts=3 --max-retry-duration=2m --min-backoff=5s --max-backoff=30s --max-doublings=2
    Invoke-ProdGcloud run worker-pools describe pnl-worker --region=asia-southeast1
    Invoke-ProdGcloud run worker-pools logs read pnl-worker --region=asia-southeast1 --limit=100
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
    Invoke-ProdGcloud run jobs replace deploy/gcp/rendered/maintenance-job.yaml --region=asia-southeast1
    Invoke-ProdGcloud run jobs execute pnl-maintenance --region=asia-southeast1 --wait
    ```

    Its first dry-run must prove UID 10001 create/delete access to
    `/var/tmp/pnl` and `/app/data`; otherwise stop before controlled apply.

12. Run the complete Production acceptance path: managed HTTPS, React/BFF, remote
    readiness, login/logout, lockout, synthetic Model upload/private Storage SHA,
    publication, Analysis/pgmq/independent Worker/Result/Admin/Viewer,
    Presentation/History/Evidence XLSX/P&L, audit/correlation, and maintenance.
    Validate Forecast sync mode: 1 and 6 months execute; 7 and 12 fail before
    reservation. Never upload a company workbook.

## Health, operations, rollback, and rotation

Before public binding and again after final smoke, capture a secret-free
Production evidence snapshot outside `deploy/gcp/rendered/`. Record project ID
and number, Supabase ref/region/plan, migration filenames and digests, Artifact
Registry index plus Linux/AMD64 child digests, Cloud Run revision names/traffic/
labels/image digests, Worker Pool generation/manual count/Ready, controller and
Job generations, Scheduler target/schedule/retry policy, runtime service-account
names, secret *references and enabled-version counts only*, IAM role names, and
the Worker final zero state. Never export secret payloads, cookies, Access Codes,
tokens, or synthetic Workbook bytes. Commit only the redacted evidence summary;
keep raw CLI exports ignored and delete them after the rollback record is reduced.

For a first deployment, rollback means removing public invocation and returning
the new environment to its initial zero-resource/zero-worker state. Before every
later replace, capture the current serving revision, exact digest, traffic map,
Worker generation/count, controller revision, Job generation, and Scheduler
configuration as the immutable rollback target.

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
