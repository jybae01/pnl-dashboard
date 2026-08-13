[CmdletBinding()]
param(
    [Parameter(Mandatory)] [string] $ProjectId,
    [Parameter(Mandatory)] [string] $ProjectNumber,
    [Parameter(Mandatory)] [string] $Configuration,
    [Parameter(Mandatory)] [string] $SupabaseRef,
    [Parameter(Mandatory)] [string] $SupabaseRegion,
    [Parameter(Mandatory)] [string] $SupabasePlan,
    [string] $Region = 'asia-southeast1',
    [string] $GcloudPath = "$env:LOCALAPPDATA\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd",
    [string] $OutputPath = (Join-Path $PSScriptRoot 'rendered\production-snapshot.json')
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

& (Join-Path $PSScriptRoot 'assert-production-target.ps1') `
    -ProjectId $ProjectId -ProjectNumber $ProjectNumber `
    -Configuration $Configuration -GcloudPath $GcloudPath | Out-Null

if ($SupabaseRef -notmatch '^[a-z]{20}$' -or $SupabaseRef -in @(
    'ysatkswhhajicfgbrtpv', 'sarwbkxukyexgioirpaa', 'vfplhknqovdvsmjbvvax'
)) {
    throw 'SupabaseRef must be the new isolated Production project.'
}

function Invoke-GcloudJson {
    param([Parameter(Mandatory)] [string[]] $Arguments)
    $json = & $GcloudPath @Arguments `
        "--configuration=$Configuration" `
        "--project=$ProjectId" `
        '--format=json'
    if ($LASTEXITCODE -ne 0) { throw "gcloud snapshot command failed: $($Arguments -join ' ')" }
    if (-not $json) { return $null }
    return ($json | ConvertFrom-Json)
}

$secretNames = @(
    'pnl-supabase-secret-key', 'pnl-viewer-code', 'pnl-admin-code',
    'pnl-actor-namespace-secret', 'pnl-csrf-secret'
)
$secretShape = @()
foreach ($name in $secretNames) {
    $metadata = Invoke-GcloudJson @('secrets', 'describe', $name)
    $versions = @(Invoke-GcloudJson @(
        'secrets', 'versions', 'list', $name,
        '--filter=state=ENABLED'
    ))
    $secretShape += [ordered]@{
        name = $name
        replication = $metadata.replication
        enabled_version_count = @($versions).Count
        enabled_versions = @($versions | ForEach-Object {
            [ordered]@{ name = $_.name; state = $_.state; createTime = $_.createTime }
        })
    }
}

$snapshot = [ordered]@{
    schema = 'pnl-production-snapshot-v1'
    captured_at_utc = [DateTime]::UtcNow.ToString('o')
    source_commit = '1e478b68b4f73dc6b41e2681cb6238a87d1e0427'
    release_head = '6124b9c584d102045490f59f0dca7b16e1aafb0d'
    google = [ordered]@{
        project = Invoke-GcloudJson @('projects', 'describe', $ProjectId)
        billing = Invoke-GcloudJson @('billing', 'projects', 'describe', $ProjectId)
        artifact_images = Invoke-GcloudJson @(
            'artifacts', 'docker', 'images', 'list',
            "$Region-docker.pkg.dev/$ProjectId/pnl-production",
            '--include-tags'
        )
        web = Invoke-GcloudJson @('run', 'services', 'describe', 'pnl-web', "--region=$Region")
        worker = Invoke-GcloudJson @('run', 'worker-pools', 'describe', 'pnl-worker', "--region=$Region")
        controller = Invoke-GcloudJson @('run', 'services', 'describe', 'pnl-worker-controller', "--region=$Region")
        maintenance = Invoke-GcloudJson @('run', 'jobs', 'describe', 'pnl-maintenance', "--region=$Region")
        scheduler = Invoke-GcloudJson @('scheduler', 'jobs', 'describe', 'pnl-worker-reconcile', "--location=$Region")
        service_accounts = Invoke-GcloudJson @('iam', 'service-accounts', 'list')
        secrets = $secretShape
    }
    supabase = [ordered]@{ ref = $SupabaseRef; region = $SupabaseRegion; plan = $SupabasePlan }
}

$resolvedOutput = [System.IO.Path]::GetFullPath($OutputPath)
$allowedRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot 'rendered'))
if (-not $resolvedOutput.StartsWith($allowedRoot + [System.IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Snapshot output must stay in the ignored deploy/gcp/rendered directory.'
}
New-Item -ItemType Directory -Force -Path (Split-Path $resolvedOutput -Parent) | Out-Null
[System.IO.File]::WriteAllText(
    $resolvedOutput,
    ($snapshot | ConvertTo-Json -Depth 100),
    [System.Text.UTF8Encoding]::new($false)
)
Write-Output "PRODUCTION_SNAPSHOT=PASS path=$resolvedOutput"
