[CmdletBinding()]
param(
    [Parameter(Mandatory)] [string] $ProjectId,
    [Parameter(Mandatory)] [string] $ProjectNumber,
    [Parameter(Mandatory)] [string] $Configuration,
    [string] $GcloudPath = "$env:LOCALAPPDATA\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd"
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

if ($ProjectId -notmatch '^[a-z][a-z0-9-]{4,28}[a-z0-9]$') {
    throw 'ProjectId is not a valid Google Cloud project ID.'
}
if ($ProjectNumber -notmatch '^[0-9]{6,20}$') {
    throw 'ProjectNumber must be numeric.'
}
if ($Configuration -notmatch '^pnl-production-[a-z0-9-]+$') {
    throw 'Use a dedicated pnl-production-* gcloud configuration.'
}
if ($ProjectId -eq 'pnl-dashboard-staging' -or $ProjectNumber -eq '498160536475') {
    throw 'Refusing the staging Google Cloud project.'
}
if (-not (Test-Path -LiteralPath $GcloudPath -PathType Leaf)) {
    throw 'gcloud was not found at the expected path.'
}

$configuredProject = (& $GcloudPath config get-value project --configuration=$Configuration 2>$null).Trim()
if ($configuredProject -ne $ProjectId) {
    throw 'The dedicated gcloud configuration does not target the exact Production project.'
}

$described = & $GcloudPath projects describe $ProjectId `
    --configuration=$Configuration `
    --project=$ProjectId `
    --format=json
if ($LASTEXITCODE -ne 0) {
    throw 'The exact Production project could not be described.'
}
$project = $described | ConvertFrom-Json
if ([string]$project.projectId -ne $ProjectId -or [string]$project.projectNumber -ne $ProjectNumber) {
    throw 'The Production project identity does not match both pinned values.'
}
if ([string]$project.lifecycleState -ne 'ACTIVE') {
    throw 'The Production Google Cloud project is not ACTIVE.'
}

$billing = & $GcloudPath billing projects describe $ProjectId `
    --configuration=$Configuration `
    --project=$ProjectId `
    --format=json
if ($LASTEXITCODE -ne 0) {
    throw 'Production billing state could not be described.'
}
$billingState = $billing | ConvertFrom-Json
if (-not [bool]$billingState.billingEnabled) {
    throw 'Production billing is not enabled.'
}

Write-Output "PRODUCTION_GCP_TARGET=VERIFIED project=$ProjectId number=$ProjectNumber configuration=$Configuration"
