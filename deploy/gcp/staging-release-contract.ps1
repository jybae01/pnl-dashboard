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
    if (-not [string]::Equals($Origins, $expected, [StringComparison]::Ordinal)) {
        throw 'ApprovedOrigins must be the exact ordered two-origin staging set with no whitespace or duplicates.'
    }
    $items = $Origins.Split([char]',', [StringSplitOptions]::None)
    if ($items.Count -ne 2) {
        throw 'ApprovedOrigins must contain exactly two origins.'
    }
    foreach ($origin in $items) {
        Assert-PnlApprovedStagingOrigin -Origin $origin
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
    $shortHead = $GitHead.Substring(0, 12)
    $suffix = "$token-$shortHead"
    $revision = "$Service-$suffix"
    if ($revision.Length -gt 63) {
        throw 'The deterministic Cloud Run revision name exceeds 63 characters.'
    }
    return [pscustomobject][ordered]@{
        stage = $Stage
        short_head = $shortHead
        revision_suffix = $suffix
        revision_name = $revision
        candidate_tag = $suffix
    }
}

function Get-PnlActiveRevision {
    param(
        [Parameter(Mandatory)] [object] $ServiceDescription,
        [string] $Service = $script:PnlStagingService
    )

    $traffic = @($ServiceDescription.status.traffic)
    $active = @(
        $traffic |
            Where-Object { [int]$_.percent -eq 100 -and -not [string]::IsNullOrWhiteSpace([string]$_.revisionName) } |
            ForEach-Object { [string]$_.revisionName } |
            Sort-Object -Unique
    )
    if ($active.Count -ne 1) {
        throw 'Expected exactly one dynamically resolved revision serving 100 percent traffic.'
    }
    if ($active[0] -notmatch "^$([regex]::Escape($Service))-[a-z0-9-]+$") {
        throw 'The active revision does not belong to the exact staging service.'
    }
    return $active[0]
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
