Set-StrictMode -Version Latest

$script:PnlStagingProjectId = 'pnl-dashboard-staging'
$script:PnlStagingProjectNumber = '498160536475'
$script:PnlStagingRegion = 'asia-southeast1'
$script:PnlStagingService = 'pnl-web'
$script:PnlCanonicalOrigin = 'https://pnl-web-498160536475.asia-southeast1.run.app'
$script:PnlStatusOrigin = 'https://pnl-web-t4n4rdoznq-as.a.run.app'

function Get-PnlApprovedStagingOrigins {
    return @($script:PnlCanonicalOrigin, $script:PnlStatusOrigin)
}

function Assert-PnlApprovedStagingOrigin {
    param([Parameter(Mandatory)] [string] $Origin)

    if (-not [string]::Equals($Origin, $Origin.Trim(), [StringComparison]::Ordinal)) {
        throw 'Approved staging origins must not contain leading or trailing whitespace.'
    }
    $originUri = $null
    if (
        -not [Uri]::TryCreate($Origin, [UriKind]::Absolute, [ref] $originUri) -or
        $originUri.Scheme -cne 'https' -or
        -not [string]::IsNullOrEmpty($originUri.UserInfo) -or
        -not [string]::IsNullOrEmpty($originUri.Query) -or
        -not [string]::IsNullOrEmpty($originUri.Fragment) -or
        $originUri.AbsolutePath -cne '/' -or
        $Origin.EndsWith('/', [StringComparison]::Ordinal) -or
        $Origin.Contains('*', [StringComparison]::Ordinal) -or
        $originUri.IsLoopback -or
        $originUri.Host -ceq 'localhost' -or
        $originUri.Host.EndsWith('.localhost', [StringComparison]::Ordinal)
    ) {
        throw 'Approved staging origins must be well-formed non-loopback HTTPS origins without paths, queries, fragments, or wildcards.'
    }
    if (-not (
        [string]::Equals($Origin, $script:PnlCanonicalOrigin, [StringComparison]::Ordinal) -or
        [string]::Equals($Origin, $script:PnlStatusOrigin, [StringComparison]::Ordinal)
    )) {
        throw 'Origin is not one of the two exact approved pnl-web staging origins.'
    }
}

function ConvertTo-PnlApprovedStagingOriginValue {
    param([Parameter(Mandatory)] [string] $Origins)

    $expected = "$script:PnlCanonicalOrigin,$script:PnlStatusOrigin"
    $items = $Origins.Split([char]',', [StringSplitOptions]::None)
    if ($items.Count -ne 2) {
        throw 'ApprovedOrigins must contain exactly two origins.'
    }
    foreach ($origin in $items) {
        Assert-PnlApprovedStagingOrigin -Origin $origin
    }
    if (@($items | Sort-Object -Unique).Count -ne 2) {
        throw 'ApprovedOrigins must not contain duplicates.'
    }
    return $expected
}

function Assert-PnlStagingTarget {
    param(
        [Parameter(Mandatory)] [string] $ProjectId,
        [Parameter(Mandatory)] [string] $ProjectNumber,
        [Parameter(Mandatory)] [string] $Region,
        [Parameter(Mandatory)] [string] $Service
    )

    if (-not [string]::Equals($ProjectId, $script:PnlStagingProjectId, [StringComparison]::Ordinal)) {
        throw 'Release tooling is pinned to the exact pnl-dashboard-staging project.'
    }
    if (-not [string]::Equals($ProjectNumber, $script:PnlStagingProjectNumber, [StringComparison]::Ordinal)) {
        throw 'Release tooling is pinned to staging project number 498160536475.'
    }
    if (-not [string]::Equals($Region, $script:PnlStagingRegion, [StringComparison]::Ordinal)) {
        throw 'Release tooling is pinned to asia-southeast1.'
    }
    if (-not [string]::Equals($Service, $script:PnlStagingService, [StringComparison]::Ordinal)) {
        throw 'Release tooling is pinned to the pnl-web service.'
    }
}

