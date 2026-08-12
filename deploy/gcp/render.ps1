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

$tokens = [ordered]@{
    '__PROJECT_ID__' = $ProjectId
    '__PROJECT_NUMBER__' = $ProjectNumber
    '__REGION__' = $Region
    '__SUPABASE_URL__' = $SupabaseUrl.TrimEnd('/')
    '__CLOUD_RUN_ORIGIN__' = $CloudRunOrigin
    '__WORKER_CONTROLLER_URL__' = $WorkerControllerUrl
    '__WEB_IMAGE__' = $WebImage
    '__RUNTIME_IMAGE__' = $RuntimeImage
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
