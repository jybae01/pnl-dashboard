import json
from pathlib import Path

from forecast.bff.production import TrustedProxyPolicy


ROOT = Path(__file__).resolve().parents[1]
GCP = ROOT / "deploy" / "gcp"


def _text(name: str) -> str:
    return (GCP / name).read_text(encoding="utf-8")


def test_cloud_run_web_is_one_origin_with_private_bff_sidecar():
    web = _text("cloud-run-web.yaml.tmpl")
    caddy = _text("Caddyfile.cloud-run")
    image = _text("Dockerfile.web")

    assert "kind: Service" in web
    assert web.count("containerPort:") == 1
    assert "containerPort: 8080" in web
    assert "name: edge" in web and "name: bff" in web
    assert "{\"edge\":[\"bff\"]}" in web
    assert "reverse_proxy 127.0.0.1:8000" in caddy
    assert ":{$PORT}" in caddy
    assert "auto_https off" in caddy and "tls internal" not in caddy
    assert "try_files {path} /index.html" in caddy
    assert 'ARG VITE_BFF_BASE_URL=""' in image
    assert 'test -z "$VITE_BFF_BASE_URL"' in image
    assert "ARG SUPABASE" not in image and "ENV SUPABASE" not in image


def test_cloud_run_web_preserves_forecast_timeout_scaling_and_temp_boundaries():
    web = _text("cloud-run-web.yaml.tmpl")

    for value in (
        'autoscaling.knative.dev/minScale: "0"',
        'autoscaling.knative.dev/maxScale: "2"',
        "containerConcurrency: 4",
        "timeoutSeconds: 180",
        "value: sync",
        'name: BFF_FORECAST_SYNC_APPROVED\n              value: "true"',
        'name: BFF_FORECAST_SYNC_MAX_MONTHS\n              value: "6"',
        'name: BFF_FORECAST_MAX_SECONDS\n              value: "120"',
        "memory: 2Gi",
        "sizeLimit: 512Mi",
        'name: BFF_TEMP_QUOTA_BYTES\n              value: "536870912"',
    ):
        assert value in web
    assert web.count('cpu: "1"') == 2
    assert "name: edge" in web and "memory: 512Mi" in web
    assert 'cpu: "250m"' not in web
    assert "BFF_FORECAST_SYNC_MAX_MONTHS\n              value: \"12\"" not in web


def test_cloud_run_proxy_contract_ignores_spoofed_forwarded_identity():
    web = _text("cloud-run-web.yaml.tmpl")
    caddy = _text("Caddyfile.cloud-run")
    policy = TrustedProxyPolicy.from_cidrs([])

    assert "name: BFF_PROXY_MODE\n              value: direct" in web
    assert "BFF_TRUSTED_PROXY_CIDRS" not in web
    for header in ("Forwarded", "X-Forwarded-For", "X-Real-IP"):
        assert f"header_up -{header}" in caddy
    assert policy.client_ip(
        "127.0.0.1", {"x-forwarded-for": "198.51.100.7"}
    ) == "127.0.0.1"


def test_cloud_run_secret_mounts_are_server_only_and_use_file_adapter():
    web = _text("cloud-run-web.yaml.tmpl")
    worker = _text("worker-pool.yaml.tmpl")
    job = _text("maintenance-job.yaml.tmpl")
    controller = _text("worker-controller.yaml.tmpl")
    entrypoint = (ROOT / "deploy" / "python-entrypoint.sh").read_text(encoding="utf-8")

    for manifest in (web, worker, job, controller):
        assert "SUPABASE_SECRET_KEY_FILE" in manifest
        assert "secretName: pnl-supabase-secret-key" in manifest
        assert "run.googleapis.com/secrets:" in manifest
        assert "projects/__PROJECT_NUMBER__/secrets/pnl-supabase-secret-key" in manifest
        assert "name: SUPABASE_SECRET_KEY\n" not in manifest
    for name in (
        "VIEWER_CODE_FILE",
        "ADMIN_CODE_FILE",
        "BFF_ACTOR_NAMESPACE_SECRET_FILE",
        "BFF_CSRF_SECRET_FILE",
    ):
        assert name in web and name not in worker and name not in job
    assert "load_secret SUPABASE_SECRET_KEY" in entrypoint
    assert "service-account.json" not in (web + worker + job + controller).lower()
    assert "GOOGLE_APPLICATION_CREDENTIALS" not in (web + worker + job + controller)


