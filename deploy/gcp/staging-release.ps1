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
    [string] $ValidatedRevisionA,
    [string] $ValidatedRevisionAEdgeImage,
    [string] $ValidatedRevisionARuntimeImage,
    [string] $RevisionSuffix,
    [string] $CandidateTag,
    [string] $Revision,

    [ValidateSet('REVISION_B_TO_A', 'REVISION_A_TO_PRE_RELEASE', 'GOLDEN')]
    [string] $RollbackKind,
    [string] $PreReleaseStatePath,
    [string] $CapturedServiceJsonPath,
    [string] $CapturedActiveRevisionJsonPath,
    [string] $RuntimeManifestJsonPath,
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
    $resolvedGcloud = Resolve-PnlGcloudExecutable -GcloudPath $GcloudPath
    $windowsCmdShim = $resolvedGcloud.EndsWith('.cmd', [StringComparison]::OrdinalIgnoreCase)
    $executionArguments = ConvertTo-PnlGcloudExecutionArguments `
        -Arguments $Arguments `
        -WindowsCmdShim $windowsCmdShim
    $quotedExecutable = "'$($resolvedGcloud.Replace("'", "''"))'"
    $quoted = @($executionArguments | ForEach-Object { "'$($_.Replace("'", "''"))'" })
    return '& ' + $quotedExecutable + ' ' + ($quoted -join ' ')
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
    return Resolve-PnlGcloudExecutable -GcloudPath $GcloudPath
}

function Assert-GcloudCandidateCapabilities {
    return Assert-PnlGcloudCandidateCapabilities -GcloudPath $GcloudPath
}

function Assert-GcloudTrafficCapabilities {
    return Assert-PnlGcloudTrafficCapabilities -GcloudPath $GcloudPath
}

function Invoke-PnlGcloud {
    param([Parameter(Mandatory)] [string[]] $Arguments)
    $resolvedGcloud = Assert-GcloudAvailable
    $windowsCmdShim = $resolvedGcloud.EndsWith('.cmd', [StringComparison]::OrdinalIgnoreCase)
    $executionArguments = ConvertTo-PnlGcloudExecutionArguments `
        -Arguments $Arguments `
        -WindowsCmdShim $windowsCmdShim
    $stdoutPath = [IO.Path]::GetTempFileName()
    $stderrPath = [IO.Path]::GetTempFileName()
    try {
        $global:LASTEXITCODE = 0
        & $resolvedGcloud @executionArguments 1> $stdoutPath 2> $stderrPath
        $commandSucceeded = $?
        $exitCode = $global:LASTEXITCODE
        $stdout = [IO.File]::ReadAllText($stdoutPath)
        $stderr = [IO.File]::ReadAllText($stderrPath)
    }
    finally {
        [IO.File]::Delete($stdoutPath)
        [IO.File]::Delete($stderrPath)
    }
    if (-not $commandSucceeded -or $exitCode -ne 0) {
        throw "gcloud command failed with exit code $exitCode`: $($Arguments -join ' ')`n$stderr"
    }
    return $stdout
}

function Get-PlannedGcloudExecutable {
    return Resolve-PnlGcloudExecutable -GcloudPath $GcloudPath
}

function Resolve-ReleaseStatePath {
    param([Parameter(Mandatory)] [string] $Path)

    $resolvedPath = [IO.Path]::GetFullPath($Path)
    if (-not $resolvedPath.StartsWith(
        $allowedOutputRoot + [IO.Path]::DirectorySeparatorChar,
        [StringComparison]::OrdinalIgnoreCase
    )) {
        throw 'Release capture state must stay inside deploy/gcp/rendered.'
    }
    return $resolvedPath
}

function Read-ValidatedPreReleaseState {
    param(
        [Parameter(Mandatory)] [string] $Path,
        [Parameter(Mandatory)] [string] $ExpectedGitHead
    )

    $resolvedStatePath = Resolve-ReleaseStatePath -Path $Path
    if (-not (Test-Path -LiteralPath $resolvedStatePath -PathType Leaf)) {
        throw 'Captured pre-release revision state was not found.'
    }
    try {
        $state = Get-Content -Raw -LiteralPath $resolvedStatePath | ConvertFrom-Json -Depth 20
    }
    catch {
        throw 'Captured pre-release revision state is not valid JSON.'
    }
    $capturedAt = [DateTimeOffset]::MinValue
    $capturedAtValid = [DateTimeOffset]::TryParse(
        [string](Get-PnlRequiredJsonProperty -Object $state -Name 'captured_at_utc' -FieldName 'captured_at_utc'),
        [ref]$capturedAt
    )
    $validValue = Get-PnlRequiredJsonProperty -Object $state -Name 'valid' -FieldName 'valid'
    $trafficPercentValue = Get-PnlRequiredJsonProperty `
        -Object $state `
        -Name 'traffic_percent' `
        -FieldName 'traffic_percent'
    if (
        ([string](Get-PnlRequiredJsonProperty -Object $state -Name 'schema' -FieldName 'schema') -cne 'pnl-staging-active-revision-v1') -or
        ([string](Get-PnlRequiredJsonProperty -Object $state -Name 'project' -FieldName 'project') -cne $ProjectId) -or
        ([string](Get-PnlRequiredJsonProperty -Object $state -Name 'project_number' -FieldName 'project_number') -cne $ProjectNumber) -or
        ([string](Get-PnlRequiredJsonProperty -Object $state -Name 'region' -FieldName 'region') -cne $Region) -or
        ([string](Get-PnlRequiredJsonProperty -Object $state -Name 'service' -FieldName 'service') -cne $Service) -or
        ([string](Get-PnlRequiredJsonProperty -Object $state -Name 'source_commit' -FieldName 'source_commit') -cne $ExpectedGitHead) -or
        ([string](Get-PnlRequiredJsonProperty -Object $state -Name 'release_identity' -FieldName 'release_identity') -cne $ExpectedGitHead) -or
        ([string](Get-PnlRequiredJsonProperty -Object $state -Name 'purpose' -FieldName 'purpose') -cne 'pre-release rollback target') -or
        ($validValue -isnot [bool]) -or
        (-not [bool]$validValue) -or
        (($trafficPercentValue -isnot [int]) -and ($trafficPercentValue -isnot [long])) -or
        ([long]$trafficPercentValue -ne 100) -or
        (-not $capturedAtValid)
    ) {
        throw 'Captured pre-release revision state does not match this release.'
    }
    $activeRevision = [string](Get-PnlRequiredJsonProperty `
        -Object $state `
        -Name 'active_revision' `
        -FieldName 'active_revision')
    Assert-PnlExplicitRevisionTarget -Revision $activeRevision -Service $Service | Out-Null
    return [pscustomobject][ordered]@{
        path = $resolvedStatePath
        valid = $true
        release_identity = $ExpectedGitHead
        service = $Service
        active_revision = $activeRevision
        traffic_percent = 100
        captured_at_utc = [string]$state.captured_at_utc
    }
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
    try {
        return ($json | ConvertFrom-Json -Depth 100)
    }
    catch {
        throw 'Cloud Run service describe returned malformed JSON.'
    }
}