function Assert-PnlDigestImage {
    param(
        [Parameter(Mandatory)] [string] $Image,
        [Parameter(Mandatory)] [ValidateSet('edge', 'runtime')] [string] $Role
    )

    $pattern = '^asia-southeast1-docker\.pkg\.dev/pnl-dashboard-staging/[a-z0-9._-]+/[a-z0-9._-]+@sha256:[0-9a-f]{64}$'
    if ($Image -notmatch $pattern) {
        throw "$Role image must be an exact staging Artifact Registry reference pinned by lowercase sha256 digest."
    }
    $expectedName = if ($Role -eq 'edge') { '/pnl-web@sha256:' } else { '/pnl-runtime@sha256:' }
    if ($Image.IndexOf($expectedName, [StringComparison]::Ordinal) -lt 0) {
        throw "$Role image uses the wrong repository image name."
    }
}

function Assert-PnlCandidateTag {
    param([Parameter(Mandatory)] [AllowEmptyString()] [string] $Tag)

    if (
        [string]::IsNullOrWhiteSpace($Tag) -or
        $Tag.Length -gt 63 -or
        $Tag -notmatch '^[a-z][a-z0-9-]*[a-z0-9]$'
    ) {
        throw 'Candidate tag must be an explicit lowercase Cloud Run tag no longer than 63 characters.'
    }
    if ($Tag.ToLowerInvariant() -match '(^|-)(latest|newest|current|candidate)($|-)') {
        throw 'Generic latest/newest/current/candidate tags are forbidden.'
    }
    return $Tag
}

function Assert-PnlExplicitRevisionTarget {
    param(
        [Parameter(Mandatory)] [AllowEmptyString()] [string] $Revision,
        [string] $Service = $script:PnlStagingService
    )

    if ([string]::IsNullOrWhiteSpace($Revision) -or $Revision.Length -gt 63) {
        throw 'An explicit Cloud Run revision target is required.'
    }
    if ($Revision.ToLowerInvariant() -match '(^|-)(latest|newest|current|candidate)($|-)') {
        throw 'Generic latest/newest/current/candidate revision targets are forbidden.'
    }
    $revisionPattern = '^' + [regex]::Escape($Service) + '-[a-z0-9][a-z0-9-]*[a-z0-9]$'
    if ($Revision -notmatch $revisionPattern) {
        throw 'Traffic targets must be explicit revisions of the exact staging service.'
    }
    return $Revision
}

function Get-PnlStagingReleaseIdentity {
    param(
        [Parameter(Mandatory)] [ValidateSet('BACKEND_FIRST', 'FINAL_FRONTEND')] [string] $Stage,
        [Parameter(Mandatory)] [string] $GitHead,
        [string] $Service = $script:PnlStagingService
    )

    if ($GitHead -notmatch '^[0-9a-f]{40}$') {
        throw 'GitHead must be a full lowercase 40-character Git commit.'
    }
    if ($Service -notmatch '^[a-z][a-z0-9-]{0,47}[a-z0-9]$') {
        throw 'Service is not a valid Cloud Run service name for this identity policy.'
    }
    $token = if ($Stage -eq 'BACKEND_FIRST') { 'pnlbe' } else { 'pnlfe' }
    $headToken = $GitHead
    $tagHeadToken = $GitHead.Substring(0, 16)
    $suffix = "$token-$headToken"
    $revision = "$Service-$suffix"
    if ($revision.Length -gt 63) {
        throw 'The deterministic Cloud Run revision name exceeds 63 characters.'
    }
    $candidateTag = Assert-PnlCandidateTag -Tag "$token-$tagHeadToken"
    return [pscustomobject][ordered]@{
        stage = $Stage
        head_token = $headToken
        revision_suffix = $suffix
        revision_name = $revision
        candidate_tag = $candidateTag
    }
}

function Get-PnlRequiredJsonProperty {
    param(
        [Parameter(Mandatory)] [AllowNull()] $Object,
        [Parameter(Mandatory)] [string] $Name,
        [Parameter(Mandatory)] [string] $FieldName
    )

    if ($null -eq $Object) {
        throw "$FieldName is missing."
    }
    $property = $Object.PSObject.Properties[$Name]
    if ($null -eq $property -or $null -eq $property.Value) {
        throw "$FieldName is missing."
    }
    return $property.Value
}