def test_worker_pool_is_independent_continuous_pgmq_consumer():
    worker = _text("worker-pool.yaml.tmpl")

    assert "kind: WorkerPool" in worker
    assert 'run.googleapis.com/scalingMode: manual' in worker
    assert 'run.googleapis.com/manualInstanceCount: "0"' in worker
    assert "forecast.worker_cli" in worker
    assert "--backend" in worker and "supabase" in worker
    assert 'cpu: "1"' in worker and "memory: 1Gi" in worker
    assert worker.count("sizeLimit: 256Mi") == 2
    assert "containerPort" not in worker
    assert "uvicorn" not in worker and "streamlit" not in worker.lower()


def test_demand_only_controller_and_reconciler_contract_is_least_privilege():
    controller = _text("worker-controller.yaml.tmpl")
    role = _text("worker-controller-role.yaml")
    operation_role = _text("worker-operation-viewer-role.yaml")
    web = _text("cloud-run-web.yaml.tmpl")
    runbook = _text("README.md")

    assert "name: pnl-worker-controller" in controller
    assert 'autoscaling.knative.dev/minScale: "0"' in controller
    assert 'autoscaling.knative.dev/maxScale: "1"' in controller
    assert "forecast.worker_controller_server:create_worker_controller_from_environment" in controller
    assert "--factory" in controller
    assert "run.workerpools.get" in role and "run.workerpools.update" in role
    assert "run.operations.get" not in role
    assert "run.operations.get" in operation_role
    assert "run.workerpools" not in operation_role
    for forbidden in ("run.workerpools.create", "run.workerpools.delete", "run.admin", "roles/owner"):
        assert forbidden not in role.lower()
    assert "BFF_WORKER_LIFECYCLE_MODE\n              value: demand_only" in web
    assert "BFF_WORKER_CONTROLLER_URL" in web
    assert "*/5 * * * *" in runbook
    assert "08:00" not in runbook and "18:00" not in runbook
    assert "--oidc-service-account-email" in runbook
    assert "--max-retry-attempts=3" in runbook
    assert "iam.serviceAccounts.actAs" in runbook
    assert "pnl-worker-controller@EXACT_PROJECT_ID.iam.gserviceaccount.com' --role=roles/iam.serviceAccountUser" in runbook
    assert "roles/cloudscheduler.serviceAgent" in runbook


def test_maintenance_job_is_one_shot_dry_run_by_default():
    job = _text("maintenance-job.yaml.tmpl")

    assert "kind: Job" in job
    assert "taskCount: 1" in job and "parallelism: 1" in job
    assert "maxRetries: 0" in job and 'timeoutSeconds: "900"' in job
    assert "forecast.maintenance" in job and "cleanup" in job
    assert "--apply" not in job
    assert "containerPort" not in job


def test_build_and_source_upload_contexts_exclude_sensitive_artifacts():
    dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")
    gcloudignore = (ROOT / ".gcloudignore").read_text(encoding="utf-8")
    required = (
        "*.xlsx",
        "*.xls",
        "*.xlsm",
        "*.xlsb",
        ".env*",
        "deploy/local-secrets",
        "deploy/gcp/rendered",
        ".pytest-demand-only-*",
        "**/*service-account*.json",
        "**/*credentials*.json",
    )
    assert all(pattern in dockerignore for pattern in required)
    assert all(pattern in gcloudignore for pattern in required)


def test_linux_entrypoint_is_normalized_during_image_build():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    attributes = (ROOT / ".gitattributes").read_text(encoding="utf-8")
    entrypoint = (ROOT / "deploy" / "python-entrypoint.sh").read_text(encoding="utf-8")
    web = _text("cloud-run-web.yaml.tmpl")
    worker = _text("worker-pool.yaml.tmpl")
    job = _text("maintenance-job.yaml.tmpl")

    assert "sed -i 's/\\r$//' /usr/local/bin/pnl-entrypoint" in dockerfile
    assert "deploy/*.sh text eol=lf" in attributes
    assert "verify_writable_volumes" in entrypoint
    assert 'mktemp "$path/.pnl-volume-canary.XXXXXX"' in entrypoint
    assert "volume_canary=pass uid=$(id -u)" in entrypoint
    assert "PNL_VOLUME_CANARY_PATHS" in web
    assert "value: /var/tmp/pnl:/app/data" in web
    assert "value: /tmp:/app/data" in worker
    assert "value: /var/tmp/pnl:/app/data" in job


