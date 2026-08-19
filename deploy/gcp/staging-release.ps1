[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidateSet('CANDIDATE', 'CAPTURE_ACTIVE', 'PROMOTE', 'ROLLBACK')]
    [string] $Operation,

    [Parameter(Mandatory)] [string] $ProjectId,
    [Parameter(Mandatory)] [string] $ProjectNumber,
    [Parameter(Mandatory)] [string] $Region,
    [Parameter(Mandatory)] [string] $Service,

    [ValidateSet('BACKEND_FIRST', 'FINAL_FRONTEND')]
    [string] $Stage,
    [string] $GitHead,
    [string] $ApprovedOrigins,
    [string] $SupabaseUrl,
    [string] $WorkerControllerUrl,
    [string] $FrozenEdgeImage,
    [string] $FinalEdgeImage,
    [string] $RuntimeImage,
    [string] $ValidatedRevisionARuntimeImage,
    [string] $RevisionSuffix,
    [string] $CandidateTag,
    [string] $Revision,

    [ValidateSet('REVISION_B_TO_A', 'REVISION_A_TO_PRE_RELEASE', 'GOLDEN')]
    [string] $RollbackKind,
    [string] $PreReleaseStatePath,
    [string] $IncidentApproval,

    [string] $GcloudPath = "$env:LOCALAPPDATA\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd",
    [string] $OutputDirectory = (Join-Path $PSScriptRoot 'rendered\staging-release'),
    [switch] $Execute,
    [string] $MutationApproval,
    [ValidateSet('passed')] [string] $SmokeGate
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

. (Join-Path $PSScriptRoot 'staging-release-contract.ps1')

Assert-PnlStagingTarget `
    -ProjectId $ProjectId `
    -ProjectNumber $ProjectNumber `
    -Region $Region `
    -Service $Service

$allowedOutputRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot 'rendered'))
$resolvedOutputDirectory = [IO.Path]::GetFullPath($OutputDirectory)
if (-not (
    [string]::Equals($resolvedOutputDirectory, $allowedOutputRoot, [StringComparison]::OrdinalIgnoreCase) -or
    $resolvedOutputDirectory.StartsWith(
        $allowedOutputRoot + [IO.Path]::DirectorySeparatorChar,
        [StringComparison]::OrdinalIgnoreCase
    )
)) {
    throw 'Release output must stay inside the ignored deploy/gcp/rendered directory.'
}
New-Item -ItemType Directory -Force -Path $resolvedOutputDirectory | Out-Null

function Assert-RequiredText {
    param([Parameter(Mandatory)] [string] $Name, [AllowEmptyString()] [string] $Value)
    if ([string]::IsNullOrWhiteSpace($Value)) {
        throw "$Name is required for $Operation."
    }
}