function Get-PnlActiveRevision {
    param(
        [Parameter(Mandatory)] [object] $ServiceDescription,
        [string] $Service = $script:PnlStagingService
    )

    $metadata = Get-PnlRequiredJsonProperty -Object $ServiceDescription -Name 'metadata' -FieldName 'metadata'
    if ([string](Get-PnlRequiredJsonProperty -Object $metadata -Name 'name' -FieldName 'metadata.name') -cne $Service) {
        throw 'Captured service identity does not match the exact staging service.'
    }
    if ([string](Get-PnlRequiredJsonProperty -Object $metadata -Name 'namespace' -FieldName 'metadata.namespace') -cne $script:PnlStagingProjectNumber) {
        throw 'Captured service project does not match the exact staging project number.'
    }
    $status = Get-PnlRequiredJsonProperty -Object $ServiceDescription -Name 'status' -FieldName 'status'
    $trafficValue = Get-PnlRequiredJsonProperty -Object $status -Name 'traffic' -FieldName 'status.traffic'
    $traffic = @($trafficValue)
    if ($traffic.Count -eq 0) {
        throw 'Captured service has no traffic entries.'
    }

    $positiveTraffic = @()
    foreach ($entry in $traffic) {
        if ($null -eq $entry) {
            throw 'Traffic entries must be non-null objects.'
        }
        $revisionProperty = $entry.PSObject.Properties['revisionName']
        if ($null -eq $revisionProperty -or [string]::IsNullOrWhiteSpace([string]$revisionProperty.Value)) {
            throw 'Every traffic entry must identify an explicit revision.'
        }
        $entryRevision = Assert-PnlExplicitRevisionTarget -Revision ([string]$revisionProperty.Value) -Service $Service

        $tagProperty = $entry.PSObject.Properties['tag']
        $hasTag = $null -ne $tagProperty -and -not [string]::IsNullOrWhiteSpace([string]$tagProperty.Value)
        if ($null -ne $tagProperty -and -not $hasTag) {
            throw 'Traffic tags must not be null or empty when present.'
        }
        if ($hasTag) {
            Assert-PnlCandidateTag -Tag ([string]$tagProperty.Value) | Out-Null
        }

        $percentProperty = $entry.PSObject.Properties['percent']
        if ($null -eq $percentProperty) {
            if (-not $hasTag) {
                throw 'An untagged traffic entry must contain an explicit integer percentage.'
            }
            continue
        }
        if ($null -eq $percentProperty.Value) {
            throw 'Traffic percentage must not be null.'
        }
        $percentValue = $percentProperty.Value
        if ($percentValue -isnot [int] -and $percentValue -isnot [long]) {
            throw 'Traffic percentage must be an integer JSON number.'
        }
        $percent = [long]$percentValue
        if ($percent -lt 0 -or $percent -gt 100) {
            throw 'Traffic percentage must be inside the inclusive 0..100 range.'
        }
        if ($percent -gt 0) {
            $positiveTraffic += [pscustomobject]@{
                revision = $entryRevision
                percent = $percent
            }
        }
    }
    if ($positiveTraffic.Count -ne 1 -or $positiveTraffic[0].percent -ne 100) {
        throw 'Expected exactly one explicit revision serving 100 percent production traffic.'
    }
    return [string]$positiveTraffic[0].revision
}