def test_templates_are_placeholder_only_and_renderer_requires_digest_images():
    combined = "\n".join(
        _text(name)
        for name in (
            "cloud-run-web.yaml.tmpl",
            "worker-pool.yaml.tmpl",
            "worker-controller.yaml.tmpl",
            "maintenance-job.yaml.tmpl",
        )
    )
    renderer = _text("render.ps1")

    assert "__PROJECT_ID__" in combined
    assert "__PROJECT_NUMBER__" in combined
    assert "__RUNTIME_IMAGE__" in combined
    assert "__WEB_IMAGE__" in combined
    assert "__SUPABASE_URL__" in combined
    assert "__CLOUD_RUN_ORIGIN__" in combined
    assert "__WORKER_CONTROLLER_URL__" in combined
    assert "__SOURCE_COMMIT__" in combined
    assert "__RELEASE_STAGE__" in combined
    assert "__BUSINESS_GATE__" in combined
    assert combined.count("source-commit: __SOURCE_COMMIT__") == 8
    assert combined.count("release-stage: __RELEASE_STAGE__") == 8
    assert combined.count("business-gate: __BUSINESS_GATE__") == 8
    assert "@sha256:[0-9a-f]{64}" in renderer
    assert "SourceCommit must be a full lowercase 40-character Git commit" in renderer
    assert "ValidateSet('passed')" in renderer
    assert "gcloud " not in renderer.lower()
    assert "docker " not in renderer.lower()
    assert "Invoke-" not in renderer


def test_production_renderer_and_target_guard_fail_closed_against_staging():
    renderer = _text("render.ps1")
    guard = _text("assert-production-target.ps1")
    env_example = _text("env.example")

    for forbidden_identity in (
        "pnl-dashboard-staging",
        "498160536475",
        "ysatkswhhajicfgbrtpv",
        "sarwbkxukyexgioirpaa",
        "vfplhknqovdvsmjbvvax",
    ):
        assert forbidden_identity in renderer or forbidden_identity in guard
    assert "DeploymentProfile -eq 'production'" in renderer
    assert "/pnl-production/" in renderer
    assert "1e478b68b4f73dc6b41e2681cb6238a87d1e0427" in renderer
    assert "36502f01eed08012e2c0efb5f4756212c72b1373a390b5ed9bb78e59741d8330" in renderer
    assert "4121d8f3fe25b555ea30355110008c4b6e5ac9cb2ecbc065f164bde2cd5ce485" in renderer
    assert "v1-production-pilot" in renderer
    assert "pnl-production-*" in guard
    assert "billingEnabled" in guard
    assert "GOOGLE_ARTIFACT_REPOSITORY=pnl-production" in env_example
    assert "DEPLOYMENT_PROFILE=production" in env_example


def test_production_secret_bootstrap_is_no_echo_and_single_version():
    helper = _text("register-production-secrets.ps1")

    assert "assert-production-target.ps1" in helper
    assert helper.count("Read-Host") == 5
    assert helper.count("-AsSecureString") == 5
    assert "RedirectStandardInput = $true" in helper
    assert "--data-file=-" in helper
    assert "Refusing to add a second enabled version" in helper
    assert "New-RandomSecureString 48" in helper
    assert "pnl-dashboard-staging" not in helper