function ConvertTo-CommandText {
    param([Parameter(Mandatory)] [string[]] $Arguments)
    $quoted = @($Arguments | ForEach-Object { "'$($_.Replace("'", "''"))'" })
    return 'gcloud ' + ($quoted -join ' ')
}

function Write-ReleaseArtifact {
    param(
        [Parameter(Mandatory)] [string] $Name,
        [Parameter(Mandatory)] [object] $Payload,
        [string[]] $CommandArguments
    )
    $jsonPath = Join-Path $resolvedOutputDirectory "$Name.json"
    [IO.File]::WriteAllText(
        $jsonPath,
        ($Payload | ConvertTo-Json -Depth 20),
        [Text.UTF8Encoding]::new($false)
    )
    if ($null -ne $CommandArguments -and $CommandArguments.Count -gt 0) {
        [IO.File]::WriteAllText(
            (Join-Path $resolvedOutputDirectory "$Name.command.txt"),
            (ConvertTo-CommandText -Arguments $CommandArguments),
            [Text.UTF8Encoding]::new($false)
        )
    }
    return $jsonPath
}

function Assert-GcloudAvailable {
    if (-not (Test-Path -LiteralPath $GcloudPath -PathType Leaf)) {
        throw 'gcloud was not found at the explicit path.'
    }
}

function Assert-GcloudCandidateCapabilities {
    Assert-GcloudAvailable
    $helpText = (& $GcloudPath run deploy --help 2>&1 | Out-String)
    if ($LASTEXITCODE -ne 0) {
        throw 'Unable to inspect installed gcloud run deploy help.'
    }
    foreach ($flag in @('--revision-suffix', '--tag', '--no-traffic', '--container', '--image')) {
        if (-not $helpText.Contains($flag, [StringComparison]::Ordinal)) {
            throw "Installed gcloud does not support required safe candidate flag: $flag"
        }
    }
}

function Assert-GcloudTrafficCapabilities {
    Assert-GcloudAvailable
    $helpText = (& $GcloudPath run services update-traffic --help 2>&1 | Out-String)
    if ($LASTEXITCODE -ne 0 -or -not $helpText.Contains('--to-revisions', [StringComparison]::Ordinal)) {
        throw 'Installed gcloud cannot route traffic to an explicit revision.'
    }
}

function Invoke-PnlGcloud {
    param([Parameter(Mandatory)] [string[]] $Arguments)
    Assert-GcloudAvailable
    $output = & $GcloudPath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "gcloud command failed: $($Arguments -join ' ')"
    }
    return $output
}

function Get-LiveServiceDescription {
    $json = Invoke-PnlGcloud -Arguments @(
        'run', 'services', 'describe', $Service,
        "--project=$ProjectId",
        "--region=$Region",
        '--format=json',
        '--quiet'
    )
    if (-not $json) {
        throw 'Cloud Run service describe returned no data.'
    }
    return ($json | ConvertFrom-Json)
}

function Get-ContainerByName {
    param([Parameter(Mandatory)] [object] $Description, [Parameter(Mandatory)] [string] $Name)
    $matches = @($Description.spec.template.spec.containers | Where-Object { [string]$_.name -eq $Name })
    if ($matches.Count -ne 1) {
        throw "Live service must contain exactly one $Name container."
    }
    return $matches[0]
}

function Get-EnvironmentValue {
    param([Parameter(Mandatory)] [object] $Container, [Parameter(Mandatory)] [string] $Name)
    $matches = @($Container.env | Where-Object { [string]$_.name -eq $Name })
    if ($matches.Count -ne 1 -or $null -eq $matches[0].value) {
        throw "Live service is missing required non-secret environment value $Name."
    }
    return [string]$matches[0].value
}

function Assert-LiveServicePreservationContract {
    param([Parameter(Mandatory)] [object] $Description)

    $containers = @($Description.spec.template.spec.containers)
    if ($containers.Count -ne 2) {
        throw 'Live staging service must contain exactly two containers before candidate deployment.'
    }
    $edge = Get-ContainerByName -Description $Description -Name 'edge'
    $bff = Get-ContainerByName -Description $Description -Name 'bff'
    if ([string]$Description.spec.template.spec.serviceAccountName -ne "pnl-web@$ProjectId.iam.gserviceaccount.com") {
        throw 'Live staging service uses an unexpected service account.'
    }
    if ([int]$Description.spec.template.spec.containerConcurrency -ne 4) {
        throw 'Live staging service concurrency drifted from 4.'
    }
    if ([int]$Description.spec.template.spec.timeoutSeconds -ne 180) {
        throw 'Live staging service timeout drifted from 180 seconds.'
    }
    if ([string]$edge.resources.limits.cpu -ne '1' -or [string]$edge.resources.limits.memory -ne '512Mi') {
        throw 'Live edge resource limits drifted.'
    }
    if ([string]$bff.resources.limits.cpu -ne '1' -or [string]$bff.resources.limits.memory -ne '2Gi') {
        throw 'Live runtime resource limits drifted.'
    }
    $serviceIngress = $Description.metadata.annotations.PSObject.Properties['run.googleapis.com/ingress']
    if ($null -eq $serviceIngress -or [string]$serviceIngress.Value -ne 'all') {
        throw 'Live staging service ingress drifted from all.'
    }
    $annotations = $Description.spec.template.metadata.annotations
    $expectedAnnotations = [ordered]@{
        'autoscaling.knative.dev/minScale' = '0'
        'autoscaling.knative.dev/maxScale' = '2'
        'run.googleapis.com/container-dependencies' = '{"edge":["bff"]}'
        'run.googleapis.com/execution-environment' = 'gen2'
        'run.googleapis.com/startup-cpu-boost' = 'true'
    }
    foreach ($entry in $expectedAnnotations.GetEnumerator()) {
        $property = $annotations.PSObject.Properties[$entry.Key]
        if ($null -eq $property -or [string]$property.Value -ne $entry.Value) {
            throw "Live staging service annotation drifted: $($entry.Key)"
        }
    }
    $expectedEnvironment = [ordered]@{
        PNL_REPOSITORY_BACKEND = 'supabase'
        SUPABASE_URL = $SupabaseUrl.TrimEnd('/')
        SUPABASE_SECRET_KEY_FILE = '/var/run/pnl-secrets/supabase/supabase_secret_key'
        VIEWER_CODE_FILE = '/var/run/pnl-secrets/viewer/viewer_code'
        ADMIN_CODE_FILE = '/var/run/pnl-secrets/admin/admin_code'
        BFF_ACTOR_NAMESPACE_SECRET_FILE = '/var/run/pnl-secrets/actor/actor_namespace_secret'
        BFF_CSRF_SECRET_FILE = '/var/run/pnl-secrets/csrf/csrf_secret'
        BFF_ENVIRONMENT = 'production'
        BFF_FORECAST_MODE = 'sync'
        BFF_FORECAST_SYNC_APPROVED = 'true'
        BFF_FORECAST_SYNC_MAX_MONTHS = '6'
        BFF_FORECAST_MAX_SECONDS = '120'
        BFF_FORECAST_PERMIT_LEASE_SECONDS = '240'
        BFF_FORECAST_MAX_CONCURRENCY = '1'
        BFF_FORECAST_REQUEST_MAX_BYTES = '1048576'
        BFF_SESSION_TTL_SECONDS = '28800'
        BFF_LOGIN_MAX_ATTEMPTS = '5'
        BFF_LOGIN_WINDOW_SECONDS = '300'
        BFF_COOKIE_SECURE = 'true'
        BFF_COOKIE_SAME_SITE = 'strict'
        BFF_PROXY_MODE = 'direct'
        BFF_WORKER_LIFECYCLE_MODE = 'demand_only'
        BFF_WORKER_CONTROLLER_URL = $WorkerControllerUrl
        BFF_TEMP_ROOT = '/var/tmp/pnl'
        BFF_TEMP_QUOTA_BYTES = '536870912'
        PNL_VOLUME_CANARY_PATHS = '/var/tmp/pnl:/app/data'
        BFF_TEMP_ORPHAN_AGE_SECONDS = '86400'
        BFF_PARSER_TIMEOUT_SECONDS = '45'
        BFF_PARSER_MEMORY_LIMIT_BYTES = '805306368'
        BFF_PARSER_MAX_CONCURRENCY = '1'
        BFF_LOG_LEVEL = 'INFO'
    }
    foreach ($entry in $expectedEnvironment.GetEnumerator()) {
        if ((Get-EnvironmentValue -Container $bff -Name $entry.Key) -ne $entry.Value) {
            throw "Live staging service environment drifted: $($entry.Key)"
        }
    }
    $currentOriginValue = Get-EnvironmentValue -Container $bff -Name 'BFF_ALLOWED_ORIGINS'
    if ($currentOriginValue.Contains(',', [StringComparison]::Ordinal)) {
        ConvertTo-PnlApprovedStagingOriginValue -Origins $currentOriginValue | Out-Null
    }
    else {
        Assert-PnlApprovedStagingOrigin -Origin $currentOriginValue
    }

    $edgePorts = @($edge.ports)
    if (
        $edgePorts.Count -ne 1 -or
        [string]$edgePorts[0].name -ne 'http1' -or
        [int]$edgePorts[0].containerPort -ne 8080
    ) {
        throw 'Live edge port contract drifted.'
    }
    if (
        [string]$edge.startupProbe.httpGet.path -ne '/health/ready' -or
        [int]$edge.startupProbe.httpGet.port -ne 8080 -or
        [int]$edge.startupProbe.initialDelaySeconds -ne 0 -or
        [int]$edge.startupProbe.timeoutSeconds -ne 3 -or
        [int]$edge.startupProbe.periodSeconds -ne 5 -or
        [int]$edge.startupProbe.failureThreshold -ne 24
    ) {
        throw 'Live edge startup probe drifted.'
    }
    if (
        [string]$bff.startupProbe.httpGet.path -ne '/health/ready' -or
        [int]$bff.startupProbe.httpGet.port -ne 8000 -or
        [int]$bff.startupProbe.initialDelaySeconds -ne 0 -or
        [int]$bff.startupProbe.timeoutSeconds -ne 3 -or
        [int]$bff.startupProbe.periodSeconds -ne 5 -or
        [int]$bff.startupProbe.failureThreshold -ne 24
    ) {
        throw 'Live runtime startup probe drifted.'
    }
    if (
        [string]$bff.livenessProbe.httpGet.path -ne '/health/live' -or
        [int]$bff.livenessProbe.httpGet.port -ne 8000 -or
        [int]$bff.livenessProbe.timeoutSeconds -ne 3 -or
        [int]$bff.livenessProbe.periodSeconds -ne 30 -or
        [int]$bff.livenessProbe.failureThreshold -ne 3
    ) {
        throw 'Live runtime liveness probe drifted.'
    }

    $volumes = @($Description.spec.template.spec.volumes)
    $requiredVolumeNames = @(
        'bff-temp', 'model-cache', 'supabase-secret', 'viewer-secret',
        'admin-secret', 'actor-secret', 'csrf-secret'
    )
    if ($volumes.Count -ne $requiredVolumeNames.Count) {
        throw 'Live staging service volume count drifted.'
    }
    foreach ($name in $requiredVolumeNames) {
        if (@($volumes | Where-Object { [string]$_.name -eq $name }).Count -ne 1) {
            throw "Live staging service dropped or duplicated required volume $name."
        }
    }
    $bffTemp = @($volumes | Where-Object { [string]$_.name -eq 'bff-temp' })[0]
    $modelCache = @($volumes | Where-Object { [string]$_.name -eq 'model-cache' })[0]
    if ([string]$bffTemp.emptyDir.medium -ne 'Memory' -or [string]$bffTemp.emptyDir.sizeLimit -ne '512Mi') {
        throw 'Live bff-temp volume drifted.'
    }
    if ([string]$modelCache.emptyDir.medium -ne 'Memory' -or [string]$modelCache.emptyDir.sizeLimit -ne '256Mi') {
        throw 'Live model-cache volume drifted.'
    }
    $secretVolumes = [ordered]@{
        'supabase-secret' = 'pnl-supabase-secret-key'
        'viewer-secret' = 'pnl-viewer-code'
        'admin-secret' = 'pnl-admin-code'
        'actor-secret' = 'pnl-actor-namespace-secret'
        'csrf-secret' = 'pnl-csrf-secret'
    }
    foreach ($entry in $secretVolumes.GetEnumerator()) {
        $volume = @($volumes | Where-Object { [string]$_.name -eq $entry.Key })[0]
        if ([string]$volume.secret.secretName -ne $entry.Value) {
            throw "Live staging secret volume drifted: $($entry.Key)"
        }
    }
    $expectedMounts = [ordered]@{
        'bff-temp' = '/var/tmp/pnl'
        'model-cache' = '/app/data'
        'supabase-secret' = '/var/run/pnl-secrets/supabase'
        'viewer-secret' = '/var/run/pnl-secrets/viewer'
        'admin-secret' = '/var/run/pnl-secrets/admin'
        'actor-secret' = '/var/run/pnl-secrets/actor'
        'csrf-secret' = '/var/run/pnl-secrets/csrf'
    }
    $mounts = @($bff.volumeMounts)
    if ($mounts.Count -ne $expectedMounts.Count) {
        throw 'Live runtime volume-mount count drifted.'
    }
    foreach ($entry in $expectedMounts.GetEnumerator()) {
        $matches = @($mounts | Where-Object {
            [string]$_.name -eq $entry.Key -and [string]$_.mountPath -eq $entry.Value
        })
        if ($matches.Count -ne 1) {
            throw "Live runtime volume mount drifted: $($entry.Key)"
        }
    }
    $serialized = $Description | ConvertTo-Json -Depth 100
    foreach ($secretName in @(
        'pnl-supabase-secret-key', 'pnl-viewer-code', 'pnl-admin-code',
        'pnl-actor-namespace-secret', 'pnl-csrf-secret'
    )) {
        if (-not $serialized.Contains($secretName, [StringComparison]::Ordinal)) {
            throw "Live staging service dropped required secret reference $secretName."
        }
        $secretResource = "projects/$ProjectNumber/secrets/$secretName"
        if (-not $serialized.Contains($secretResource, [StringComparison]::Ordinal)) {
            throw "Live staging service secret annotation drifted: $secretName."
        }
    }
}

function Write-ActiveRevisionState {
    param(
        [Parameter(Mandatory)] [object] $Description,
        [Parameter(Mandatory)] [string] $Path,
        [AllowEmptyString()] [string] $SourceCommit,
        [Parameter(Mandatory)] [string] $Purpose
    )
    $resolvedPath = [IO.Path]::GetFullPath($Path)
    if (-not $resolvedPath.StartsWith(
        $allowedOutputRoot + [IO.Path]::DirectorySeparatorChar,
        [StringComparison]::OrdinalIgnoreCase
    )) {
        throw 'Captured revision state must stay inside deploy/gcp/rendered.'
    }
    New-Item -ItemType Directory -Force -Path (Split-Path $resolvedPath -Parent) | Out-Null
    $active = Get-PnlActiveRevision -ServiceDescription $Description -Service $Service
    $state = [ordered]@{
        schema = 'pnl-staging-active-revision-v1'
        captured_at_utc = [DateTime]::UtcNow.ToString('o')
        purpose = $Purpose
        project = $ProjectId
        project_number = $ProjectNumber
        region = $Region
        service = $Service
        source_commit = $SourceCommit
        active_revision = $active
    }
    if (Test-Path -LiteralPath $resolvedPath -PathType Leaf) {
        $existing = Get-Content -Raw -LiteralPath $resolvedPath | ConvertFrom-Json
        if (
            [string]$existing.schema -ne [string]$state.schema -or
            [string]$existing.project -ne [string]$state.project -or
            [string]$existing.project_number -ne [string]$state.project_number -or
            [string]$existing.region -ne [string]$state.region -or
            [string]$existing.service -ne [string]$state.service -or
            [string]$existing.source_commit -ne [string]$state.source_commit -or
            [string]$existing.active_revision -ne [string]$state.active_revision
        ) {
            throw 'Refusing to overwrite captured active-revision state with different release data.'
        }
        return $active
    }
    [IO.File]::WriteAllText(
        $resolvedPath,
        ($state | ConvertTo-Json -Depth 5),
        [Text.UTF8Encoding]::new($false)
    )
    return $active
}

function Assert-StageAndHead {
    Assert-RequiredText -Name 'Stage' -Value $Stage
    Assert-RequiredText -Name 'GitHead' -Value $GitHead
    return Get-PnlStagingReleaseIdentity -Stage $Stage -GitHead $GitHead -Service $Service
}

$describeArguments = @(
    'run', 'services', 'describe', $Service,
    "--project=$ProjectId",
    "--region=$Region",
    '--format=json',
    '--quiet'
)

if ($Operation -eq 'CANDIDATE') {
    $identity = Assert-StageAndHead
    foreach ($required in @(
        @('ApprovedOrigins', $ApprovedOrigins),
        @('SupabaseUrl', $SupabaseUrl),
        @('WorkerControllerUrl', $WorkerControllerUrl),
        @('RuntimeImage', $RuntimeImage),
        @('RevisionSuffix', $RevisionSuffix),
        @('CandidateTag', $CandidateTag)
    )) {
        Assert-RequiredText -Name $required[0] -Value $required[1]
    }
    $originValue = ConvertTo-PnlApprovedStagingOriginValue -Origins $ApprovedOrigins
    Assert-PnlDigestImage -Image $RuntimeImage -Role 'runtime'
    if (-not [string]::Equals($RevisionSuffix, $identity.revision_suffix, [StringComparison]::Ordinal)) {
        throw "RevisionSuffix must equal deterministic value $($identity.revision_suffix)."
    }
    if (-not [string]::Equals($CandidateTag, $identity.candidate_tag, [StringComparison]::Ordinal)) {
        throw "CandidateTag must equal deterministic value $($identity.candidate_tag)."
    }

    if ($Stage -eq 'BACKEND_FIRST') {
        Assert-RequiredText -Name 'FrozenEdgeImage' -Value $FrozenEdgeImage
        if (-not [string]::IsNullOrWhiteSpace($FinalEdgeImage)) {
            throw 'BACKEND_FIRST must not accept a final edge image.'
        }
        $edgeImage = $FrozenEdgeImage
        $releaseStage = 'pnl-backend-first'
    }
    else {
        Assert-RequiredText -Name 'FinalEdgeImage' -Value $FinalEdgeImage
        Assert-RequiredText -Name 'ValidatedRevisionARuntimeImage' -Value $ValidatedRevisionARuntimeImage
        if (-not [string]::IsNullOrWhiteSpace($FrozenEdgeImage)) {
            throw 'FINAL_FRONTEND must not accept a frozen edge image.'
        }
        if (-not [string]::Equals($RuntimeImage, $ValidatedRevisionARuntimeImage, [StringComparison]::Ordinal)) {
            throw 'FINAL_FRONTEND runtime image must exactly equal the runtime image validated in Revision A.'
        }
        $edgeImage = $FinalEdgeImage
        $releaseStage = 'pnl-final-frontend'
    }
    Assert-PnlDigestImage -Image $edgeImage -Role 'edge'

    $manifestDirectory = Join-Path $resolvedOutputDirectory "manifest-$($Stage.ToLowerInvariant().Replace('_', '-'))"
    & (Join-Path $PSScriptRoot 'render.ps1') `
        -ProjectId $ProjectId `
        -ProjectNumber $ProjectNumber `
        -Region $Region `
        -SupabaseUrl $SupabaseUrl `
        -ApprovedOrigins $originValue `
        -WorkerControllerUrl $WorkerControllerUrl `
        -WebImage $edgeImage `
        -RuntimeImage $RuntimeImage `
        -SourceCommit $GitHead `
        -ReleaseStage $releaseStage `
        -BusinessGate 'passed' `
        -DeploymentProfile 'staging' `
        -OutputDirectory $manifestDirectory | Out-Null

    $webManifestPath = Join-Path $manifestDirectory 'cloud-run-web.yaml'
    $webManifest = Get-Content -Raw -LiteralPath $webManifestPath
    Assert-PnlRenderedWebManifest `
        -Manifest $webManifest `
        -ProjectId $ProjectId `
        -Service $Service `
        -EdgeImage $edgeImage `
        -RuntimeImage $RuntimeImage `
        -ApprovedOrigins $originValue

    $dictionaryDelimiter = if ([IO.Path]::GetExtension($GcloudPath) -ieq '.cmd') {
        '^^^^@^^^^'
    }
    else {
        '^@^'
    }
    $candidateArguments = @(
        'run', 'deploy', $Service,
        "--project=$ProjectId",
        "--region=$Region",
        "--revision-suffix=$RevisionSuffix",
        "--tag=$CandidateTag",
        '--no-traffic',
        "--update-labels=source-commit=$GitHead,release-stage=$releaseStage,business-gate=passed",
        '--container=edge',
        "--image=$edgeImage",
        '--container=bff',
        "--image=$RuntimeImage",
        "--update-env-vars=$($dictionaryDelimiter)BFF_ALLOWED_ORIGINS=$originValue",
        '--quiet'
    )
    $plan = [ordered]@{
        schema = 'pnl-staging-release-plan-v1'
        operation = 'CANDIDATE'
        dry_run = -not $Execute
        cloud_mutation = [bool]$Execute
        project = $ProjectId
        project_number = $ProjectNumber
        region = $Region
        service = $Service
        source_commit = $GitHead
        stage = $Stage
        revision_suffix = $identity.revision_suffix
        revision_name = $identity.revision_name
        candidate_tag = $identity.candidate_tag
        zero_traffic = $true
        edge_image = $edgeImage
        runtime_image = $RuntimeImage
        approved_origins = @($originValue.Split([char]','))
        rendered_manifest = $webManifestPath
        gcloud = [ordered]@{
            executable = 'gcloud'
            arguments = $candidateArguments
            command = ConvertTo-CommandText -Arguments $candidateArguments
        }
    }
    $artifactPath = Write-ReleaseArtifact `
        -Name "candidate-$($Stage.ToLowerInvariant().Replace('_', '-'))" `
        -Payload $plan `
        -CommandArguments $candidateArguments

    if (-not $Execute) {
        Write-Output "DRY_RUN=PASS operation=CANDIDATE stage=$Stage revision=$($identity.revision_name) plan=$artifactPath"
        return
    }
    if ($MutationApproval -ne 'APPROVE_STAGING_CANDIDATE') {
        throw 'Candidate execution requires MutationApproval=APPROVE_STAGING_CANDIDATE.'
    }
    Assert-GcloudCandidateCapabilities
    $liveDescription = Get-LiveServiceDescription
    Assert-LiveServicePreservationContract -Description $liveDescription
    $liveEdge = Get-ContainerByName -Description $liveDescription -Name 'edge'
    $liveRuntime = Get-ContainerByName -Description $liveDescription -Name 'bff'
    if (
        $Stage -eq 'BACKEND_FIRST' -and
        -not [string]::Equals([string]$liveEdge.image, $FrozenEdgeImage, [StringComparison]::Ordinal)
    ) {
        throw 'FrozenEdgeImage must exactly equal the current live service edge digest.'
    }
    if (
        $Stage -eq 'FINAL_FRONTEND' -and
        -not [string]::Equals([string]$liveRuntime.image, $ValidatedRevisionARuntimeImage, [StringComparison]::Ordinal)
    ) {
        throw 'FINAL_FRONTEND requires the live service template to retain Revision A runtime exactly.'
    }
    Invoke-PnlGcloud -Arguments $candidateArguments | Out-Host
    Write-Output "CANDIDATE_CREATED=PASS revision=$($identity.revision_name) traffic=0 tag=$($identity.candidate_tag)"
    return
}

if ($Operation -eq 'CAPTURE_ACTIVE') {
    Assert-RequiredText -Name 'GitHead' -Value $GitHead
    $statePath = if ([string]::IsNullOrWhiteSpace($PreReleaseStatePath)) {
        Join-Path $resolvedOutputDirectory 'pre-release-active-revision.json'
    }
    else {
        $PreReleaseStatePath
    }
    $plan = [ordered]@{
        schema = 'pnl-staging-release-plan-v1'
        operation = 'CAPTURE_ACTIVE'
        dry_run = -not $Execute
        cloud_mutation = $false
        project = $ProjectId
        region = $Region
        service = $Service
        output = [IO.Path]::GetFullPath($statePath)
        gcloud = [ordered]@{
            executable = 'gcloud'
            arguments = $describeArguments
            command = ConvertTo-CommandText -Arguments $describeArguments
        }
    }
    $artifactPath = Write-ReleaseArtifact -Name 'capture-active' -Payload $plan -CommandArguments $describeArguments
    if (-not $Execute) {
        Write-Output "DRY_RUN=PASS operation=CAPTURE_ACTIVE plan=$artifactPath"
        return
    }
    $description = Get-LiveServiceDescription
    $active = Write-ActiveRevisionState `
        -Description $description `
        -Path $statePath `
        -SourceCommit $GitHead `
        -Purpose 'pre-release rollback target'
    Write-Output "ACTIVE_REVISION_CAPTURED=PASS revision=$active path=$([IO.Path]::GetFullPath($statePath))"
    return
}

if ($Operation -eq 'PROMOTE') {
    $identity = Assert-StageAndHead
    Assert-RequiredText -Name 'Revision' -Value $Revision
    if (-not [string]::Equals($Revision, $identity.revision_name, [StringComparison]::Ordinal)) {
        throw "Promotion revision must equal deterministic target $($identity.revision_name)."
    }
    $promotionArguments = @(
        'run', 'services', 'update-traffic', $Service,
        "--project=$ProjectId",
        "--region=$Region",
        "--to-revisions=$Revision=100",
        '--quiet'
    )
    $captureName = if ($Stage -eq 'BACKEND_FIRST') {
        "pre-release-$($identity.short_head).json"
    }
    else {
        "pre-final-$($identity.short_head).json"
    }
    $capturePath = Join-Path $resolvedOutputDirectory $captureName
    $plan = [ordered]@{
        schema = 'pnl-staging-release-plan-v1'
        operation = 'PROMOTE'
        dry_run = -not $Execute
        cloud_mutation = [bool]$Execute
        project = $ProjectId
        region = $Region
        service = $Service
        source_commit = $GitHead
        stage = $Stage
        target_revision = $Revision
        smoke_gate_required = 'passed'
        capture_current_100_percent_revision_before_promotion = $true
        capture_output = $capturePath
        capture_command = ConvertTo-CommandText -Arguments $describeArguments
        gcloud = [ordered]@{
            executable = 'gcloud'
            arguments = $promotionArguments
            command = ConvertTo-CommandText -Arguments $promotionArguments
        }
    }
    $artifactPath = Write-ReleaseArtifact `
        -Name "promote-$($Stage.ToLowerInvariant().Replace('_', '-'))" `
        -Payload $plan `
        -CommandArguments $promotionArguments
    if (-not $Execute) {
        Write-Output "DRY_RUN=PASS operation=PROMOTE target=$Revision plan=$artifactPath"
        return
    }
    if ($MutationApproval -ne 'APPROVE_STAGING_PROMOTION') {
        throw 'Promotion requires MutationApproval=APPROVE_STAGING_PROMOTION.'
    }
    if ($SmokeGate -ne 'passed') {
        throw 'Promotion requires SmokeGate=passed from the candidate-specific smoke.'
    }
    Assert-GcloudTrafficCapabilities
    $description = Get-LiveServiceDescription
    $active = Get-PnlActiveRevision -ServiceDescription $description -Service $Service
    if ([string]::Equals($active, $Revision, [StringComparison]::Ordinal)) {
        throw 'The explicit promotion target already serves 100 percent traffic.'
    }
    if ($Stage -eq 'FINAL_FRONTEND') {
        $expectedRevisionA = (
            Get-PnlStagingReleaseIdentity -Stage 'BACKEND_FIRST' -GitHead $GitHead -Service $Service
        ).revision_name
        if (-not [string]::Equals($active, $expectedRevisionA, [StringComparison]::Ordinal)) {
            throw 'FINAL_FRONTEND promotion requires deterministic Revision A to be the current 100-percent revision.'
        }
    }
    $active = Write-ActiveRevisionState `
        -Description $description `
        -Path $capturePath `
        -SourceCommit $GitHead `
        -Purpose "rollback target before promoting $Revision"
    Invoke-PnlGcloud -Arguments $promotionArguments | Out-Host
    Write-Output "PROMOTION=PASS revision=$Revision traffic=100 previous=$active"
    return
}

if ($Operation -eq 'ROLLBACK') {
    Assert-RequiredText -Name 'RollbackKind' -Value $RollbackKind
    Assert-RequiredText -Name 'GitHead' -Value $GitHead
    $backendIdentity = Get-PnlStagingReleaseIdentity -Stage 'BACKEND_FIRST' -GitHead $GitHead -Service $Service
    if ($RollbackKind -eq 'REVISION_B_TO_A') {
        $targetRevision = $backendIdentity.revision_name
        $rollbackSource = 'deterministic Revision A identity'
    }
    elseif ($RollbackKind -eq 'REVISION_A_TO_PRE_RELEASE') {
        Assert-RequiredText -Name 'PreReleaseStatePath' -Value $PreReleaseStatePath
        $resolvedStatePath = [IO.Path]::GetFullPath($PreReleaseStatePath)
        if (-not $resolvedStatePath.StartsWith(
            $allowedOutputRoot + [IO.Path]::DirectorySeparatorChar,
            [StringComparison]::OrdinalIgnoreCase
        )) {
            throw 'Pre-release state must be read from deploy/gcp/rendered.'
        }
        if (-not (Test-Path -LiteralPath $resolvedStatePath -PathType Leaf)) {
            throw 'Captured pre-release revision state was not found.'
        }
        $state = Get-Content -Raw -LiteralPath $resolvedStatePath | ConvertFrom-Json
        if (
            [string]$state.schema -ne 'pnl-staging-active-revision-v1' -or
            [string]$state.project -ne $ProjectId -or
            [string]$state.project_number -ne $ProjectNumber -or
            [string]$state.region -ne $Region -or
            [string]$state.service -ne $Service -or
            [string]$state.source_commit -ne $GitHead
        ) {
            throw 'Captured pre-release revision state does not match this release.'
        }
        $targetRevision = [string]$state.active_revision
        if ($targetRevision -notmatch "^$([regex]::Escape($Service))-[a-z0-9-]+$") {
            throw 'Captured pre-release revision is invalid.'
        }
        $rollbackSource = $resolvedStatePath
    }
    else {
        $targetRevision = 'pnl-web-golden-1e478b6'
        $rollbackSource = 'incident-only frozen golden revision'
    }

    $rollbackArguments = @(
        'run', 'services', 'update-traffic', $Service,
        "--project=$ProjectId",
        "--region=$Region",
        "--to-revisions=$targetRevision=100",
        '--quiet'
    )
    $plan = [ordered]@{
        schema = 'pnl-staging-release-plan-v1'
        operation = 'ROLLBACK'
        dry_run = -not $Execute
        cloud_mutation = [bool]$Execute
        project = $ProjectId
        region = $Region
        service = $Service
        source_commit = $GitHead
        rollback_kind = $RollbackKind
        target_revision = $targetRevision
        target_source = $rollbackSource
        incident_approval_required = ($RollbackKind -eq 'GOLDEN')
        gcloud = [ordered]@{
            executable = 'gcloud'
            arguments = $rollbackArguments
            command = ConvertTo-CommandText -Arguments $rollbackArguments
        }
    }
    $artifactPath = Write-ReleaseArtifact `
        -Name "rollback-$($RollbackKind.ToLowerInvariant().Replace('_', '-'))" `
        -Payload $plan `
        -CommandArguments $rollbackArguments
    if (-not $Execute) {
        Write-Output "DRY_RUN=PASS operation=ROLLBACK kind=$RollbackKind target=$targetRevision plan=$artifactPath"
        return
    }
    if ($MutationApproval -ne 'APPROVE_STAGING_ROLLBACK') {
        throw 'Rollback requires MutationApproval=APPROVE_STAGING_ROLLBACK.'
    }
    if ($RollbackKind -eq 'GOLDEN' -and $IncidentApproval -ne 'APPROVE_GOLDEN_INCIDENT_ROLLBACK') {
        throw 'Golden rollback requires explicit incident approval.'
    }
    Assert-GcloudTrafficCapabilities
    Invoke-PnlGcloud -Arguments $rollbackArguments | Out-Host
    Write-Output "ROLLBACK=PASS kind=$RollbackKind revision=$targetRevision traffic=100"
    return
}

throw "Unsupported release operation: $Operation"
