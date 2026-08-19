[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

. (Join-Path $PSScriptRoot 'staging-release-contract.ps1')

function Assert-True {
    param([Parameter(Mandatory)] [bool] $Condition, [Parameter(Mandatory)] [string] $Message)
    if (-not $Condition) { throw $Message }
}

function Assert-Equal {
    param(
        [AllowNull()] [object] $Actual,
        [AllowNull()] [object] $Expected,
        [Parameter(Mandatory)] [string] $Message
    )
    if (-not [object]::Equals($Actual, $Expected)) {
        throw "$Message Expected=[$Expected] Actual=[$Actual]"
    }
}

function Assert-Throws {
    param([Parameter(Mandatory)] [scriptblock] $Action, [Parameter(Mandatory)] [string] $Message)
    try {
        & $Action | Out-Null
    }
    catch {
        return
    }
    throw $Message
}

$canonical = 'https://pnl-web-498160536475.asia-southeast1.run.app'
$statusUrl = 'https://pnl-web-t4n4rdoznq-as.a.run.app'
$originPair = "$canonical,$statusUrl"
$head = '37d3db2354d8eedb7fa410c06fca7b48c495bc1f'
$project = 'pnl-dashboard-staging'
$projectNumber = '498160536475'
$region = 'asia-southeast1'
$service = 'pnl-web'
$supabaseUrl = 'https://ysatkswhhajicfgbrtpv.supabase.co'
$controllerUrl = 'https://pnl-worker-controller-498160536475.asia-southeast1.run.app'
$frozenEdge = 'asia-southeast1-docker.pkg.dev/pnl-dashboard-staging/pnl-staging/pnl-web@sha256:' + ('1' * 64)
$finalEdge = 'asia-southeast1-docker.pkg.dev/pnl-dashboard-staging/pnl-staging/pnl-web@sha256:' + ('2' * 64)
$runtimeA = 'asia-southeast1-docker.pkg.dev/pnl-dashboard-staging/pnl-staging/pnl-runtime@sha256:' + ('3' * 64)
$runtimeB = 'asia-southeast1-docker.pkg.dev/pnl-dashboard-staging/pnl-staging/pnl-runtime@sha256:' + ('4' * 64)
$backendIdentity = Get-PnlStagingReleaseIdentity -Stage BACKEND_FIRST -GitHead $head -Service $service
$frontendIdentity = Get-PnlStagingReleaseIdentity -Stage FINAL_FRONTEND -GitHead $head -Service $service

Assert-PnlApprovedStagingOrigin -Origin $canonical
Assert-PnlApprovedStagingOrigin -Origin $statusUrl
Assert-Equal `
    -Actual (ConvertTo-PnlApprovedStagingOriginValue -Origins $originPair) `
    -Expected $originPair `
    -Message 'The exact approved pair must pass.'

foreach ($invalid in @(
    '*',
    $canonical,
    $statusUrl,
    'https://localhost',
    'http://pnl-web-498160536475.asia-southeast1.run.app',
    'https://third-party.example',
    "$originPair,https://third.example",
    "$canonical,$canonical",
    "$canonical, $statusUrl",
    "$statusUrl,$canonical"
)) {
    Assert-Throws `
        -Action { ConvertTo-PnlApprovedStagingOriginValue -Origins $invalid } `
        -Message "Malformed or unapproved origin value passed: $invalid"
}

Assert-Equal -Actual $backendIdentity.revision_suffix -Expected 'pnlbe-37d3db2354d8' -Message 'Backend suffix is not deterministic.'
Assert-Equal -Actual $frontendIdentity.revision_suffix -Expected 'pnlfe-37d3db2354d8' -Message 'Frontend suffix is not deterministic.'
Assert-True -Condition ($backendIdentity.revision_name -ne $frontendIdentity.revision_name) -Message 'Revision A/B names collided.'
Assert-True -Condition ($backendIdentity.candidate_tag -ne $frontendIdentity.candidate_tag) -Message 'Revision A/B tags collided.'

$activeFixture = [pscustomobject]@{
    status = [pscustomobject]@{
        traffic = @(
            [pscustomobject]@{ revisionName = 'pnl-web-dynamic-fixture-a1b2c3'; percent = 100 },
            [pscustomobject]@{ revisionName = 'pnl-web-pnlbe-37d3db2354d8'; percent = 0; tag = 'candidate' }
        )
    }
}
Assert-Equal `
    -Actual (Get-PnlActiveRevision -ServiceDescription $activeFixture -Service $service) `
    -Expected 'pnl-web-dynamic-fixture-a1b2c3' `
    -Message 'Dynamic active revision capture failed.'
Assert-Throws -Action {
    Get-PnlActiveRevision -ServiceDescription ([pscustomobject]@{
        status = [pscustomobject]@{
            traffic = @(
                [pscustomobject]@{ revisionName = 'pnl-web-one'; percent = 100 },
                [pscustomobject]@{ revisionName = 'pnl-web-two'; percent = 100 }
            )
        }
    }) -Service $service
} -Message 'Ambiguous 100-percent traffic state must fail.'

$renderedRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot 'rendered'))
$testRoot = Join-Path $renderedRoot ("staging-release-test-" + [Guid]::NewGuid().ToString('N'))
if (-not $testRoot.StartsWith(
    $renderedRoot + [IO.Path]::DirectorySeparatorChar,
    [StringComparison]::OrdinalIgnoreCase
)) {
    throw 'Resolved test path escaped deploy/gcp/rendered.'
}