def test_v1_production_migration_chain_and_runbook_are_explicit():
    verifier = _text("verify-v1-migrations.ps1")
    runbook = _text("README.md")
    normalized = " ".join(runbook.split())
    manifest = [
        line.strip()
        for line in verifier.splitlines()
        if ".sql' = '" in line
    ]
    expected_pnl = [
        "'202608190001_pnl_reporting_persistence_slice_b.sql' = "
        "'ad124609334dea962c52b8bf46a44dd1e1a9ff9b150d93fec2204c7319eaf9d9'",
        "'202608190002_pnl_reporting_viewer_read_slice_c.sql' = "
        "'1bf546d0619070609540cea0ccf94dff83f3dec39b10a258d83e8092b42dbcbd'",
        "'202608190003_pnl_reporting_viewer_year_bootstrap.sql' = "
        "'5f2345163b66979efe7b8a10b9bac695e360ae9ed3bd2b243bb2530dc94bb4b1'",
    ]

    assert len(manifest) == 25
    assert manifest[-3:] == expected_pnl
    assert "202608090001_phase1_foundation.sql" in verifier
    assert "202608120001_demand_only_worker_lifecycle.sql" in verifier
    assert "20260815023857_persistent_delete_slice3.sql" in verifier
    assert "20260815050758_persistent_delete_recovery_slice3a.sql" in verifier
    assert "20260815053855_persistent_delete_status_classification_slice3a.sql" in verifier
    assert "20260815055055_persistent_delete_storage_requirement_slice3a.sql" in verifier
    assert "Migration order mismatch" in verifier
    assert "normalizedLfHash" in verifier
    assert "normalizedCrlfHash" in verifier
    assert "all 25 files in lexical order" in normalized
    assert "expected count is 25" in normalized
    assert "remote migration history proving 25/25" in normalized
    assert "read-only history/list operation" in normalized
    assert "future additive forward-fix migration" in normalized
    assert "Security Advisor" in runbook
    assert "pnl-production --repository-format=docker" in runbook
    assert "Invoke-ProdGcloud" in runbook
    assert "volume_canary=pass uid=10001 path_count=2" in runbook
    assert "Production evidence snapshot" in runbook
    assert "& $GcloudPath @args" in runbook
    assert "--impersonate-service-account=$DeployerAccount" in runbook
    assert "Do not add or change staging IAM for promotion" in runbook


def test_production_snapshot_is_target_guarded_and_never_reads_secret_payloads():
    snapshot = _text("capture-production-snapshot.ps1")

    assert "assert-production-target.ps1" in snapshot
    assert "pnl-production-snapshot-v1" in snapshot
    assert "Join-Path $PSScriptRoot 'rendered'" in snapshot
    assert "Snapshot output must stay in the ignored" in snapshot
    assert "enabled_version_count" in snapshot
    assert "secrets', 'versions', 'list'" in snapshot
    assert "secrets versions access" not in snapshot
    assert "secret payload" not in snapshot.lower()
    assert "ysatkswhhajicfgbrtpv" in snapshot
    assert "sarwbkxukyexgioirpaa" in snapshot
    assert "vfplhknqovdvsmjbvvax" in snapshot


def test_artifact_cleanup_policy_keeps_three_and_starts_as_documented_dry_run():
    policy = json.loads(_text("cleanup-policy.json"))
    assert any(
        item.get("condition", {}).get("olderThan") == "1209600s"
        and item.get("condition", {}).get("tagState") == "untagged"
        for item in policy
    )
    assert any(
        item.get("mostRecentVersions", {}).get("keepCount") == 3 for item in policy
    )
    assert "--dry-run" in _text("README.md")


def test_production_web_bootstrap_stays_private_until_exact_origin_smoke_passes():
    runbook = _text("README.md")
    normalized = " ".join(runbook.split())

    first_replace = runbook.index(
        "Invoke-ProdDeploy run services replace deploy/gcp/rendered/cloud-run-web.yaml"
    )
    exact_origin = runbook.index(
        "Render once more with `$privateUrl` as the exact `CloudRunOrigin`"
    )
    public_binding = runbook.index(
        "Invoke-ProdGcloud run services add-iam-policy-binding pnl-web --region=asia-southeast1 --member=allUsers"
    )
    assert first_replace < exact_origin < public_binding
    assert "Do not add `allUsers` yet" in normalized
    assert "implicit zero-traffic rollout" in normalized


def test_readiness_record_preserves_business_and_cloud_overclaim_boundaries():
    record = (ROOT / "docs" / "google_cloud_deployment_readiness.md").read_text(
        encoding="utf-8"
    )
    for invariant in (
        "LC 4-inch",
        "FS LENGTH/m",
        "effects_total + residual = OP_delta",
        "direct KRW/JPY",
        "customer freight",
        "Worker completion unpublished/non-default",
        "Forecast maximum six consecutive months",
    ):
        assert invariant in record
    assert "REAL GOOGLE CLOUD DEPLOYMENT = NOT_YET_EXECUTED" in record
    assert "REAL CLOUD DEPLOYMENT TOPOLOGY = NOT_YET_VALIDATED" in record
    assert "GOLDEN BUSINESS GATE = BLOCKED_NO_EXCEL_CALCULATED_PAIR" in record
    assert "FULL 12-MONTH FORECAST = DEFERRED_UNVERIFIED" in record
