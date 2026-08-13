[CmdletBinding()]
param(
    [Parameter(Mandatory)] [string] $ProjectId,
    [Parameter(Mandatory)] [string] $ProjectNumber,
    [Parameter(Mandatory)] [string] $Region,
    [Parameter(Mandatory)] [string] $SupabaseUrl,
    [Parameter(Mandatory)] [string] $CloudRunOrigin,
    [Parameter(Mandatory)] [string] $WorkerControllerUrl,
    [Parameter(Mandatory)] [string] $WebImage,
    [Parameter(Mandatory)] [string] $RuntimeImage,
    [Parameter(Mandatory)] [string] $SourceCommit,
    [Parameter(Mandatory)] [string] $ReleaseStage,
    [Parameter(Mandatory)] [ValidateSet('passed')] [string] $BusinessGate,
    [ValidateSet('staging', 'production')] [string] $DeploymentProfile = 'staging',
    [string] $OutputDirectory = (Join-Path $PSScriptRoot 'rendered')
)

$ErrorActionPreference = 'Stop'

if ($ProjectId -notmatch '^[a-z][a-z0-9-]{4,28}[a-z0-9]$') {
    throw 'ProjectId is not a valid Google Cloud project ID.'
}
if ($ProjectNumber -notmatch '^[0-9]{6,20}$') {
    throw 'ProjectNumber must contain only the numeric Google Cloud project number.'
}
if ($Region -notmatch '^[a-z]+-[a-z]+[0-9]+$') {
    throw 'Region is not a valid Google Cloud region name.'
}
if ($SupabaseUrl -notmatch '^https://[a-z0-9]+\.supabase\.co/?$') {
    throw 'SupabaseUrl must be an https://<project-ref>.supabase.co URL.'
}
if ($CloudRunOrigin -notmatch '^https://[^/]+$') {
    throw 'CloudRunOrigin must be an HTTPS origin without a path.'
}
if ($WorkerControllerUrl -notmatch '^https://[^/]+$') {
    throw 'WorkerControllerUrl must be an HTTPS origin without a path.'
}
$digestImage = '^[a-z0-9.-]+(?:/[a-z0-9._-]+)+@sha256:[0-9a-f]{64}$'
foreach ($image in @($WebImage, $RuntimeImage)) {
    if ($image -notmatch $digestImage) {
        throw 'Container images must be Artifact Registry references pinned by sha256 digest.'
    }
}
if ($SourceCommit -notmatch '^[0-9a-f]{40}$') {
    throw 'SourceCommit must be a full lowercase 40-character Git commit.'
}
if ($ReleaseStage -notmatch '^[a-z][a-z0-9-]{0,62}$') {
    throw 'ReleaseStage must be a lowercase Google label value.'
}

if ($DeploymentProfile -eq 'production') {
    $acceptedRuntimeCommit = '1e478b68b4f73dc6b41e2681cb6238a87d1e0427'
    $acceptedWebDigest = 'sha256:36502f01eed08012e2c0efb5f4756212c72b1373a390b5ed9bb78e59741d8330'
    $acceptedRuntimeDigest = 'sha256:4121d8f3fe25b555ea30355110008c4b6e5ac9cb2ecbc065f164bde2cd5ce485'
    $knownNonProductionProjectIds = @('pnl-dashboard-staging')
    $knownNonProductionProjectNumbers = @('498160536475')
    $knownNonProductionSupabaseRefs = @(
        'ysatkswhhajicfgbrtpv',
        'sarwbkxukyexgioirpaa',
        'vfplhknqovdvsmjbvvax'
    )
    if ($ProjectId -in $knownNonProductionProjectIds) {
        throw 'Production rendering refuses the staging Google Cloud project.'
    }
    if ($ProjectNumber -in $knownNonProductionProjectNumbers) {
        throw 'Production rendering refuses the staging Google Cloud project number.'
    }
    if ($SupabaseUrl -match '^https://(?<ref>[a-z0-9]+)\.supabase\.co/?$' -and
        $Matches.ref -in $knownNonProductionSupabaseRefs) {
        throw 'Production rendering refuses a staging or legacy Supabase project.'
    }
    $productionImagePrefix = "^$([regex]::Escape($Region))-docker\.pkg\.dev/$([regex]::Escape($ProjectId))/pnl-production/"
    foreach ($image in @($WebImage, $RuntimeImage)) {
        if ($image -notmatch $productionImagePrefix) {
            throw 'Production images must come from the exact production project and pnl-production repository.'
        }
    }
    if (-not $WebImage.EndsWith("@$acceptedWebDigest", [StringComparison]::Ordinal)) {
        throw 'Production Web image must use the Golden-accepted OCI index digest.'
    }
    if (-not $RuntimeImage.EndsWith("@$acceptedRuntimeDigest", [StringComparison]::Ordinal)) {
        throw 'Production runtime image must use the Golden-accepted OCI index digest.'
    }
    if ($SourceCommit -ne $acceptedRuntimeCommit) {
        throw 'V1 production must use the Golden-accepted runtime commit.'
    }
    if ($ReleaseStage -ne 'v1-production-pilot') {
        throw 'Production ReleaseStage must be v1-production-pilot.'
    }
}

$tokens = [ordered]@{
    '__PROJECT_ID__' = $ProjectId
    '__PROJECT_NUMBER__' = $ProjectNumber
    '__REGION__' = $Region
    '__SUPABASE_URL__' = $SupabaseUrl.TrimEnd('/')
    '__CLOUD_RUN_ORIGIN__' = $CloudRunOrigin
    '__WORKER_CONTROLLER_URL__' = $WorkerControllerUrl
    '__WEB_IMAGE__' = $WebImage
    '__RUNTIME_IMAGE__' = $RuntimeImage
    '__SOURCE_COMMIT__' = $SourceCommit
    '__RELEASE_STAGE__' = $ReleaseStage
    '__BUSINESS_GATE__' = $BusinessGate
}

New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
foreach ($name in @('cloud-run-web.yaml', 'worker-pool.yaml', 'worker-controller.yaml', 'maintenance-job.yaml')) {
    $template = Join-Path $PSScriptRoot ($name + '.tmpl')
    $content = Get-Content -Raw -LiteralPath $template
    foreach ($entry in $tokens.GetEnumerator()) {
        $content = $content.Replace($entry.Key, $entry.Value)
    }
    if ($content -match '__[A-Z0-9_]+__') {
        throw "Unresolved template token in $name."
    }
    $outputPath = Join-Path $OutputDirectory $name
    [System.IO.File]::WriteAllText($outputPath, $content, [System.Text.UTF8Encoding]::new($false))
}

Write-Output "Rendered secret-free deployment manifests to $OutputDirectory"