try {
    New-Item -ItemType Directory -Force -Path $testRoot | Out-Null

    foreach ($invalidRendererOrigin in @('*', 'https://third-party.example')) {
        Assert-Throws -Action {
            & (Join-Path $PSScriptRoot 'render.ps1') `
                -ProjectId $project `
                -ProjectNumber $projectNumber `
                -Region $region `
                -SupabaseUrl $supabaseUrl `
                -ApprovedOrigins $invalidRendererOrigin `
                -WorkerControllerUrl $controllerUrl `
                -WebImage $frozenEdge `
                -RuntimeImage $runtimeA `
                -SourceCommit $head `
                -ReleaseStage 'pnl-backend-first' `
                -BusinessGate 'passed' `
                -DeploymentProfile 'staging' `
                -OutputDirectory (Join-Path $testRoot 'invalid-render')
        } -Message "Staging renderer accepted forbidden origins: $invalidRendererOrigin"
    }

    $renderOutput = Join-Path $testRoot 'renderer'
    & (Join-Path $PSScriptRoot 'render.ps1') `
        -ProjectId $project `
        -ProjectNumber $projectNumber `
        -Region $region `
        -SupabaseUrl $supabaseUrl `
        -ApprovedOrigins $originPair `
        -WorkerControllerUrl $controllerUrl `
        -WebImage $frozenEdge `
        -RuntimeImage $runtimeA `
        -SourceCommit $head `
        -ReleaseStage 'pnl-backend-first' `
        -BusinessGate 'passed' `
        -DeploymentProfile 'staging' `
        -OutputDirectory $renderOutput | Out-Null
    $renderedWeb = Get-Content -Raw -LiteralPath (Join-Path $renderOutput 'cloud-run-web.yaml')
    Assert-PnlRenderedWebManifest `
        -Manifest $renderedWeb `
        -ProjectId $project `
        -Service $service `
        -EdgeImage $frozenEdge `
        -RuntimeImage $runtimeA `
        -ApprovedOrigins $originPair
    Assert-True -Condition ($renderedWeb.Contains("value: $originPair", [StringComparison]::Ordinal)) -Message 'Renderer did not emit the exact dual-origin value.'
    foreach ($forbidden in @('*', 'localhost', 'third-party.example', 'sb_secret_', 'GOOGLE_APPLICATION_CREDENTIALS')) {
        Assert-True -Condition (-not $renderedWeb.Contains($forbidden, [StringComparison]::OrdinalIgnoreCase)) -Message "Rendered manifest contains forbidden value: $forbidden"
    }

    $backendOutput = Join-Path $testRoot 'backend'
    & (Join-Path $PSScriptRoot 'staging-release.ps1') `
        -Operation CANDIDATE `
        -ProjectId $project `
        -ProjectNumber $projectNumber `
        -Region $region `
        -Service $service `
        -Stage BACKEND_FIRST `
        -GitHead $head `
        -ApprovedOrigins $originPair `
        -SupabaseUrl $supabaseUrl `
        -WorkerControllerUrl $controllerUrl `
        -FrozenEdgeImage $frozenEdge `
        -RuntimeImage $runtimeA `
        -RevisionSuffix $backendIdentity.revision_suffix `
        -CandidateTag $backendIdentity.candidate_tag `
        -GcloudPath (Join-Path $testRoot 'must-not-run-gcloud.cmd') `
        -OutputDirectory $backendOutput | Out-Null

    $backendPlan = Get-Content -Raw -LiteralPath (Join-Path $backendOutput 'candidate-backend-first.json') | ConvertFrom-Json
    $backendArguments = @($backendPlan.gcloud.arguments)
    Assert-Equal -Actual $backendPlan.dry_run -Expected $true -Message 'Candidate default must be dry-run.'
    Assert-Equal -Actual $backendPlan.cloud_mutation -Expected $false -Message 'Dry-run must report no Cloud mutation.'
    Assert-Equal -Actual $backendPlan.zero_traffic -Expected $true -Message 'Candidate plan must declare zero traffic.'
    Assert-True -Condition ($backendArguments -contains '--no-traffic') -Message 'Candidate command omitted --no-traffic.'
    Assert-True -Condition ($backendArguments -contains "--revision-suffix=$($backendIdentity.revision_suffix)") -Message 'Candidate command omitted deterministic revision suffix.'
    Assert-True -Condition ($backendArguments -contains "--tag=$($backendIdentity.candidate_tag)") -Message 'Candidate command omitted deterministic tag.'
    Assert-True -Condition ($backendArguments -contains '--container=edge') -Message 'Candidate command omitted edge container.'
    Assert-True -Condition ($backendArguments -contains '--container=bff') -Message 'Candidate command omitted BFF container.'
    Assert-True -Condition ($backendArguments -contains "--image=$frozenEdge") -Message 'Backend candidate omitted frozen edge digest.'
    Assert-True -Condition ($backendArguments -contains "--image=$runtimeA") -Message 'Backend candidate omitted runtime digest.'
    $originArgument = @($backendArguments | Where-Object { $_ -like '--update-env-vars=*BFF_ALLOWED_ORIGINS=*' })
    Assert-Equal -Actual $originArgument.Count -Expected 1 -Message 'Candidate command must contain one allowed-origin update.'
    Assert-True -Condition ($originArgument[0].EndsWith("BFF_ALLOWED_ORIGINS=$originPair", [StringComparison]::Ordinal)) -Message 'Candidate command altered the approved origin pair.'
    if ([Environment]::OSVersion.Platform -eq [PlatformID]::Win32NT) {
        Assert-True -Condition ($originArgument[0].StartsWith('--update-env-vars=^^^^@^^^^', [StringComparison]::Ordinal)) -Message 'Windows gcloud dictionary delimiter is not escaped as installed help requires.'
        $fakeGcloud = Join-Path $testRoot 'fake-gcloud.cmd'
        [IO.File]::WriteAllText(
            $fakeGcloud,
            "@echo off`r`nsetlocal DisableDelayedExpansion`r`necho %*`r`n",
            [Text.ASCIIEncoding]::new()
        )
        $propagated = (& $fakeGcloud $originArgument[0] 2>&1 | Out-String).Trim()
        Assert-Equal -Actual $LASTEXITCODE -Expected 0 -Message "Windows command parser split the escaped gcloud dictionary argument. Output=[$propagated]"
        Assert-True -Condition ($propagated.Contains('^@^BFF_ALLOWED_ORIGINS=', [StringComparison]::Ordinal)) -Message 'Windows command parser did not deliver gcloud alternate-delimiter syntax.'
        Assert-True -Condition ($propagated.EndsWith($originPair, [StringComparison]::Ordinal)) -Message 'Windows command parser altered the approved origin pair.'
    }
    Assert-True -Condition (-not (($backendArguments -join ' ').Contains('services replace', [StringComparison]::OrdinalIgnoreCase))) -Message 'Candidate command used unsafe services replace.'
    Assert-True -Condition (-not (Test-Path -LiteralPath (Join-Path $testRoot 'must-not-run-gcloud.cmd'))) -Message 'Dry-run created or invoked a gcloud stub.'

    $finalOutput = Join-Path $testRoot 'final'
    & (Join-Path $PSScriptRoot 'staging-release.ps1') `
        -Operation CANDIDATE `
        -ProjectId $project `
        -ProjectNumber $projectNumber `
        -Region $region `
        -Service $service `
        -Stage FINAL_FRONTEND `
        -GitHead $head `
        -ApprovedOrigins $originPair `
        -SupabaseUrl $supabaseUrl `
        -WorkerControllerUrl $controllerUrl `
        -FinalEdgeImage $finalEdge `
        -RuntimeImage $runtimeA `
        -ValidatedRevisionARuntimeImage $runtimeA `
        -RevisionSuffix $frontendIdentity.revision_suffix `
        -CandidateTag $frontendIdentity.candidate_tag `
        -GcloudPath (Join-Path $testRoot 'must-not-run-gcloud.cmd') `
        -OutputDirectory $finalOutput | Out-Null
    $finalPlan = Get-Content -Raw -LiteralPath (Join-Path $finalOutput 'candidate-final-frontend.json') | ConvertFrom-Json
    Assert-Equal -Actual $finalPlan.runtime_image -Expected $runtimeA -Message 'Final candidate runtime changed.'
    Assert-True -Condition (@($finalPlan.gcloud.arguments) -contains "--image=$finalEdge") -Message 'Final candidate omitted final edge digest.'

    Assert-Throws -Action {
        & (Join-Path $PSScriptRoot 'staging-release.ps1') `
            -Operation CANDIDATE `
            -ProjectId $project `
            -ProjectNumber $projectNumber `
            -Region $region `
            -Service $service `
            -Stage FINAL_FRONTEND `
            -GitHead $head `
            -ApprovedOrigins $originPair `
            -SupabaseUrl $supabaseUrl `
            -WorkerControllerUrl $controllerUrl `
            -FinalEdgeImage $finalEdge `
            -RuntimeImage $runtimeB `
            -ValidatedRevisionARuntimeImage $runtimeA `
            -RevisionSuffix $frontendIdentity.revision_suffix `
            -CandidateTag $frontendIdentity.candidate_tag `
            -OutputDirectory (Join-Path $testRoot 'wrong-runtime')
    } -Message 'Revision B accepted a runtime digest different from Revision A.'

    $captureOutput = Join-Path $testRoot 'capture'
    Assert-Throws -Action {
        & (Join-Path $PSScriptRoot 'staging-release.ps1') `
            -Operation CAPTURE_ACTIVE `
            -ProjectId $project `
            -ProjectNumber $projectNumber `
            -Region $region `
            -Service $service `
            -OutputDirectory (Join-Path $testRoot 'capture-without-head')
    } -Message 'Active-revision capture accepted a missing GitHead.'
    & (Join-Path $PSScriptRoot 'staging-release.ps1') `
        -Operation CAPTURE_ACTIVE `
        -ProjectId $project `
        -ProjectNumber $projectNumber `
        -Region $region `
        -Service $service `
        -GitHead $head `
        -GcloudPath (Join-Path $testRoot 'must-not-run-gcloud.cmd') `
        -OutputDirectory $captureOutput | Out-Null
    $capturePlan = Get-Content -Raw -LiteralPath (Join-Path $captureOutput 'capture-active.json') | ConvertFrom-Json
    Assert-Equal -Actual $capturePlan.cloud_mutation -Expected $false -Message 'Capture plan must be read-only.'
    Assert-True -Condition (($capturePlan.gcloud.arguments -join ' ') -match 'run services describe pnl-web') -Message 'Capture plan did not dynamically describe the service.'

    $promotionOutput = Join-Path $testRoot 'promotion'
    & (Join-Path $PSScriptRoot 'staging-release.ps1') `
        -Operation PROMOTE `
        -ProjectId $project `
        -ProjectNumber $projectNumber `
        -Region $region `
        -Service $service `
        -Stage BACKEND_FIRST `
        -GitHead $head `
        -Revision $backendIdentity.revision_name `
        -GcloudPath (Join-Path $testRoot 'must-not-run-gcloud.cmd') `
        -OutputDirectory $promotionOutput | Out-Null
    $promotionPlan = Get-Content -Raw -LiteralPath (Join-Path $promotionOutput 'promote-backend-first.json') | ConvertFrom-Json
    Assert-Equal -Actual $promotionPlan.capture_current_100_percent_revision_before_promotion -Expected $true -Message 'Promotion did not require dynamic active-revision capture.'
    Assert-True -Condition (@($promotionPlan.gcloud.arguments) -contains "--to-revisions=$($backendIdentity.revision_name)=100") -Message 'Promotion did not target the explicit Revision A name.'
    Assert-True -Condition (-not (@($promotionPlan.gcloud.arguments) -contains '--to-latest')) -Message 'Promotion used latest revision selection.'

    $rollbackOutput = Join-Path $testRoot 'rollback'
    & (Join-Path $PSScriptRoot 'staging-release.ps1') `
        -Operation ROLLBACK `
        -ProjectId $project `
        -ProjectNumber $projectNumber `
        -Region $region `
        -Service $service `
        -RollbackKind REVISION_B_TO_A `
        -GitHead $head `
        -GcloudPath (Join-Path $testRoot 'must-not-run-gcloud.cmd') `
        -OutputDirectory $rollbackOutput | Out-Null
    $rollbackPlan = Get-Content -Raw -LiteralPath (Join-Path $rollbackOutput 'rollback-revision-b-to-a.json') | ConvertFrom-Json
    Assert-True -Condition (@($rollbackPlan.gcloud.arguments) -contains "--to-revisions=$($backendIdentity.revision_name)=100") -Message 'Revision B rollback did not target Revision A.'

    $preReleaseState = Join-Path $rollbackOutput 'captured-pre-release.json'
    [IO.File]::WriteAllText(
        $preReleaseState,
        ([ordered]@{
            schema = 'pnl-staging-active-revision-v1'
            project = $project
            project_number = $projectNumber
            region = $region
            service = $service
            source_commit = $head
            active_revision = 'pnl-web-dynamic-fixture-a1b2c3'
        } | ConvertTo-Json),
        [Text.UTF8Encoding]::new($false)
    )
    & (Join-Path $PSScriptRoot 'staging-release.ps1') `
        -Operation ROLLBACK `
        -ProjectId $project `
        -ProjectNumber $projectNumber `
        -Region $region `
        -Service $service `
        -RollbackKind REVISION_A_TO_PRE_RELEASE `
        -GitHead $head `
        -PreReleaseStatePath $preReleaseState `
        -GcloudPath (Join-Path $testRoot 'must-not-run-gcloud.cmd') `
        -OutputDirectory $rollbackOutput | Out-Null
    $preReleasePlan = Get-Content -Raw -LiteralPath (Join-Path $rollbackOutput 'rollback-revision-a-to-pre-release.json') | ConvertFrom-Json
    Assert-True -Condition (@($preReleasePlan.gcloud.arguments) -contains '--to-revisions=pnl-web-dynamic-fixture-a1b2c3=100') -Message 'Pre-release rollback did not use captured state.'

    & (Join-Path $PSScriptRoot 'staging-release.ps1') `
        -Operation ROLLBACK `
        -ProjectId $project `
        -ProjectNumber $projectNumber `
        -Region $region `
        -Service $service `
        -RollbackKind GOLDEN `
        -GitHead $head `
        -GcloudPath (Join-Path $testRoot 'must-not-run-gcloud.cmd') `
        -OutputDirectory $rollbackOutput | Out-Null
    $goldenPlan = Get-Content -Raw -LiteralPath (Join-Path $rollbackOutput 'rollback-golden.json') | ConvertFrom-Json
    Assert-Equal -Actual $goldenPlan.target_revision -Expected 'pnl-web-golden-1e478b6' -Message 'Golden rollback target changed.'
    Assert-Equal -Actual $goldenPlan.incident_approval_required -Expected $true -Message 'Golden rollback lost incident approval gate.'
}
finally {
    if (Test-Path -LiteralPath $testRoot) {
        $resolvedTestRoot = [IO.Path]::GetFullPath($testRoot)
        if (-not $resolvedTestRoot.StartsWith(
            $renderedRoot + [IO.Path]::DirectorySeparatorChar,
            [StringComparison]::OrdinalIgnoreCase
        )) {
            throw 'Refusing to remove a test directory outside deploy/gcp/rendered.'
        }
        Remove-Item -LiteralPath $resolvedTestRoot -Recurse -Force
    }
}

Write-Output 'STAGING_RELEASE_TOOLING_TESTS=PASS cloud_mutation=NONE'