function Get-PnlResolvedActiveRevisionBaseline {
    param(
        [Parameter(Mandatory)] [object] $ServiceDescription,
        [Parameter(Mandatory)] [object] $RevisionDescription,
        [string] $Service = $script:PnlStagingService
    )

    $activeRevision = Get-PnlActiveRevision -ServiceDescription $ServiceDescription -Service $Service
    $metadata = Get-PnlRequiredJsonProperty -Object $RevisionDescription -Name 'metadata' -FieldName 'revision.metadata'
    if ([string](Get-PnlRequiredJsonProperty -Object $metadata -Name 'name' -FieldName 'revision.metadata.name') -cne $activeRevision) {
        throw 'Resolved revision identity does not match the exact 100-percent active revision.'
    }
    if ([string](Get-PnlRequiredJsonProperty -Object $metadata -Name 'namespace' -FieldName 'revision.metadata.namespace') -cne $script:PnlStagingProjectNumber) {
        throw 'Resolved revision project does not match the exact staging project number.'
    }

    $status = Get-PnlRequiredJsonProperty -Object $RevisionDescription -Name 'status' -FieldName 'revision.status'
    $conditions = @(Get-PnlRequiredJsonProperty -Object $status -Name 'conditions' -FieldName 'revision.status.conditions')
    $readyConditions = @()
    foreach ($condition in $conditions) {
        if ($null -eq $condition) {
            throw 'Resolved revision conditions must be non-null objects.'
        }
        $conditionType = [string](Get-PnlRequiredJsonProperty `
            -Object $condition `
            -Name 'type' `
            -FieldName 'revision.status.conditions[].type')
        if ($conditionType -ceq 'Ready') {
            $readyConditions += $condition
        }
    }
    if ($readyConditions.Count -ne 1) {
        throw 'Resolved active revision must expose exactly one Ready condition.'
    }
    if ([string](Get-PnlRequiredJsonProperty `
        -Object $readyConditions[0] `
        -Name 'status' `
        -FieldName 'revision.status.conditions[Ready].status') -cne 'True') {
        throw 'Resolved active revision must be Ready before candidate planning.'
    }

    $spec = Get-PnlRequiredJsonProperty -Object $RevisionDescription -Name 'spec' -FieldName 'revision.spec'
    $containers = @(Get-PnlRequiredJsonProperty -Object $spec -Name 'containers' -FieldName 'revision.spec.containers')
    if ($containers.Count -ne 2) {
        throw 'Resolved active revision must contain exactly two containers.'
    }
    $containersByName = @{}
    foreach ($container in $containers) {
        if ($null -eq $container) {
            throw 'Resolved active revision containers must be non-null objects.'
        }
        $containerName = [string](Get-PnlRequiredJsonProperty `
            -Object $container `
            -Name 'name' `
            -FieldName 'revision.spec.containers[].name')
        if ($containerName -cne 'edge' -and $containerName -cne 'bff') {
            throw 'Resolved active revision container names must exactly match edge and bff.'
        }
        if ($containersByName.ContainsKey($containerName)) {
            throw "Resolved active revision contains duplicate $containerName containers."
        }
        $containersByName[$containerName] = $container
    }
    if (-not $containersByName.ContainsKey('edge') -or -not $containersByName.ContainsKey('bff')) {
        throw 'Resolved active revision container topology must exactly match edge and bff.'
    }

    $resolvedEdgeImage = [string](Get-PnlRequiredJsonProperty `
        -Object $containersByName['edge'] `
        -Name 'image' `
        -FieldName 'revision.spec.containers[edge].image')
    $resolvedRuntimeImage = [string](Get-PnlRequiredJsonProperty `
        -Object $containersByName['bff'] `
        -Name 'image' `
        -FieldName 'revision.spec.containers[bff].image')
    Assert-PnlDigestImage -Image $resolvedEdgeImage -Role 'edge'
    Assert-PnlDigestImage -Image $resolvedRuntimeImage -Role 'runtime'

    return [pscustomobject][ordered]@{
        active_revision = $activeRevision
        traffic_percent = 100
        ready = $true
        edge_image = $resolvedEdgeImage
        runtime_image = $resolvedRuntimeImage
        source = 'resolved active revision'
    }
}

function Assert-PnlRevisionBLineage {
    param(
        [Parameter(Mandatory)] [string] $FinalEdgeImage,
        [Parameter(Mandatory)] [string] $RuntimeImage,
        [Parameter(Mandatory)] [string] $ValidatedRevisionAEdgeImage,
        [Parameter(Mandatory)] [string] $ValidatedRevisionARuntimeImage,
        [AllowEmptyString()] [string] $ObservedRevisionAEdgeImage,
        [AllowEmptyString()] [string] $ObservedRevisionARuntimeImage
    )

    Assert-PnlDigestImage -Image $FinalEdgeImage -Role 'edge'
    Assert-PnlDigestImage -Image $ValidatedRevisionAEdgeImage -Role 'edge'
    Assert-PnlDigestImage -Image $RuntimeImage -Role 'runtime'
    Assert-PnlDigestImage -Image $ValidatedRevisionARuntimeImage -Role 'runtime'
    if (-not [string]::Equals($RuntimeImage, $ValidatedRevisionARuntimeImage, [StringComparison]::Ordinal)) {
        throw 'FINAL_FRONTEND runtime image must exactly equal the runtime image validated in Revision A.'
    }
    if ([string]::Equals($FinalEdgeImage, $ValidatedRevisionAEdgeImage, [StringComparison]::Ordinal)) {
        throw 'FINAL_FRONTEND edge image must differ from the frozen edge image validated in Revision A.'
    }
    $hasObservedEdge = -not [string]::IsNullOrWhiteSpace($ObservedRevisionAEdgeImage)
    $hasObservedRuntime = -not [string]::IsNullOrWhiteSpace($ObservedRevisionARuntimeImage)
    if ($hasObservedEdge -xor $hasObservedRuntime) {
        throw 'Observed Revision A edge and runtime lineage must be supplied together.'
    }
    if ($hasObservedEdge) {
        Assert-PnlDigestImage -Image $ObservedRevisionAEdgeImage -Role 'edge'
        Assert-PnlDigestImage -Image $ObservedRevisionARuntimeImage -Role 'runtime'
        if (-not [string]::Equals($ObservedRevisionAEdgeImage, $ValidatedRevisionAEdgeImage, [StringComparison]::Ordinal)) {
            throw 'Live Revision A edge digest does not match the stored validated Revision A edge digest.'
        }
        if (-not [string]::Equals($ObservedRevisionARuntimeImage, $ValidatedRevisionARuntimeImage, [StringComparison]::Ordinal)) {
            throw 'Live Revision A runtime digest does not match the stored validated Revision A runtime digest.'
        }
    }
}

function ConvertTo-PnlGcloudExecutionArguments {
    param(
        [Parameter(Mandatory)] [string[]] $Arguments,
        [Parameter(Mandatory)] [bool] $WindowsCmdShim
    )

    if (-not $WindowsCmdShim) {
        return @($Arguments)
    }
    return @(
        foreach ($argument in $Arguments) {
            if ($argument -match '^--update-env-vars=\^.{1}\^') {
                $argument.Replace('^', '^^^^')
            }
            else {
                $argument
            }
        }
    )
}

function Resolve-PnlGcloudExecutable {
    param([Parameter(Mandatory)] [AllowEmptyString()] [string] $GcloudPath)

    if ([string]::IsNullOrWhiteSpace($GcloudPath)) {
        throw 'GcloudPath must identify an explicit executable or command name.'
    }
    if (Test-Path -LiteralPath $GcloudPath -PathType Leaf) {
        return (Resolve-Path -LiteralPath $GcloudPath).Path
    }
    $resolved = Get-Command -Name $GcloudPath -CommandType Application, ExternalScript -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($null -eq $resolved -and $GcloudPath -ceq 'gcloud' -and
        [Environment]::OSVersion.Platform -eq [PlatformID]::Win32NT -and
        -not [string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) {
        $sdkShim = Join-Path $env:LOCALAPPDATA 'Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd'
        if (Test-Path -LiteralPath $sdkShim -PathType Leaf) {
            return (Resolve-Path -LiteralPath $sdkShim).Path
        }
    }
    if ($null -eq $resolved) {
        throw "Unable to resolve gcloud executable '$GcloudPath'."
    }
    return [string]$resolved.Source
}

function Get-PnlGcloudHelpText {
    param(
        [Parameter(Mandatory)] [string] $GcloudPath,
        [Parameter(Mandatory)] [string[]] $Arguments
    )

    $resolved = Resolve-PnlGcloudExecutable -GcloudPath $GcloudPath
    $global:LASTEXITCODE = 0
    $helpText = (& $resolved @Arguments 2>&1 | Out-String)
    if (-not $? -or $global:LASTEXITCODE -ne 0) {
        throw "Unable to inspect installed gcloud help through $resolved."
    }
    return $helpText
}

function Assert-PnlGcloudCandidateCapabilities {
    param([Parameter(Mandatory)] [string] $GcloudPath)

    $helpText = Get-PnlGcloudHelpText -GcloudPath $GcloudPath -Arguments @('run', 'deploy', '--help')
    foreach ($flag in @('--revision-suffix', '--tag', '--no-traffic', '--container', '--image', '--port', '--depends-on')) {
        if (-not $helpText.Contains($flag, [StringComparison]::Ordinal)) {
            throw "Installed gcloud does not support required safe candidate flag: $flag"
        }
    }
    return Resolve-PnlGcloudExecutable -GcloudPath $GcloudPath
}

function Assert-PnlGcloudTrafficCapabilities {
    param([Parameter(Mandatory)] [string] $GcloudPath)

    $helpText = Get-PnlGcloudHelpText `
        -GcloudPath $GcloudPath `
        -Arguments @('run', 'services', 'update-traffic', '--help')
    if (-not $helpText.Contains('--to-revisions', [StringComparison]::Ordinal)) {
        throw 'Installed gcloud cannot route traffic to an explicit revision.'
    }
    return Resolve-PnlGcloudExecutable -GcloudPath $GcloudPath
}

function Assert-PnlRenderedWebManifest {
    param(
        [Parameter(Mandatory)] [string] $Manifest,
        [Parameter(Mandatory)] [string] $ProjectId,
        [Parameter(Mandatory)] [string] $Service,
        [Parameter(Mandatory)] [string] $EdgeImage,
        [Parameter(Mandatory)] [string] $RuntimeImage,
        [Parameter(Mandatory)] [string] $ApprovedOrigins
    )

    $normalized = $Manifest.Replace("`r`n", "`n")
    if ($normalized -match '__[A-Z0-9_]+__') {
        throw 'Rendered web manifest contains an unresolved token.'
    }
    if ($normalized -notmatch "(?m)^  name: $([regex]::Escape($Service))$") {
        throw 'Rendered web manifest targets the wrong service.'
    }
    if ($normalized -notmatch "(?m)^      serviceAccountName: pnl-web@$([regex]::Escape($ProjectId))\.iam\.gserviceaccount\.com$") {
        throw 'Rendered web manifest targets the wrong runtime service account.'
    }
    $imageLines = @([regex]::Matches($normalized, '(?m)^          image: (?<image>\S+)$'))
    if ($imageLines.Count -ne 2) {
        throw 'Rendered web manifest must contain exactly two container images.'
    }
    if ($normalized -notmatch "(?m)^        - name: edge\n          image: $([regex]::Escape($EdgeImage))$") {
        throw 'Rendered web manifest edge image does not match the candidate input.'
    }
    if ($normalized -notmatch "(?m)^        - name: bff\n          image: $([regex]::Escape($RuntimeImage))$") {
        throw 'Rendered web manifest runtime image does not match the candidate input.'
    }
    if ($normalized -notmatch "(?m)^            - name: BFF_ALLOWED_ORIGINS\n              value: $([regex]::Escape($ApprovedOrigins))$") {
        throw 'Rendered web manifest does not contain the exact approved origin pair.'
    }

    $required = @(
        'run.googleapis.com/container-dependencies: ''{"edge":["bff"]}''',
        'run.googleapis.com/execution-environment: gen2',
        'run.googleapis.com/secrets:',
        'containerConcurrency: 4',
        'timeoutSeconds: 180',
        "name: BFF_COOKIE_SECURE`n              value: `"true`"",
        "name: BFF_COOKIE_SAME_SITE`n              value: strict",
        'secretName: pnl-supabase-secret-key',
        'secretName: pnl-viewer-code',
        'secretName: pnl-admin-code',
        'secretName: pnl-actor-namespace-secret',
        'secretName: pnl-csrf-secret',
        'memory: 512Mi',
        'memory: 2Gi',
        'sizeLimit: 512Mi',
        'sizeLimit: 256Mi'
    )
    foreach ($value in $required) {
        if (-not $normalized.Contains($value, [StringComparison]::Ordinal)) {
            throw "Rendered web manifest dropped required configuration: $value"
        }
    }
    foreach ($forbidden in @(
        "name: SUPABASE_SECRET_KEY`n",
        "name: VIEWER_CODE`n",
        "name: ADMIN_CODE`n",
        'sb_secret_',
        'service-account.json',
        'GOOGLE_APPLICATION_CREDENTIALS'
    )) {
        if ($normalized.Contains($forbidden, [StringComparison]::OrdinalIgnoreCase)) {
            throw 'Rendered web manifest contains a secret payload or unsupported credential material.'
        }
    }
}