function Get-LiveRevisionDescription {
    param([Parameter(Mandatory)] [string] $Revision)

    Assert-PnlExplicitRevisionTarget -Revision $Revision -Service $Service | Out-Null
    $json = Invoke-PnlGcloud -Arguments @(
        'run', 'revisions', 'describe', $Revision,
        "--project=$ProjectId",
        "--region=$Region",
        '--format=json',
        '--quiet'
    )
    if (-not $json) {
        throw 'Cloud Run revision describe returned no data.'
    }
    try {
        return ($json | ConvertFrom-Json -Depth 100)
    }
    catch {
        throw 'Cloud Run revision describe returned malformed JSON.'
    }
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

function Get-CloudRunZeroDefaultInteger {
    param(
        [Parameter(Mandatory)] [object] $Object,
        [Parameter(Mandatory)] [string] $Name,
        [Parameter(Mandatory)] [string] $FieldName
    )

    $property = $Object.PSObject.Properties[$Name]
    if ($null -eq $property) {
        return 0
    }
    if ($null -eq $property.Value) {
        throw "$FieldName must not be null."
    }
    return [int]$property.Value
}

function Assert-LiveServicePreservationContract {
    param(
        [Parameter(Mandatory)] [object] $Description,
        [Parameter(Mandatory)] [object] $ActiveRevisionDescription,
        [Parameter(Mandatory)] [ValidateSet('BACKEND_FIRST', 'FINAL_FRONTEND')] [string] $CandidateStage,
        [Parameter(Mandatory)] [string] $CandidateEdgeImage,
        [Parameter(Mandatory)] [string] $CandidateRuntimeImage,
        [AllowEmptyString()] [string] $ExpectedRevisionA,
        [AllowEmptyString()] [string] $ValidatedAEdgeImage,
        [AllowEmptyString()] [string] $ValidatedARuntimeImage,
        [AllowEmptyString()] [string] $RequestedRuntimeManifestJson
    )

    $metadata = Get-PnlRequiredJsonProperty -Object $Description -Name 'metadata' -FieldName 'metadata'
    if ([string](Get-PnlRequiredJsonProperty -Object $metadata -Name 'name' -FieldName 'metadata.name') -cne $Service) {
        throw 'Live service preflight returned an unexpected service name.'
    }
    if ([string](Get-PnlRequiredJsonProperty -Object $metadata -Name 'namespace' -FieldName 'metadata.namespace') -cne $ProjectNumber) {
        throw 'Live service preflight returned an unexpected project namespace.'
    }
    $activeBaseline = Get-PnlResolvedActiveRevisionBaseline `
        -ServiceDescription $Description `
        -RevisionDescription $ActiveRevisionDescription `
        -Service $Service
    $activeRevision = [string]$activeBaseline.active_revision
    $containers = @($Description.spec.template.spec.containers)
    if ($containers.Count -ne 2) {
        throw 'Live staging service must contain exactly two containers before candidate deployment.'
    }
    $edge = Get-ContainerByName -Description $Description -Name 'edge'
    $bff = Get-ContainerByName -Description $Description -Name 'bff'
    $observedEdgeImage = [string]$activeBaseline.edge_image
    $observedRuntimeImage = [string]$activeBaseline.runtime_image
    if ($CandidateStage -eq 'BACKEND_FIRST') {
        if (-not [string]::Equals($observedEdgeImage, $CandidateEdgeImage, [StringComparison]::Ordinal)) {
            throw 'Revision A frozen edge must exactly equal the current live service edge digest.'
        }
        if ([string]::Equals($observedRuntimeImage, $CandidateRuntimeImage, [StringComparison]::Ordinal)) {
            throw 'Revision A runtime must be a new immutable digest relative to the active runtime.'
        }
    }
    else {
        Assert-PnlDigestImage -Image ([string]$edge.image) -Role 'edge'
        Assert-PnlDigestImage -Image ([string]$bff.image) -Role 'runtime'
        if ([string]::IsNullOrWhiteSpace($ExpectedRevisionA)) {
            throw 'Revision B candidate creation requires a validated Revision A target.'
        }
        if (-not [string]::Equals($activeRevision, $ExpectedRevisionA, [StringComparison]::Ordinal)) {
            throw 'Revision B candidate creation requires deterministic Revision A, explicitly validated or same-HEAD derived, to be the current 100-percent revision.'
        }
        $runtimeAuthority = Assert-PnlRevisionBLineage `
            -FinalEdgeImage $CandidateEdgeImage `
            -RuntimeImage $CandidateRuntimeImage `
            -ValidatedRevisionAEdgeImage $ValidatedAEdgeImage `
            -ValidatedRevisionARuntimeImage $ValidatedARuntimeImage `
            -ObservedRevisionAEdgeImage $observedEdgeImage `
            -ObservedRevisionARuntimeImage $observedRuntimeImage `
            -RequestedRuntimeManifestJson $RequestedRuntimeManifestJson
    }
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
        $canonicalCurrentOrigins = ConvertTo-PnlApprovedStagingOriginValue -Origins $currentOriginValue
        if (
            $CandidateStage -eq 'FINAL_FRONTEND' -and
            -not [string]::Equals($currentOriginValue, $canonicalCurrentOrigins, [StringComparison]::Ordinal)
        ) {
            throw 'Revision B preflight requires Revision A to contain the canonical approved origin order.'
        }
    }
    else {
        if ($CandidateStage -eq 'FINAL_FRONTEND') {
            throw 'Revision B preflight requires the exact two-origin state established by Revision A.'
        }
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
    $edgeStartupInitialDelay = Get-CloudRunZeroDefaultInteger `
        -Object $edge.startupProbe `
        -Name 'initialDelaySeconds' `
        -FieldName 'edge.startupProbe.initialDelaySeconds'
    if (
        [string]$edge.startupProbe.httpGet.path -ne '/health/ready' -or
        [int]$edge.startupProbe.httpGet.port -ne 8080 -or
        $edgeStartupInitialDelay -ne 0 -or
        [int]$edge.startupProbe.timeoutSeconds -ne 3 -or
        [int]$edge.startupProbe.periodSeconds -ne 5 -or
        [int]$edge.startupProbe.failureThreshold -ne 24
    ) {
        throw 'Live edge startup probe drifted.'
    }
    $runtimeStartupInitialDelay = Get-CloudRunZeroDefaultInteger `
        -Object $bff.startupProbe `
        -Name 'initialDelaySeconds' `
        -FieldName 'bff.startupProbe.initialDelaySeconds'
    if (
        [string]$bff.startupProbe.httpGet.path -ne '/health/ready' -or
        [int]$bff.startupProbe.httpGet.port -ne 8000 -or
        $runtimeStartupInitialDelay -ne 0 -or
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
    return [pscustomobject][ordered]@{
        project = $ProjectId
        project_number = $ProjectNumber
        region = $Region
        service = $Service
        stage = $CandidateStage
        contract_valid = $true
        active_revision = $activeRevision
        traffic_percent = 100
        active_revision_ready = [bool]$activeBaseline.ready
        active_image_source = [string]$activeBaseline.source
        observed_edge_image = $observedEdgeImage
        observed_runtime_image = $observedRuntimeImage
        validated_revision_a = if ($CandidateStage -eq 'FINAL_FRONTEND') { $ExpectedRevisionA } else { $null }
        validated_revision_a_edge_image = if ($CandidateStage -eq 'FINAL_FRONTEND') { $ValidatedAEdgeImage } else { $null }
        validated_revision_a_runtime_image = if ($CandidateStage -eq 'FINAL_FRONTEND') { $ValidatedARuntimeImage } else { $null }
        revision_a_runtime_authority = if ($CandidateStage -eq 'FINAL_FRONTEND') { $runtimeAuthority } else { $null }
        origins = $currentOriginValue
        edge_port = 8080
        dependency = 'edge->bff'
    }
}

function Write-ActiveRevisionState {
    param(
        [Parameter(Mandatory)] [object] $Description,
        [Parameter(Mandatory)] [string] $Path,
        [AllowEmptyString()] [string] $SourceCommit,
        [Parameter(Mandatory)] [string] $Purpose
    )
    $resolvedPath = Resolve-ReleaseStatePath -Path $Path
    New-Item -ItemType Directory -Force -Path (Split-Path $resolvedPath -Parent) | Out-Null
    $active = Get-PnlActiveRevision -ServiceDescription $Description -Service $Service
    $state = [ordered]@{
        schema = 'pnl-staging-active-revision-v1'
        captured_at_utc = [DateTime]::UtcNow.ToString('o')
        purpose = $Purpose
        valid = $true
        project = $ProjectId
        project_number = $ProjectNumber
        region = $Region
        service = $Service
        source_commit = $SourceCommit
        release_identity = $SourceCommit
        active_revision = $active
        traffic_percent = 100
    }
    if (Test-Path -LiteralPath $resolvedPath -PathType Leaf) {
        try {
            $existing = Get-Content -Raw -LiteralPath $resolvedPath | ConvertFrom-Json -Depth 20
        }
        catch {
            throw 'Existing active-revision state is not valid JSON.'
        }
        $existingValid = Get-PnlRequiredJsonProperty -Object $existing -Name 'valid' -FieldName 'valid'
        $existingTraffic = Get-PnlRequiredJsonProperty -Object $existing -Name 'traffic_percent' -FieldName 'traffic_percent'
        $existingCapturedAt = [DateTimeOffset]::MinValue
        $existingCapturedAtValid = [DateTimeOffset]::TryParse(
            [string](Get-PnlRequiredJsonProperty -Object $existing -Name 'captured_at_utc' -FieldName 'captured_at_utc'),
            [ref]$existingCapturedAt
        )
        if (
            ([string](Get-PnlRequiredJsonProperty -Object $existing -Name 'schema' -FieldName 'schema') -cne [string]$state.schema) -or
            ([string](Get-PnlRequiredJsonProperty -Object $existing -Name 'project' -FieldName 'project') -cne [string]$state.project) -or
            ([string](Get-PnlRequiredJsonProperty -Object $existing -Name 'project_number' -FieldName 'project_number') -cne [string]$state.project_number) -or
            ([string](Get-PnlRequiredJsonProperty -Object $existing -Name 'region' -FieldName 'region') -cne [string]$state.region) -or
            ([string](Get-PnlRequiredJsonProperty -Object $existing -Name 'service' -FieldName 'service') -cne [string]$state.service) -or
            ([string](Get-PnlRequiredJsonProperty -Object $existing -Name 'source_commit' -FieldName 'source_commit') -cne [string]$state.source_commit) -or
            ([string](Get-PnlRequiredJsonProperty -Object $existing -Name 'release_identity' -FieldName 'release_identity') -cne [string]$state.release_identity) -or
            ($existingValid -isnot [bool]) -or
            (-not [bool]$existingValid) -or
            (($existingTraffic -isnot [int]) -and ($existingTraffic -isnot [long])) -or
            ([long]$existingTraffic -ne 100) -or
            (-not $existingCapturedAtValid) -or
            ([string](Get-PnlRequiredJsonProperty -Object $existing -Name 'purpose' -FieldName 'purpose') -cne [string]$state.purpose) -or
            ([string](Get-PnlRequiredJsonProperty -Object $existing -Name 'active_revision' -FieldName 'active_revision') -cne [string]$state.active_revision)
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

function Resolve-ValidatedRevisionATarget {
    param(
        [Parameter(Mandatory)] [string] $CandidateGitHead,
        [AllowEmptyString()] [string] $ExplicitRevision
    )

    if ([string]::IsNullOrWhiteSpace($ExplicitRevision)) {
        return (
            Get-PnlStagingReleaseIdentity -Stage 'BACKEND_FIRST' -GitHead $CandidateGitHead -Service $Service
        ).revision_name
    }
    $validatedTarget = Assert-PnlExplicitRevisionTarget -Revision $ExplicitRevision -Service $Service
    $backendFirstPattern = '^' + [regex]::Escape($Service) + '-pnlbe-[0-9a-f]{40}$'
    if ($validatedTarget -cnotmatch $backendFirstPattern) {
        throw 'ValidatedRevisionA must be an exact backend-first revision of the staging service.'
    }
    return $validatedTarget
}

function Assert-PromotionRevisionAContract {
    param(
        [Parameter(Mandatory)] [object] $ServiceDescription,
        [Parameter(Mandatory)] [object] $RevisionDescription,
        [Parameter(Mandatory)] [string] $ExpectedRevisionA
    )

    $activeBaseline = Get-PnlResolvedActiveRevisionBaseline `
        -ServiceDescription $ServiceDescription `
        -RevisionDescription $RevisionDescription `
        -Service $Service
    if (-not [string]::Equals(
        [string]$activeBaseline.active_revision,
        $ExpectedRevisionA,
        [StringComparison]::Ordinal
    )) {
        throw 'Promotion-time active revision does not match the validated Revision A.'
    }
    return [pscustomobject][ordered]@{
        result = 'PASS'
        active_revision = [string]$activeBaseline.active_revision
        traffic_percent = [long]$activeBaseline.traffic_percent
        active_revision_ready = [bool]$activeBaseline.ready
        observed_edge_image = [string]$activeBaseline.edge_image
        observed_runtime_image = [string]$activeBaseline.runtime_image
    }
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
    $validatedRevisionATarget = $null
    $requestedRuntimeManifestJson = ''
    $resolvedRuntimeManifestPath = $null
    if (-not [string]::IsNullOrWhiteSpace($RuntimeManifestJsonPath)) {
        if ($Stage -ne 'FINAL_FRONTEND') {
            throw 'RuntimeManifestJsonPath is accepted only for FINAL_FRONTEND runtime lineage validation.'
        }
        $resolvedRuntimeManifestPath = [IO.Path]::GetFullPath($RuntimeManifestJsonPath)
        if (-not (Test-Path -LiteralPath $resolvedRuntimeManifestPath -PathType Leaf)) {
            throw 'RuntimeManifestJsonPath does not identify a readable raw manifest JSON file.'
        }
        $requestedRuntimeManifestJson = [IO.File]::ReadAllText($resolvedRuntimeManifestPath)
        if ([string]::IsNullOrWhiteSpace($requestedRuntimeManifestJson)) {
            throw 'RuntimeManifestJsonPath must contain an exact raw manifest inspection.'
        }
    }
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
    Assert-PnlCandidateTag -Tag $CandidateTag | Out-Null

    $preReleaseBaseline = $null
    if ($Stage -eq 'BACKEND_FIRST') {
        Assert-RequiredText -Name 'FrozenEdgeImage' -Value $FrozenEdgeImage
        Assert-RequiredText -Name 'PreReleaseStatePath' -Value $PreReleaseStatePath
        $preReleaseBaseline = Read-ValidatedPreReleaseState `
            -Path $PreReleaseStatePath `
            -ExpectedGitHead $GitHead
        if (
            -not [string]::IsNullOrWhiteSpace($FinalEdgeImage) -or
            -not [string]::IsNullOrWhiteSpace($ValidatedRevisionA) -or
            -not [string]::IsNullOrWhiteSpace($ValidatedRevisionAEdgeImage) -or
            -not [string]::IsNullOrWhiteSpace($ValidatedRevisionARuntimeImage)
        ) {
            throw 'BACKEND_FIRST accepts only the frozen edge and new runtime image inputs.'
        }
        $edgeImage = $FrozenEdgeImage
        $releaseStage = 'pnl-backend-first'
    }
    else {
        Assert-RequiredText -Name 'FinalEdgeImage' -Value $FinalEdgeImage
        Assert-RequiredText -Name 'ValidatedRevisionAEdgeImage' -Value $ValidatedRevisionAEdgeImage
        Assert-RequiredText -Name 'ValidatedRevisionARuntimeImage' -Value $ValidatedRevisionARuntimeImage
        $validatedRevisionATarget = Resolve-ValidatedRevisionATarget `
            -CandidateGitHead $GitHead `
            -ExplicitRevision $ValidatedRevisionA
        if (-not [string]::IsNullOrWhiteSpace($PreReleaseStatePath)) {
            throw 'FINAL_FRONTEND candidate creation does not accept a pre-release rollback state path.'
        }
        if (-not [string]::IsNullOrWhiteSpace($FrozenEdgeImage)) {
            throw 'FINAL_FRONTEND must not accept a frozen edge image.'
        }
        $edgeImage = $FinalEdgeImage
        $releaseStage = 'pnl-final-frontend'
        Assert-PnlRevisionBLineage `
            -FinalEdgeImage $FinalEdgeImage `
            -RuntimeImage $RuntimeImage `
            -ValidatedRevisionAEdgeImage $ValidatedRevisionAEdgeImage `
            -ValidatedRevisionARuntimeImage $ValidatedRevisionARuntimeImage
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

    $candidateArguments = @(
        'run', 'deploy', $Service,
        '--quiet',
        "--project=$ProjectId",
        "--region=$Region",
        "--revision-suffix=$RevisionSuffix",
        "--tag=$CandidateTag",
        '--no-traffic',
        "--update-labels=source-commit=$GitHead,release-stage=$releaseStage,business-gate=passed",
        '--container=edge',
        "--image=$edgeImage",
        '--port=8080',
        '--depends-on=bff',
        '--container=bff',
        "--image=$RuntimeImage",
        "--update-env-vars=^@^BFF_ALLOWED_ORIGINS=$originValue"
    )
    if ($candidateArguments -contains '--platform=managed') {
        throw 'Candidate command must not use the unsupported --platform flag.'
    }

    $servicePreflight = [ordered]@{
        required = $true
        evaluated = $false
        source = $null
        active_revision_source = $null
        result = $null
    }
    $hasCapturedService = -not [string]::IsNullOrWhiteSpace($CapturedServiceJsonPath)
    $hasCapturedActiveRevision = -not [string]::IsNullOrWhiteSpace($CapturedActiveRevisionJsonPath)
    if ($hasCapturedService -xor $hasCapturedActiveRevision) {
        throw 'CapturedServiceJsonPath and CapturedActiveRevisionJsonPath must be supplied together.'
    }
    if ($hasCapturedService) {
        if ($Execute) {
            throw 'Captured service and active-revision JSON paths are offline-only inputs and cannot be combined with Execute.'
        }
        $resolvedCapturedServicePath = [IO.Path]::GetFullPath($CapturedServiceJsonPath)
        if (-not (Test-Path -LiteralPath $resolvedCapturedServicePath -PathType Leaf)) {
            throw 'CapturedServiceJsonPath does not identify a readable service JSON fixture.'
        }
        $resolvedCapturedActiveRevisionPath = [IO.Path]::GetFullPath($CapturedActiveRevisionJsonPath)
        if (-not (Test-Path -LiteralPath $resolvedCapturedActiveRevisionPath -PathType Leaf)) {
            throw 'CapturedActiveRevisionJsonPath does not identify a readable revision JSON fixture.'
        }
        try {
            $capturedDescription = Get-Content -Raw -LiteralPath $resolvedCapturedServicePath | ConvertFrom-Json -Depth 100
        }
        catch {
            throw 'CapturedServiceJsonPath must contain valid Cloud Run service JSON.'
        }
        try {
            $capturedActiveRevisionDescription = Get-Content -Raw -LiteralPath $resolvedCapturedActiveRevisionPath | ConvertFrom-Json -Depth 100
        }
        catch {
            throw 'CapturedActiveRevisionJsonPath must contain valid Cloud Run revision JSON.'
        }
        $preflightResult = Assert-LiveServicePreservationContract `
            -Description $capturedDescription `
            -ActiveRevisionDescription $capturedActiveRevisionDescription `
            -CandidateStage $Stage `
            -CandidateEdgeImage $edgeImage `
            -CandidateRuntimeImage $RuntimeImage `
            -ExpectedRevisionA $validatedRevisionATarget `
            -ValidatedAEdgeImage $ValidatedRevisionAEdgeImage `
            -ValidatedARuntimeImage $ValidatedRevisionARuntimeImage `
            -RequestedRuntimeManifestJson $requestedRuntimeManifestJson
        $servicePreflight = [ordered]@{
            required = $true
            evaluated = $true
            source = $resolvedCapturedServicePath
            active_revision_source = $resolvedCapturedActiveRevisionPath
            result = $preflightResult
        }
    }
    elseif ($Execute) {
        if ($MutationApproval -ne 'APPROVE_STAGING_CANDIDATE') {
            throw 'Candidate execution requires MutationApproval=APPROVE_STAGING_CANDIDATE.'
        }
        $null = Assert-GcloudCandidateCapabilities
        $liveDescription = Get-LiveServiceDescription
        $liveActiveRevision = Get-PnlActiveRevision -ServiceDescription $liveDescription -Service $Service
        $liveActiveRevisionDescription = Get-LiveRevisionDescription -Revision $liveActiveRevision
        $preflightResult = Assert-LiveServicePreservationContract `
            -Description $liveDescription `
            -ActiveRevisionDescription $liveActiveRevisionDescription `
            -CandidateStage $Stage `
            -CandidateEdgeImage $edgeImage `
            -CandidateRuntimeImage $RuntimeImage `
            -ExpectedRevisionA $validatedRevisionATarget `
            -ValidatedAEdgeImage $ValidatedRevisionAEdgeImage `
            -ValidatedARuntimeImage $ValidatedRevisionARuntimeImage `
            -RequestedRuntimeManifestJson $requestedRuntimeManifestJson
        $servicePreflight = [ordered]@{
            required = $true
            evaluated = $true
            source = 'live promotion-safe service recapture'
            active_revision_source = 'live exact active revision describe'
            result = $preflightResult
        }
    }
    if (
        $Stage -eq 'BACKEND_FIRST' -and
        $servicePreflight.evaluated -and
        -not [string]::Equals(
            [string]$servicePreflight.result.active_revision,
            [string]$preReleaseBaseline.active_revision,
            [StringComparison]::Ordinal
        )
    ) {
        throw 'Revision A candidate preflight active revision must match the persisted pre-release rollback baseline.'
    }
    $plannedGcloudExecutable = Get-PlannedGcloudExecutable
    $candidateRollbackKind = if ($Stage -eq 'BACKEND_FIRST') { 'REVISION_A_TO_PRE_RELEASE' } else { 'REVISION_B_TO_A' }
    $candidateRollbackTarget = if ($Stage -eq 'BACKEND_FIRST') {
        $preReleaseBaseline.active_revision
    }
    else {
        $validatedRevisionATarget
    }
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
        production_traffic_percent = 0
        edge_image = $edgeImage
        runtime_image = $RuntimeImage
        validated_revision_a = if ($Stage -eq 'FINAL_FRONTEND') { $validatedRevisionATarget } else { $null }
        validated_revision_a_edge_image = if ($Stage -eq 'FINAL_FRONTEND') { $ValidatedRevisionAEdgeImage } else { $null }
        validated_revision_a_runtime_image = if ($Stage -eq 'FINAL_FRONTEND') { $ValidatedRevisionARuntimeImage } else { $null }
        revision_a_edge_lineage = if ($Stage -eq 'FINAL_FRONTEND') { 'validated' } else { 'not-applicable' }
        revision_a_runtime_lineage = if ($Stage -eq 'FINAL_FRONTEND') { 'validated' } else { 'not-applicable' }
        revision_a_runtime_authority = if ($Stage -eq 'FINAL_FRONTEND' -and $servicePreflight.evaluated) {
            $servicePreflight.result.revision_a_runtime_authority
        }
        else {
            $null
        }
        runtime_manifest_source = if ($Stage -eq 'FINAL_FRONTEND') { $resolvedRuntimeManifestPath } else { $null }
        approved_origins = @($originValue.Split([char]','))
        rendered_manifest = $webManifestPath
        service_preflight = $servicePreflight
        active_revision_capture_command = ConvertTo-CommandText -Arguments $describeArguments
        smoke_gate_state = if ([string]::IsNullOrWhiteSpace($SmokeGate)) { 'not-applicable-before-smoke' } else { $SmokeGate }
        rollback_operation_type = $candidateRollbackKind
        rollback_target = $candidateRollbackTarget
        rollback_state_path = if ($Stage -eq 'BACKEND_FIRST') { $preReleaseBaseline.path } else { $null }
        rollback_baseline = if ($Stage -eq 'BACKEND_FIRST') { $preReleaseBaseline } else { $null }
        gcloud = [ordered]@{
            executable_requested = $GcloudPath
            executable_resolved = $plannedGcloudExecutable
            arguments = $candidateArguments
            windows_cmd_arguments = @(ConvertTo-PnlGcloudExecutionArguments -Arguments $candidateArguments -WindowsCmdShim $true)
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
    Invoke-PnlGcloud -Arguments $candidateArguments | Out-Host
    Write-Output "CANDIDATE_CREATED=PASS revision=$($identity.revision_name) traffic=0 tag=$($identity.candidate_tag)"
    return
}

if ($Operation -eq 'CAPTURE_ACTIVE') {
    Assert-RequiredText -Name 'GitHead' -Value $GitHead
    if ($GitHead -notmatch '^[0-9a-f]{40}$') {
        throw 'GitHead must be a full lowercase 40-character Git commit.'
    }
    $statePath = if ([string]::IsNullOrWhiteSpace($PreReleaseStatePath)) {
        Join-Path $resolvedOutputDirectory "pre-release-$GitHead.json"
    }
    else {
        $PreReleaseStatePath
    }
    $statePath = Resolve-ReleaseStatePath -Path $statePath
    $plan = [ordered]@{
        schema = 'pnl-staging-release-plan-v1'
        operation = 'CAPTURE_ACTIVE'
        dry_run = -not $Execute
        cloud_mutation = $false
        project = $ProjectId
        region = $Region
        service = $Service
        source_commit = $GitHead
        release_identity = $GitHead
        purpose = 'pre-release rollback target'
        resolved_active_revision_capture_required = $true
        resolved_active_revision_capture_operation = 'run revisions describe <exact 100-percent revisionName>'
        output = [IO.Path]::GetFullPath($statePath)
        gcloud = [ordered]@{
            executable_requested = $GcloudPath
            executable_resolved = Get-PlannedGcloudExecutable
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
    $activeRevision = Get-PnlActiveRevision -ServiceDescription $description -Service $Service
    $activeRevisionDescription = Get-LiveRevisionDescription -Revision $activeRevision
    $resolvedBaseline = Get-PnlResolvedActiveRevisionBaseline `
        -ServiceDescription $description `
        -RevisionDescription $activeRevisionDescription `
        -Service $Service
    $capturedServicePath = Write-ReleaseArtifact `
        -Name 'captured-active-service' `
        -Payload $description
    $capturedActiveRevisionPath = Write-ReleaseArtifact `
        -Name 'captured-active-revision' `
        -Payload $activeRevisionDescription
    $capturedBaselinePath = Write-ReleaseArtifact `
        -Name 'captured-active-resolved-baseline' `
        -Payload ([ordered]@{
            schema = 'pnl-staging-resolved-active-baseline-v1'
            captured_at_utc = [DateTime]::UtcNow.ToString('o')
            project = $ProjectId
            project_number = $ProjectNumber
            region = $Region
            service = $Service
            source_commit = $GitHead
            active_revision = [string]$resolvedBaseline.active_revision
            traffic_percent = [long]$resolvedBaseline.traffic_percent
            ready = [bool]$resolvedBaseline.ready
            resolved_edge_image = [string]$resolvedBaseline.edge_image
            resolved_runtime_image = [string]$resolvedBaseline.runtime_image
            source = [string]$resolvedBaseline.source
            captured_service_json = $capturedServicePath
            captured_active_revision_json = $capturedActiveRevisionPath
            cloud_mutation = $false
        })
    $active = Write-ActiveRevisionState `
        -Description $description `
        -Path $statePath `
        -SourceCommit $GitHead `
        -Purpose 'pre-release rollback target'
    Write-Output (
        "ACTIVE_REVISION_CAPTURED=PASS revision=$active traffic=100 ready=True " +
        "resolved_edge=$($resolvedBaseline.edge_image) resolved_runtime=$($resolvedBaseline.runtime_image) " +
        "service_json=$capturedServicePath revision_json=$capturedActiveRevisionPath " +
        "baseline_json=$capturedBaselinePath path=$([IO.Path]::GetFullPath($statePath)) cloud_mutation=NONE"
    )
    return
}

if ($Operation -eq 'PROMOTE') {
    $identity = Assert-StageAndHead
    $validatedRevisionATarget = $null
    $explicitValidatedRevisionA = $false
    if ($Stage -eq 'FINAL_FRONTEND') {
        $explicitValidatedRevisionA = -not [string]::IsNullOrWhiteSpace($ValidatedRevisionA)
        $validatedRevisionATarget = Resolve-ValidatedRevisionATarget `
            -CandidateGitHead $GitHead `
            -ExplicitRevision $ValidatedRevisionA
    }
    elseif (-not [string]::IsNullOrWhiteSpace($ValidatedRevisionA)) {
        throw 'ValidatedRevisionA is accepted only for FINAL_FRONTEND promotion.'
    }
    if ($SmokeGate -ne 'passed') {
        throw 'Promotion command generation requires SmokeGate=passed from the candidate-specific smoke.'
    }
    Assert-RequiredText -Name 'Revision' -Value $Revision
    Assert-PnlExplicitRevisionTarget -Revision $Revision -Service $Service | Out-Null
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
    $preReleaseBaseline = $null
    if ($Stage -eq 'FINAL_FRONTEND' -and -not [string]::IsNullOrWhiteSpace($PreReleaseStatePath)) {
        throw 'FINAL_FRONTEND promotion does not accept a pre-release rollback state path.'
    }
    $capturePath = if ($Stage -eq 'BACKEND_FIRST') {
        Assert-RequiredText -Name 'PreReleaseStatePath' -Value $PreReleaseStatePath
        $preReleaseBaseline = Read-ValidatedPreReleaseState `
            -Path $PreReleaseStatePath `
            -ExpectedGitHead $GitHead
        $preReleaseBaseline.path
    }
    else {
        Join-Path $resolvedOutputDirectory "pre-final-$($identity.head_token).json"
    }
    $capturePath = Resolve-ReleaseStatePath -Path $capturePath
    $capturePurpose = if ($Stage -eq 'BACKEND_FIRST') {
        'pre-release rollback target'
    }
    else {
        'Revision B pre-promotion evidence'
    }
    $rollbackKind = if ($Stage -eq 'BACKEND_FIRST') { 'REVISION_A_TO_PRE_RELEASE' } else { 'REVISION_B_TO_A' }
    $rollbackTarget = if ($Stage -eq 'BACKEND_FIRST') {
        $preReleaseBaseline.active_revision
    }
    else {
        $validatedRevisionATarget
    }
    $offlinePromotionRecapture = [ordered]@{
        required = $true
        evaluated = $false
        active_revision = $null
    }
    $promotionRevisionAValidation = [ordered]@{
        required = $explicitValidatedRevisionA
        evaluated = $false
        source = $null
        result = $null
    }
    if (
        -not [string]::IsNullOrWhiteSpace($CapturedActiveRevisionJsonPath) -and
        [string]::IsNullOrWhiteSpace($CapturedServiceJsonPath)
    ) {
        throw 'CapturedActiveRevisionJsonPath requires CapturedServiceJsonPath during promotion.'
    }
    if (-not [string]::IsNullOrWhiteSpace($CapturedServiceJsonPath)) {
        if ($Execute) {
            throw 'CapturedServiceJsonPath is offline-only input and cannot be combined with promotion Execute.'
        }
        $resolvedPromotionServicePath = [IO.Path]::GetFullPath($CapturedServiceJsonPath)
        if (-not (Test-Path -LiteralPath $resolvedPromotionServicePath -PathType Leaf)) {
            throw 'CapturedServiceJsonPath does not identify a readable promotion-time service JSON fixture.'
        }
        try {
            $promotionDescription = Get-Content -Raw -LiteralPath $resolvedPromotionServicePath | ConvertFrom-Json -Depth 100
        }
        catch {
            throw 'Promotion-time CapturedServiceJsonPath must contain valid Cloud Run service JSON.'
        }
        $capturedActive = Get-PnlActiveRevision -ServiceDescription $promotionDescription -Service $Service
        if ([string]::Equals($capturedActive, $Revision, [StringComparison]::Ordinal)) {
            throw 'The explicit promotion target already serves 100 percent traffic.'
        }
        if ($Stage -eq 'FINAL_FRONTEND') {
            if (-not [string]::Equals($capturedActive, $validatedRevisionATarget, [StringComparison]::Ordinal)) {
                throw 'FINAL_FRONTEND promotion requires the validated Revision A to be the current 100-percent revision.'
            }
            if ($explicitValidatedRevisionA) {
                Assert-RequiredText `
                    -Name 'CapturedActiveRevisionJsonPath' `
                    -Value $CapturedActiveRevisionJsonPath
                $resolvedPromotionActiveRevisionPath = [IO.Path]::GetFullPath($CapturedActiveRevisionJsonPath)
                if (-not (Test-Path -LiteralPath $resolvedPromotionActiveRevisionPath -PathType Leaf)) {
                    throw 'CapturedActiveRevisionJsonPath does not identify readable Revision A evidence.'
                }
                try {
                    $promotionActiveRevisionDescription = Get-Content `
                        -Raw `
                        -LiteralPath $resolvedPromotionActiveRevisionPath | ConvertFrom-Json -Depth 100
                }
                catch {
                    throw 'CapturedActiveRevisionJsonPath must contain valid Cloud Run revision JSON.'
                }
                $promotionPreflight = Assert-PromotionRevisionAContract `
                    -ServiceDescription $promotionDescription `
                    -RevisionDescription $promotionActiveRevisionDescription `
                    -ExpectedRevisionA $validatedRevisionATarget
                $promotionRevisionAValidation = [ordered]@{
                    required = $true
                    evaluated = $true
                    source = $resolvedPromotionActiveRevisionPath
                    result = $promotionPreflight
                }
            }
        }
        elseif (-not [string]::Equals(
            $capturedActive,
            [string]$preReleaseBaseline.active_revision,
            [StringComparison]::Ordinal
        )) {
            throw 'Revision A promotion-time active revision must match the persisted pre-release rollback baseline.'
        }
        $offlinePromotionRecapture = [ordered]@{
            required = $true
            evaluated = $true
            source = $resolvedPromotionServicePath
            active_revision = $capturedActive
        }
    }
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
        validated_revision_a = if ($Stage -eq 'FINAL_FRONTEND') { $validatedRevisionATarget } else { $null }
        smoke_gate_required = 'passed'
        smoke_gate = $SmokeGate
        capture_current_100_percent_revision_before_promotion = $true
        capture_output = $capturePath
        capture_command = ConvertTo-CommandText -Arguments $describeArguments
        promotion_time_active_recapture = $offlinePromotionRecapture
        promotion_revision_a_validation = $promotionRevisionAValidation
        rollback_operation_type = $rollbackKind
        rollback_target = $rollbackTarget
        rollback_baseline = if ($Stage -eq 'BACKEND_FIRST') { $preReleaseBaseline } else { $null }
        gcloud = [ordered]@{
            executable_requested = $GcloudPath
            executable_resolved = Get-PlannedGcloudExecutable
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
    $null = Assert-GcloudTrafficCapabilities
    $description = Get-LiveServiceDescription
    $active = Get-PnlActiveRevision -ServiceDescription $description -Service $Service
    if ([string]::Equals($active, $Revision, [StringComparison]::Ordinal)) {
        throw 'The explicit promotion target already serves 100 percent traffic.'
    }
    if ($Stage -eq 'FINAL_FRONTEND') {
        if (-not [string]::Equals($active, $validatedRevisionATarget, [StringComparison]::Ordinal)) {
            throw 'FINAL_FRONTEND promotion requires the validated Revision A to be the current 100-percent revision.'
        }
        if ($explicitValidatedRevisionA) {
            $liveActiveRevisionDescription = Get-LiveRevisionDescription -Revision $validatedRevisionATarget
            $promotionPreflight = Assert-PromotionRevisionAContract `
                -ServiceDescription $description `
                -RevisionDescription $liveActiveRevisionDescription `
                -ExpectedRevisionA $validatedRevisionATarget
            $plan['promotion_time_active_recapture'] = [ordered]@{
                required = $true
                evaluated = $true
                source = 'live promotion-time service recapture'
                active_revision = $active
            }
            $plan['promotion_revision_a_validation'] = [ordered]@{
                required = $true
                evaluated = $true
                source = 'live exact active revision describe'
                result = $promotionPreflight
            }
            $artifactPath = Write-ReleaseArtifact `
                -Name "promote-$($Stage.ToLowerInvariant().Replace('_', '-'))" `
                -Payload $plan `
                -CommandArguments $promotionArguments
        }
    }
    elseif (-not [string]::Equals(
        $active,
        [string]$preReleaseBaseline.active_revision,
        [StringComparison]::Ordinal
    )) {
        throw 'Revision A promotion-time active revision must match the persisted pre-release rollback baseline.'
    }
    $active = Write-ActiveRevisionState `
        -Description $description `
        -Path $capturePath `
        -SourceCommit $GitHead `
        -Purpose $capturePurpose
    Invoke-PnlGcloud -Arguments $promotionArguments | Out-Host
    Write-Output "PROMOTION=PASS revision=$Revision traffic=100 previous=$active"
    return
}

if ($Operation -eq 'ROLLBACK') {
    Assert-RequiredText -Name 'RollbackKind' -Value $RollbackKind
    Assert-RequiredText -Name 'GitHead' -Value $GitHead
    $backendIdentity = Get-PnlStagingReleaseIdentity -Stage 'BACKEND_FIRST' -GitHead $GitHead -Service $Service
    if ($RollbackKind -eq 'REVISION_B_TO_A') {
        if (-not [string]::IsNullOrWhiteSpace($PreReleaseStatePath)) {
            throw 'REVISION_B_TO_A must not accept a generic pre-release state target.'
        }
        $targetRevision = $backendIdentity.revision_name
        $rollbackSource = 'deterministic Revision A identity'
    }
    elseif ($RollbackKind -eq 'REVISION_A_TO_PRE_RELEASE') {
        Assert-RequiredText -Name 'PreReleaseStatePath' -Value $PreReleaseStatePath
        $preReleaseBaseline = Read-ValidatedPreReleaseState `
            -Path $PreReleaseStatePath `
            -ExpectedGitHead $GitHead
        $targetRevision = $preReleaseBaseline.active_revision
        $rollbackSource = $preReleaseBaseline.path
    }
    else {
        if (-not [string]::IsNullOrWhiteSpace($PreReleaseStatePath)) {
            throw 'GOLDEN fallback must not accept a generic pre-release state target.'
        }
        if ($IncidentApproval -ne 'APPROVE_GOLDEN_INCIDENT_ROLLBACK') {
            throw 'Golden rollback command generation requires explicit incident approval.'
        }
        $targetRevision = 'pnl-web-golden-1e478b6'
        $rollbackSource = 'incident-only frozen golden revision'
    }
    Assert-PnlExplicitRevisionTarget -Revision $targetRevision -Service $Service | Out-Null

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
        incident_approval = if ($RollbackKind -eq 'GOLDEN') { 'approved' } else { 'not-applicable' }
        gcloud = [ordered]@{
            executable_requested = $GcloudPath
            executable_resolved = Get-PlannedGcloudExecutable
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
    $null = Assert-GcloudTrafficCapabilities
    Invoke-PnlGcloud -Arguments $rollbackArguments | Out-Host
    Write-Output "ROLLBACK=PASS kind=$RollbackKind revision=$targetRevision traffic=100"
    return
}

throw "Unsupported release operation: $Operation"
