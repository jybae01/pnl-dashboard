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

function Get-TestSha256Digest {
    param([Parameter(Mandatory)] [string] $Value)

    return 'sha256:' + [Convert]::ToHexString(
        [Security.Cryptography.SHA256]::HashData([Text.Encoding]::UTF8.GetBytes($Value))
    ).ToLowerInvariant()
}

function New-TestOciIndexManifestJson {
    param(
        [Parameter(Mandatory)] [string] $ChildDigest,
        [string] $OperatingSystem = 'linux',
        [string] $Architecture = 'amd64'
    )

    return [ordered]@{
        schemaVersion = 2
        mediaType = 'application/vnd.oci.image.index.v1+json'
        manifests = @(
            [ordered]@{
                mediaType = 'application/vnd.oci.image.manifest.v1+json'
                digest = $ChildDigest
                size = 1234
                platform = [ordered]@{
                    architecture = $Architecture
                    os = $OperatingSystem
                }
            }
        )
    } | ConvertTo-Json -Depth 10 -Compress
}

$canonical = 'https://pnl-web-498160536475.asia-southeast1.run.app'
$statusUrl = 'https://pnl-web-t4n4rdoznq-as.a.run.app'
$originPair = "$canonical,$statusUrl"
$head = '37d3db2354d8eedb7fa410c06fca7b48c495bc1f'
$otherHead = '47d3db2354d8eedb7fa410c06fca7b48c495bc1f'
$samePrefixOtherHead = '37d3db2354d80000000000000000000000000000'
$validatedRevisionAHead = '30d270a71359cbe33981ed51d9e7fc36fb7c7522'
$revisionBHead = '6328ee436a2487b54633cc70298dfde4e03bfdb9'
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
$runtimeRepository = 'asia-southeast1-docker.pkg.dev/pnl-dashboard-staging/pnl-staging/pnl-runtime'
$runtimeChildDigest = 'sha256:' + ('5' * 64)
$runtimeUnrelatedDigest = 'sha256:' + ('6' * 64)
$runtimeChild = "$runtimeRepository@$runtimeChildDigest"
$runtimeUnrelatedChild = "$runtimeRepository@$runtimeUnrelatedDigest"
$runtimeIndexJson = New-TestOciIndexManifestJson -ChildDigest $runtimeChildDigest
$runtimeIndex = "$runtimeRepository@$(Get-TestSha256Digest -Value $runtimeIndexJson)"
$wrongPlatformIndexJson = New-TestOciIndexManifestJson `
    -ChildDigest $runtimeChildDigest `
    -Architecture 'arm64'
$wrongPlatformIndex = "$runtimeRepository@$(Get-TestSha256Digest -Value $wrongPlatformIndexJson)"
$mutableEdgeTag = 'asia-southeast1-docker.pkg.dev/pnl-dashboard-staging/pnl-staging/pnl-web:legacy-edge'
$mutableRuntimeTag = 'asia-southeast1-docker.pkg.dev/pnl-dashboard-staging/pnl-staging/pnl-runtime:analysis-v31-4ad67ad'
$backendIdentity = Get-PnlStagingReleaseIdentity -Stage BACKEND_FIRST -GitHead $head -Service $service
$frontendIdentity = Get-PnlStagingReleaseIdentity -Stage FINAL_FRONTEND -GitHead $head -Service $service
$explicitBackendIdentity = Get-PnlStagingReleaseIdentity -Stage BACKEND_FIRST -GitHead $validatedRevisionAHead -Service $service
$explicitFrontendIdentity = Get-PnlStagingReleaseIdentity -Stage FINAL_FRONTEND -GitHead $revisionBHead -Service $service

Assert-PnlStagingTarget -ProjectId $project -ProjectNumber $projectNumber -Region $region -Service $service
foreach ($invalidTarget in @(
    @('wrong-project', $projectNumber, $region, $service),
    @($project, '111111111111', $region, $service),
    @($project, $projectNumber, 'us-central1', $service),
    @($project, $projectNumber, $region, 'wrong-service')
)) {
    Assert-Throws `
        -Action {
            Assert-PnlStagingTarget `
                -ProjectId $invalidTarget[0] `
                -ProjectNumber $invalidTarget[1] `
                -Region $invalidTarget[2] `
                -Service $invalidTarget[3]
        } `
        -Message "Invalid staging target passed: $($invalidTarget -join '/')"
}

Assert-PnlApprovedStagingOrigin -Origin $canonical
Assert-PnlApprovedStagingOrigin -Origin $statusUrl
Assert-Equal `
    -Actual (ConvertTo-PnlApprovedStagingOriginValue -Origins $originPair) `
    -Expected $originPair `
    -Message 'The exact approved pair must pass.'
Assert-Equal `
    -Actual (ConvertTo-PnlApprovedStagingOriginValue -Origins "$statusUrl,$canonical") `
    -Expected $originPair `
    -Message 'The reverse approved set must canonicalize to the deterministic order.'

foreach ($invalid in @(
    '*',
    $canonical,
    $statusUrl,
    'https://localhost',
    'https://127.0.0.1',
    'http://pnl-web-498160536475.asia-southeast1.run.app',
    'https://third-party.example',
    'https://pnl-web-498160536475.asia-southeast1.run.app/path',
    'https://pnl-web-498160536475.asia-southeast1.run.app?unsafe=true',
    'not-a-uri',
    "$originPair,https://third.example",
    "$canonical,$canonical",
    "$canonical, $statusUrl"
)) {
    Assert-Throws `
        -Action { ConvertTo-PnlApprovedStagingOriginValue -Origins $invalid } `
        -Message "Malformed or unapproved origin value passed: $invalid"
}

Assert-Equal -Actual $backendIdentity.revision_suffix -Expected "pnlbe-$head" -Message 'Backend suffix is not deterministic.'
Assert-Equal -Actual $frontendIdentity.revision_suffix -Expected "pnlfe-$head" -Message 'Frontend suffix is not deterministic.'
Assert-Equal -Actual $backendIdentity.candidate_tag -Expected "pnlbe-$($head.Substring(0, 16))" -Message 'Revision A tag is not the deterministic 16-character HEAD prefix.'
Assert-Equal -Actual $frontendIdentity.candidate_tag -Expected "pnlfe-$($head.Substring(0, 16))" -Message 'Revision B tag is not the deterministic 16-character HEAD prefix.'
Assert-True -Condition ($backendIdentity.revision_name -ne $frontendIdentity.revision_name) -Message 'Revision A/B names collided.'
Assert-True -Condition ($backendIdentity.candidate_tag -ne $frontendIdentity.candidate_tag) -Message 'Revision A/B tags collided.'
Assert-Equal `
    -Actual (Get-PnlStagingReleaseIdentity -Stage BACKEND_FIRST -GitHead $head -Service $service).revision_name `
    -Expected $backendIdentity.revision_name `
    -Message 'The same full HEAD and stage must be deterministic.'
Assert-Equal `
    -Actual (Get-PnlStagingReleaseIdentity -Stage BACKEND_FIRST -GitHead $head -Service $service).candidate_tag `
    -Expected $backendIdentity.candidate_tag `
    -Message 'The same full HEAD and stage must produce the same tag.'
Assert-True `
    -Condition ((Get-PnlStagingReleaseIdentity -Stage BACKEND_FIRST -GitHead $otherHead -Service $service).revision_name -ne $backendIdentity.revision_name) `
    -Message 'Different HEAD values must produce different identities.'
Assert-True `
    -Condition ((Get-PnlStagingReleaseIdentity -Stage BACKEND_FIRST -GitHead $samePrefixOtherHead -Service $service).revision_name -ne $backendIdentity.revision_name) `
    -Message 'The final identity must not retain the 12-character-prefix collision risk.'
Assert-True -Condition ($backendIdentity.revision_name -match '^pnl-web-pnlbe-[0-9a-f]{40}$') -Message 'Backend revision must contain the full HEAD.'
Assert-True -Condition ($frontendIdentity.revision_name -match '^pnl-web-pnlfe-[0-9a-f]{40}$') -Message 'Frontend revision must contain the full HEAD.'
Assert-True -Condition (($service.Length + $backendIdentity.candidate_tag.Length) -le 46) -Message 'Revision A service and tag exceed the Cloud Run combined length limit.'
Assert-True -Condition (($service.Length + $frontendIdentity.candidate_tag.Length) -le 46) -Message 'Revision B service and tag exceed the Cloud Run combined length limit.'
Assert-Throws -Action { Get-PnlStagingReleaseIdentity -Stage BACKEND_FIRST -GitHead 'abc123' -Service $service } -Message 'Invalid HEAD passed.'
foreach ($ambiguous in @('latest', 'newest', 'current', 'candidate', 'pnlbe-latest')) {
    Assert-Throws -Action { Assert-PnlCandidateTag -Tag $ambiguous } -Message "Ambiguous tag passed: $ambiguous"
    Assert-Throws -Action { Assert-PnlExplicitRevisionTarget -Revision $ambiguous -Service $service } -Message "Ambiguous revision passed: $ambiguous"
}

Assert-PnlDigestImage -Image $frozenEdge -Role edge
Assert-PnlDigestImage -Image $runtimeA -Role runtime
foreach ($invalidImageCase in @(
    @('us-central1-docker.pkg.dev/pnl-dashboard-staging/pnl-staging/pnl-web@sha256:' + ('1' * 64), 'edge'),
    @('gcr.io/pnl-dashboard-staging/pnl-web@sha256:' + ('1' * 64), 'edge'),
    @('asia-southeast1-docker.pkg.dev/wrong-project/pnl-staging/pnl-web@sha256:' + ('1' * 64), 'edge'),
    @('asia-southeast1-docker.pkg.dev/pnl-dashboard-staging/wrong-repository/pnl-runtime@sha256:' + ('1' * 64), 'runtime'),
    @($runtimeA, 'edge'),
    @('asia-southeast1-docker.pkg.dev/pnl-dashboard-staging/pnl-staging/pnl-web:latest', 'edge'),
    @($mutableRuntimeTag, 'runtime'),
    @('asia-southeast1-docker.pkg.dev/pnl-dashboard-staging/pnl-staging/pnl-web@sha256:1234', 'edge')
)) {
    Assert-Throws `
        -Action { Assert-PnlDigestImage -Image $invalidImageCase[0] -Role $invalidImageCase[1] } `
        -Message "Invalid image provenance passed: $($invalidImageCase[0])"
}

$activeFixture = [pscustomobject]@{
    metadata = [pscustomobject]@{ name = $service; namespace = $projectNumber }
    status = [pscustomobject]@{
        traffic = @(
            [pscustomobject]@{ revisionName = 'pnl-web-dynamic-fixture-a1b2c3'; percent = 100 },
            [pscustomobject]@{ revisionName = $backendIdentity.revision_name; tag = $backendIdentity.candidate_tag }
        )
    }
}

$directRuntimeAuthority = Assert-PnlRuntimeImageResolution `
    -RequestedImage $runtimeA `
    -ObservedImage $runtimeA
Assert-Equal `
    -Actual $directRuntimeAuthority.resolution `
    -Expected 'DIRECT_MANIFEST' `
    -Message 'Direct immutable runtime manifest equality did not pass.'

$indexRuntimeAuthority = Assert-PnlRuntimeImageResolution `
    -RequestedImage $runtimeIndex `
    -ObservedImage $runtimeChild `
    -RequestedManifestJson $runtimeIndexJson
Assert-Equal `
    -Actual $indexRuntimeAuthority.resolution `
    -Expected 'OCI_INDEX' `
    -Message 'Exact OCI index to linux/amd64 child resolution did not pass.'
Assert-Equal `
    -Actual $indexRuntimeAuthority.platform `
    -Expected 'linux/amd64' `
    -Message 'OCI runtime authority recorded the wrong platform.'
Assert-Equal `
    -Actual $indexRuntimeAuthority.parent_child_confirmed `
    -Expected $true `
    -Message 'OCI runtime authority did not record the verified parent-child relation.'

Assert-Throws -Action {
    Assert-PnlRuntimeImageResolution `
        -RequestedImage $runtimeIndex `
        -ObservedImage $runtimeUnrelatedChild `
        -RequestedManifestJson $runtimeIndexJson
} -Message 'OCI index accepted an unrelated child digest.'
Assert-Throws -Action {
    Assert-PnlRuntimeImageResolution `
        -RequestedImage $wrongPlatformIndex `
        -ObservedImage $runtimeChild `
        -RequestedManifestJson $wrongPlatformIndexJson
} -Message 'OCI index accepted a child for the wrong platform.'
foreach ($wrongRepositoryChild in @(
    'asia-southeast1-docker.pkg.dev/pnl-dashboard-staging/wrong-repository/pnl-runtime@' + $runtimeChildDigest,
    'asia-southeast1-docker.pkg.dev/wrong-project/pnl-staging/pnl-runtime@' + $runtimeChildDigest
)) {
    Assert-Throws -Action {
        Assert-PnlRuntimeImageResolution `
            -RequestedImage $runtimeIndex `
            -ObservedImage $wrongRepositoryChild `
            -RequestedManifestJson $runtimeIndexJson
    } -Message "OCI index accepted a child from the wrong repository or project: $wrongRepositoryChild"
}
Assert-Throws -Action {
    Assert-PnlRuntimeImageResolution `
        -RequestedImage $mutableRuntimeTag `
        -ObservedImage $runtimeChild `
        -RequestedManifestJson $runtimeIndexJson
} -Message 'OCI runtime resolution accepted a mutable requested image.'
Assert-Throws -Action {
    Assert-PnlRuntimeImageResolution `
        -RequestedImage $runtimeIndex `
        -ObservedImage $runtimeChild `
        -RequestedManifestJson ''
} -Message 'OCI runtime resolution accepted a missing parent-child relation.'
Assert-Equal `
    -Actual (Get-PnlActiveRevision -ServiceDescription $activeFixture -Service $service) `
    -Expected 'pnl-web-dynamic-fixture-a1b2c3' `
    -Message 'Dynamic active revision capture failed.'
$invalidTrafficFixtures = @(
    '{"metadata":{"name":"pnl-web","namespace":"498160536475"},"status":{"traffic":[{"revisionName":"pnl-web-one","percent":50},{"revisionName":"pnl-web-two","percent":50}]}}',
    '{"metadata":{"name":"pnl-web","namespace":"498160536475"},"status":{"traffic":[null]}}',
    '{"metadata":{"name":"pnl-web","namespace":"498160536475"},"status":{"traffic":["malformed-record"]}}',
    '{"metadata":{"name":"pnl-web","namespace":"498160536475"},"status":{"traffic":[{"tag":"pnlbe-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","percent":100}]}}',
    '{"metadata":{"name":"pnl-web","namespace":"498160536475"},"status":{"traffic":[{"revisionName":"pnl-web-one","percent":99.9}]}}',
    '{"metadata":{"name":"pnl-web","namespace":"498160536475"},"status":{"traffic":[{"revisionName":"pnl-web-one","percent":"100"}]}}',
    '{"metadata":{"name":"pnl-web","namespace":"498160536475"},"status":{"traffic":[{"revisionName":"pnl-web-one","percent":true}]}}',
    '{"metadata":{"name":"pnl-web","namespace":"498160536475"},"status":{"traffic":[{"revisionName":"pnl-web-one"}]}}',
    '{"metadata":{"name":"pnl-web","namespace":"498160536475"},"status":{"traffic":[{"revisionName":"pnl-web-one","percent":null}]}}',
    '{"metadata":{"name":"pnl-web","namespace":"498160536475"},"status":{"traffic":[{"revisionName":"pnl-web-one","percent":100},{"revisionName":"pnl-web-two","tag":"latest"}]}}',
    '{"metadata":{"name":"wrong-service","namespace":"498160536475"},"status":{"traffic":[{"revisionName":"pnl-web-one","percent":100}]}}',
    '{"metadata":{"name":"pnl-web","namespace":"111111111111"},"status":{"traffic":[{"revisionName":"pnl-web-one","percent":100}]}}',
    '{"metadata":{"name":"pnl-web","namespace":"498160536475"},"status":{"traffic":[]}}'
)
foreach ($invalidTrafficJson in $invalidTrafficFixtures) {
    Assert-Throws `
        -Action { Get-PnlActiveRevision -ServiceDescription ($invalidTrafficJson | ConvertFrom-Json) -Service $service } `
        -Message "Malformed or ambiguous traffic passed: $invalidTrafficJson"
}

function New-TestServiceDescription {
    param(
        [Parameter(Mandatory)] [string] $ObservedEdgeImage,
        [Parameter(Mandatory)] [string] $ObservedRuntimeImage,
        [Parameter(Mandatory)] [string] $ActiveRevision,
        [string] $ObservedOrigins = $originPair
    )

    $environment = [ordered]@{
        PNL_REPOSITORY_BACKEND = 'supabase'
        SUPABASE_URL = $supabaseUrl
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
        BFF_ALLOWED_ORIGINS = $ObservedOrigins
        BFF_COOKIE_SECURE = 'true'
        BFF_COOKIE_SAME_SITE = 'strict'
        BFF_PROXY_MODE = 'direct'
        BFF_WORKER_LIFECYCLE_MODE = 'demand_only'
        BFF_WORKER_CONTROLLER_URL = $controllerUrl
        BFF_TEMP_ROOT = '/var/tmp/pnl'
        BFF_TEMP_QUOTA_BYTES = '536870912'
        PNL_VOLUME_CANARY_PATHS = '/var/tmp/pnl:/app/data'
        BFF_TEMP_ORPHAN_AGE_SECONDS = '86400'
        BFF_PARSER_TIMEOUT_SECONDS = '45'
        BFF_PARSER_MEMORY_LIMIT_BYTES = '805306368'
        BFF_PARSER_MAX_CONCURRENCY = '1'
        BFF_LOG_LEVEL = 'INFO'
    }
    $secretAnnotation = @(
        'pnl-supabase-secret-key:projects/498160536475/secrets/pnl-supabase-secret-key',
        'pnl-viewer-code:projects/498160536475/secrets/pnl-viewer-code',
        'pnl-admin-code:projects/498160536475/secrets/pnl-admin-code',
        'pnl-actor-namespace-secret:projects/498160536475/secrets/pnl-actor-namespace-secret',
        'pnl-csrf-secret:projects/498160536475/secrets/pnl-csrf-secret'
    ) -join ','
    $fixture = [ordered]@{
        metadata = [ordered]@{
            name = $service
            namespace = $projectNumber
            annotations = [ordered]@{ 'run.googleapis.com/ingress' = 'all' }
        }
        spec = [ordered]@{
            template = [ordered]@{
                metadata = [ordered]@{
                    annotations = [ordered]@{
                        'autoscaling.knative.dev/minScale' = '0'
                        'autoscaling.knative.dev/maxScale' = '2'
                        'run.googleapis.com/container-dependencies' = '{"edge":["bff"]}'
                        'run.googleapis.com/execution-environment' = 'gen2'
                        'run.googleapis.com/secrets' = $secretAnnotation
                        'run.googleapis.com/startup-cpu-boost' = 'true'
                    }
                }
                spec = [ordered]@{
                    serviceAccountName = 'pnl-web@pnl-dashboard-staging.iam.gserviceaccount.com'
                    containerConcurrency = 4
                    timeoutSeconds = 180
                    containers = @(
                        [ordered]@{
                            name = 'edge'
                            image = $ObservedEdgeImage
                            ports = @([ordered]@{ name = 'http1'; containerPort = 8080 })
                            resources = [ordered]@{ limits = [ordered]@{ cpu = '1'; memory = '512Mi' } }
                            startupProbe = [ordered]@{
                                httpGet = [ordered]@{ path = '/health/ready'; port = 8080 }
                                timeoutSeconds = 3
                                periodSeconds = 5
                                failureThreshold = 24
                            }
                        },
                        [ordered]@{
                            name = 'bff'
                            image = $ObservedRuntimeImage
                            resources = [ordered]@{ limits = [ordered]@{ cpu = '1'; memory = '2Gi' } }
                            env = @($environment.GetEnumerator() | ForEach-Object {
                                [ordered]@{ name = $_.Key; value = [string]$_.Value }
                            })
                            startupProbe = [ordered]@{
                                httpGet = [ordered]@{ path = '/health/ready'; port = 8000 }
                                timeoutSeconds = 3
                                periodSeconds = 5
                                failureThreshold = 24
                            }
                            livenessProbe = [ordered]@{
                                httpGet = [ordered]@{ path = '/health/live'; port = 8000 }
                                timeoutSeconds = 3
                                periodSeconds = 30
                                failureThreshold = 3
                            }
                            volumeMounts = @(
                                [ordered]@{ name = 'bff-temp'; mountPath = '/var/tmp/pnl' },
                                [ordered]@{ name = 'model-cache'; mountPath = '/app/data' },
                                [ordered]@{ name = 'supabase-secret'; mountPath = '/var/run/pnl-secrets/supabase' },
                                [ordered]@{ name = 'viewer-secret'; mountPath = '/var/run/pnl-secrets/viewer' },
                                [ordered]@{ name = 'admin-secret'; mountPath = '/var/run/pnl-secrets/admin' },
                                [ordered]@{ name = 'actor-secret'; mountPath = '/var/run/pnl-secrets/actor' },
                                [ordered]@{ name = 'csrf-secret'; mountPath = '/var/run/pnl-secrets/csrf' }
                            )
                        }
                    )
                    volumes = @(
                        [ordered]@{ name = 'bff-temp'; emptyDir = [ordered]@{ medium = 'Memory'; sizeLimit = '512Mi' } },
                        [ordered]@{ name = 'model-cache'; emptyDir = [ordered]@{ medium = 'Memory'; sizeLimit = '256Mi' } },
                        [ordered]@{ name = 'supabase-secret'; secret = [ordered]@{ secretName = 'pnl-supabase-secret-key' } },
                        [ordered]@{ name = 'viewer-secret'; secret = [ordered]@{ secretName = 'pnl-viewer-code' } },
                        [ordered]@{ name = 'admin-secret'; secret = [ordered]@{ secretName = 'pnl-admin-code' } },
                        [ordered]@{ name = 'actor-secret'; secret = [ordered]@{ secretName = 'pnl-actor-namespace-secret' } },
                        [ordered]@{ name = 'csrf-secret'; secret = [ordered]@{ secretName = 'pnl-csrf-secret' } }
                    )
                }
            }
        }
        status = [ordered]@{
            traffic = @([ordered]@{ revisionName = $ActiveRevision; percent = 100 })
        }
    }
    return ($fixture | ConvertTo-Json -Depth 100 | ConvertFrom-Json -Depth 100)
}

function New-TestActiveRevisionDescription {
    param(
        [Parameter(Mandatory)] [string] $Revision,
        [Parameter(Mandatory)] [string] $ResolvedEdgeImage,
        [Parameter(Mandatory)] [string] $ResolvedRuntimeImage,
        [string] $ReadyStatus = 'True'
    )

    return ([ordered]@{
        metadata = [ordered]@{
            name = $Revision
            namespace = $projectNumber
        }
        spec = [ordered]@{
            containers = @(
                [ordered]@{ name = 'edge'; image = $ResolvedEdgeImage },
                [ordered]@{ name = 'bff'; image = $ResolvedRuntimeImage }
            )
        }
        status = [ordered]@{
            conditions = @(
                [ordered]@{ type = 'Ready'; status = $ReadyStatus },
                [ordered]@{ type = 'Active'; status = 'True' }
            )
        }
    } | ConvertTo-Json -Depth 20 | ConvertFrom-Json -Depth 20)
}

function Invoke-TestRevisionBCandidate {
    param(
        [Parameter(Mandatory)] [string] $CandidateGitHead,
        [Parameter(Mandatory)] [string] $ServiceJsonPath,
        [Parameter(Mandatory)] [string] $ActiveRevisionJsonPath,
        [Parameter(Mandatory)] [string] $OutputDirectory,
        [Parameter(Mandatory)] [string] $GcloudPath,
        [AllowEmptyString()] [string] $ExplicitRevisionA,
        [string] $ValidatedAEdgeImage = $frozenEdge,
        [string] $ValidatedARuntimeImage = $runtimeA
    )

    $candidateIdentity = Get-PnlStagingReleaseIdentity `
        -Stage FINAL_FRONTEND `
        -GitHead $CandidateGitHead `
        -Service $service
    $candidateParameters = @{
        Operation = 'CANDIDATE'
        ProjectId = $project
        ProjectNumber = $projectNumber
        Region = $region
        Service = $service
        Stage = 'FINAL_FRONTEND'
        GitHead = $CandidateGitHead
        ApprovedOrigins = $originPair
        SupabaseUrl = $supabaseUrl
        WorkerControllerUrl = $controllerUrl
        FinalEdgeImage = $finalEdge
        RuntimeImage = $runtimeA
        ValidatedRevisionAEdgeImage = $ValidatedAEdgeImage
        ValidatedRevisionARuntimeImage = $ValidatedARuntimeImage
        CapturedServiceJsonPath = $ServiceJsonPath
        CapturedActiveRevisionJsonPath = $ActiveRevisionJsonPath
        RevisionSuffix = $candidateIdentity.revision_suffix
        CandidateTag = $candidateIdentity.candidate_tag
        GcloudPath = $GcloudPath
        OutputDirectory = $OutputDirectory
    }
    if (-not [string]::IsNullOrWhiteSpace($ExplicitRevisionA)) {
        $candidateParameters.ValidatedRevisionA = $ExplicitRevisionA
    }
    & (Join-Path $PSScriptRoot 'staging-release.ps1') @candidateParameters | Out-Null
    return Get-Content -Raw -LiteralPath (Join-Path $OutputDirectory 'candidate-final-frontend.json') | ConvertFrom-Json
}

function Invoke-TestRevisionBPromotion {
    param(
        [Parameter(Mandatory)] [string] $CandidateGitHead,
        [Parameter(Mandatory)] [string] $ServiceJsonPath,
        [Parameter(Mandatory)] [string] $OutputDirectory,
        [Parameter(Mandatory)] [string] $GcloudPath,
        [AllowEmptyString()] [string] $ExplicitRevisionA,
        [AllowEmptyString()] [string] $ActiveRevisionJsonPath
    )

    $candidateIdentity = Get-PnlStagingReleaseIdentity `
        -Stage FINAL_FRONTEND `
        -GitHead $CandidateGitHead `
        -Service $service
    $promotionParameters = @{
        Operation = 'PROMOTE'
        ProjectId = $project
        ProjectNumber = $projectNumber
        Region = $region
        Service = $service
        Stage = 'FINAL_FRONTEND'
        GitHead = $CandidateGitHead
        Revision = $candidateIdentity.revision_name
        SmokeGate = 'passed'
        CapturedServiceJsonPath = $ServiceJsonPath
        GcloudPath = $GcloudPath
        OutputDirectory = $OutputDirectory
    }
    if (-not [string]::IsNullOrWhiteSpace($ExplicitRevisionA)) {
        $promotionParameters.ValidatedRevisionA = $ExplicitRevisionA
        $promotionParameters.CapturedActiveRevisionJsonPath = $ActiveRevisionJsonPath
    }
    & (Join-Path $PSScriptRoot 'staging-release.ps1') @promotionParameters | Out-Null
    return Get-Content -Raw -LiteralPath (Join-Path $OutputDirectory 'promote-final-frontend.json') | ConvertFrom-Json
}

$legacyActiveRevision = 'pnl-web-legacy-active'
$legacyTemplateFixture = New-TestServiceDescription `
    -ObservedEdgeImage $finalEdge `
    -ObservedRuntimeImage $mutableRuntimeTag `
    -ActiveRevision $legacyActiveRevision
$validResolvedRevision = New-TestActiveRevisionDescription `
    -Revision $legacyActiveRevision `
    -ResolvedEdgeImage $frozenEdge `
    -ResolvedRuntimeImage $runtimeB
$resolvedBaseline = Get-PnlResolvedActiveRevisionBaseline `
    -ServiceDescription $legacyTemplateFixture `
    -RevisionDescription $validResolvedRevision `
    -Service $service
Assert-Equal -Actual $resolvedBaseline.active_revision -Expected $legacyActiveRevision -Message 'Resolved baseline selected the wrong active revision.'
Assert-Equal -Actual $resolvedBaseline.ready -Expected $true -Message 'Resolved baseline did not require Ready=True.'
Assert-Equal -Actual $resolvedBaseline.edge_image -Expected $frozenEdge -Message 'Resolved baseline used the mutable service template instead of the active edge digest.'
Assert-Equal -Actual $resolvedBaseline.runtime_image -Expected $runtimeB -Message 'Resolved baseline used the mutable service template instead of the active runtime digest.'

$missingResolvedDigest = New-TestActiveRevisionDescription `
    -Revision $legacyActiveRevision `
    -ResolvedEdgeImage $frozenEdge `
    -ResolvedRuntimeImage $runtimeB
$missingResolvedDigest.spec.containers[1].PSObject.Properties.Remove('image')
Assert-Throws -Action {
    Get-PnlResolvedActiveRevisionBaseline `
        -ServiceDescription $legacyTemplateFixture `
        -RevisionDescription $missingResolvedDigest `
        -Service $service
} -Message 'Mutable service template passed when the active revision runtime digest was missing.'

foreach ($invalidResolvedRuntime in @(
    'asia-southeast1-docker.pkg.dev/wrong-project/pnl-staging/pnl-runtime@sha256:' + ('4' * 64),
    'us-central1-docker.pkg.dev/pnl-dashboard-staging/pnl-staging/pnl-runtime@sha256:' + ('4' * 64),
    $frozenEdge,
    'asia-southeast1-docker.pkg.dev/pnl-dashboard-staging/pnl-staging/pnl-runtime@sha256:malformed'
)) {
    $invalidResolvedRevision = New-TestActiveRevisionDescription `
        -Revision $legacyActiveRevision `
        -ResolvedEdgeImage $frozenEdge `
        -ResolvedRuntimeImage $invalidResolvedRuntime
    Assert-Throws -Action {
        Get-PnlResolvedActiveRevisionBaseline `
            -ServiceDescription $legacyTemplateFixture `
            -RevisionDescription $invalidResolvedRevision `
            -Service $service
    } -Message "Invalid active revision runtime provenance passed: $invalidResolvedRuntime"
}

$notReadyRevision = New-TestActiveRevisionDescription `
    -Revision $legacyActiveRevision `
    -ResolvedEdgeImage $frozenEdge `
    -ResolvedRuntimeImage $runtimeB `
    -ReadyStatus 'False'
Assert-Throws -Action {
    Get-PnlResolvedActiveRevisionBaseline `
        -ServiceDescription $legacyTemplateFixture `
        -RevisionDescription $notReadyRevision `
        -Service $service
} -Message 'An active revision without Ready=True passed the resolved baseline.'

$badResolvedTopology = New-TestActiveRevisionDescription `
    -Revision $legacyActiveRevision `
    -ResolvedEdgeImage $frozenEdge `
    -ResolvedRuntimeImage $runtimeB
$badResolvedTopology.spec.containers[1].name = 'worker'
Assert-Throws -Action {
    Get-PnlResolvedActiveRevisionBaseline `
        -ServiceDescription $legacyTemplateFixture `
        -RevisionDescription $badResolvedTopology `
        -Service $service
} -Message 'Unexpected active revision container topology passed the resolved baseline.'

$splitTrafficFixture = New-TestServiceDescription `
    -ObservedEdgeImage $finalEdge `
    -ObservedRuntimeImage $mutableRuntimeTag `
    -ActiveRevision $legacyActiveRevision
$splitTrafficFixture.status.traffic = @(
    [pscustomobject]@{ revisionName = $legacyActiveRevision; percent = 50 },
    [pscustomobject]@{ revisionName = 'pnl-web-other-active'; percent = 50 }
)
Assert-Throws -Action {
    Get-PnlResolvedActiveRevisionBaseline `
        -ServiceDescription $splitTrafficFixture `
        -RevisionDescription $validResolvedRevision `
        -Service $service
} -Message 'Split traffic passed the resolved active-revision baseline.'

$installedGcloud = if ([Environment]::OSVersion.Platform -eq [PlatformID]::Win32NT) {
    Join-Path $env:LOCALAPPDATA 'Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd'
}
else {
    'gcloud'
}
$resolvedInstalledGcloud = Assert-PnlGcloudCandidateCapabilities -GcloudPath $installedGcloud
Assert-True -Condition (-not [string]::IsNullOrWhiteSpace($resolvedInstalledGcloud)) -Message 'Installed gcloud executable did not resolve.'
Assert-Equal `
    -Actual (Assert-PnlGcloudTrafficCapabilities -GcloudPath $installedGcloud) `
    -Expected $resolvedInstalledGcloud `
    -Message 'Installed gcloud explicit traffic capability validation failed.'

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
    $mustNotRunGcloud = Join-Path $testRoot 'must-not-run-gcloud.cmd'
    $gcloudInvocationMarker = Join-Path $testRoot 'gcloud-invoked.txt'
    [IO.File]::WriteAllText(
        $mustNotRunGcloud,
        "@echo off`r`necho invoked>`"%~dp0gcloud-invoked.txt`"`r`nexit /b 97`r`n",
        [Text.ASCIIEncoding]::new()
    )
    $revisionAPreflightPath = Join-Path $testRoot 'revision-a-service.json'
    $revisionAActiveRevisionPath = Join-Path $testRoot 'revision-a-active-revision.json'
    $revisionBPreflightPath = Join-Path $testRoot 'revision-b-service.json'
    $revisionBMutableTemplatePath = Join-Path $testRoot 'revision-b-mutable-template-service.json'
    $revisionBActiveRevisionPath = Join-Path $testRoot 'revision-b-active-revision.json'
    [IO.File]::WriteAllText(
        $revisionAPreflightPath,
        ((New-TestServiceDescription `
            -ObservedEdgeImage $finalEdge `
            -ObservedRuntimeImage $mutableRuntimeTag `
            -ActiveRevision 'pnl-web-pre-release-fixture') | ConvertTo-Json -Depth 100),
        [Text.UTF8Encoding]::new($false)
    )
    [IO.File]::WriteAllText(
        $revisionAActiveRevisionPath,
        ((New-TestActiveRevisionDescription `
            -Revision 'pnl-web-pre-release-fixture' `
            -ResolvedEdgeImage $frozenEdge `
            -ResolvedRuntimeImage $runtimeB) | ConvertTo-Json -Depth 100),
        [Text.UTF8Encoding]::new($false)
    )
    [IO.File]::WriteAllText(
        $revisionBPreflightPath,
        ((New-TestServiceDescription `
            -ObservedEdgeImage $frozenEdge `
            -ObservedRuntimeImage $runtimeA `
            -ActiveRevision $backendIdentity.revision_name) | ConvertTo-Json -Depth 100),
        [Text.UTF8Encoding]::new($false)
    )
    [IO.File]::WriteAllText(
        $revisionBActiveRevisionPath,
        ((New-TestActiveRevisionDescription `
            -Revision $backendIdentity.revision_name `
            -ResolvedEdgeImage $frozenEdge `
            -ResolvedRuntimeImage $runtimeA) | ConvertTo-Json -Depth 100),
        [Text.UTF8Encoding]::new($false)
    )
    [IO.File]::WriteAllText(
        $revisionBMutableTemplatePath,
        ((New-TestServiceDescription `
            -ObservedEdgeImage $frozenEdge `
            -ObservedRuntimeImage $mutableRuntimeTag `
            -ActiveRevision $backendIdentity.revision_name) | ConvertTo-Json -Depth 100),
        [Text.UTF8Encoding]::new($false)
    )
    $explicitRevisionAServicePath = Join-Path $testRoot 'explicit-revision-a-service.json'
    $explicitRevisionAActiveRevisionPath = Join-Path $testRoot 'explicit-revision-a-active-revision.json'
    $explicitRevisionAEdgeMismatchPath = Join-Path $testRoot 'explicit-revision-a-edge-mismatch.json'
    $explicitRevisionARuntimeMismatchPath = Join-Path $testRoot 'explicit-revision-a-runtime-mismatch.json'
    $explicitRevisionAInvalidEdgePath = Join-Path $testRoot 'explicit-revision-a-invalid-edge.json'
    $explicitRevisionAInvalidRuntimePath = Join-Path $testRoot 'explicit-revision-a-invalid-runtime.json'
    [IO.File]::WriteAllText(
        $explicitRevisionAServicePath,
        ((New-TestServiceDescription `
            -ObservedEdgeImage $frozenEdge `
            -ObservedRuntimeImage $runtimeA `
            -ActiveRevision $explicitBackendIdentity.revision_name) | ConvertTo-Json -Depth 100),
        [Text.UTF8Encoding]::new($false)
    )
    [IO.File]::WriteAllText(
        $explicitRevisionAActiveRevisionPath,
        ((New-TestActiveRevisionDescription `
            -Revision $explicitBackendIdentity.revision_name `
            -ResolvedEdgeImage $frozenEdge `
            -ResolvedRuntimeImage $runtimeA) | ConvertTo-Json -Depth 100),
        [Text.UTF8Encoding]::new($false)
    )
    [IO.File]::WriteAllText(
        $explicitRevisionAEdgeMismatchPath,
        ((New-TestActiveRevisionDescription `
            -Revision $explicitBackendIdentity.revision_name `
            -ResolvedEdgeImage $finalEdge `
            -ResolvedRuntimeImage $runtimeA) | ConvertTo-Json -Depth 100),
        [Text.UTF8Encoding]::new($false)
    )
    [IO.File]::WriteAllText(
        $explicitRevisionARuntimeMismatchPath,
        ((New-TestActiveRevisionDescription `
            -Revision $explicitBackendIdentity.revision_name `
            -ResolvedEdgeImage $frozenEdge `
            -ResolvedRuntimeImage $runtimeB) | ConvertTo-Json -Depth 100),
        [Text.UTF8Encoding]::new($false)
    )
    [IO.File]::WriteAllText(
        $explicitRevisionAInvalidEdgePath,
        ((New-TestActiveRevisionDescription `
            -Revision $explicitBackendIdentity.revision_name `
            -ResolvedEdgeImage $mutableEdgeTag `
            -ResolvedRuntimeImage $runtimeA) | ConvertTo-Json -Depth 100),
        [Text.UTF8Encoding]::new($false)
    )
    [IO.File]::WriteAllText(
        $explicitRevisionAInvalidRuntimePath,
        ((New-TestActiveRevisionDescription `
            -Revision $explicitBackendIdentity.revision_name `
            -ResolvedEdgeImage $frozenEdge `
            -ResolvedRuntimeImage $mutableRuntimeTag) | ConvertTo-Json -Depth 100),
        [Text.UTF8Encoding]::new($false)
    )
    $explicitRevisionANotActiveService = New-TestServiceDescription `
        -ObservedEdgeImage $frozenEdge `
        -ObservedRuntimeImage $runtimeA `
        -ActiveRevision $backendIdentity.revision_name
    $explicitRevisionANotActiveService.status.traffic = @(
        [pscustomobject]@{ revisionName = $backendIdentity.revision_name; percent = 100 },
        [pscustomobject]@{ revisionName = $explicitBackendIdentity.revision_name; tag = $explicitBackendIdentity.candidate_tag }
    )
    $explicitRevisionANotActiveServicePath = Join-Path $testRoot 'explicit-revision-a-not-active-service.json'
    [IO.File]::WriteAllText(
        $explicitRevisionANotActiveServicePath,
        ($explicitRevisionANotActiveService | ConvertTo-Json -Depth 100),
        [Text.UTF8Encoding]::new($false)
    )
    $baselineMismatchPath = Join-Path $testRoot 'revision-a-baseline-mismatch.json'
    $baselineMismatchActiveRevisionPath = Join-Path $testRoot 'revision-a-baseline-mismatch-active-revision.json'
    [IO.File]::WriteAllText(
        $baselineMismatchPath,
        ((New-TestServiceDescription `
            -ObservedEdgeImage $frozenEdge `
            -ObservedRuntimeImage $runtimeB `
            -ActiveRevision 'pnl-web-other-pre-release') | ConvertTo-Json -Depth 100),
        [Text.UTF8Encoding]::new($false)
    )
    [IO.File]::WriteAllText(
        $baselineMismatchActiveRevisionPath,
        ((New-TestActiveRevisionDescription `
            -Revision 'pnl-web-other-pre-release' `
            -ResolvedEdgeImage $frozenEdge `
            -ResolvedRuntimeImage $runtimeB) | ConvertTo-Json -Depth 100),
        [Text.UTF8Encoding]::new($false)
    )
    $preReleaseState = Join-Path $testRoot 'captured-pre-release.json'
    [IO.File]::WriteAllText(
        $preReleaseState,
        ([ordered]@{
            schema = 'pnl-staging-active-revision-v1'
            captured_at_utc = [DateTimeOffset]::UtcNow.ToString('o')
            purpose = 'pre-release rollback target'
            valid = $true
            project = $project
            project_number = $projectNumber
            region = $region
            service = $service
            source_commit = $head
            release_identity = $head
            active_revision = 'pnl-web-pre-release-fixture'
            traffic_percent = 100
        } | ConvertTo-Json -Depth 10),
        [Text.UTF8Encoding]::new($false)
    )

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
        -ApprovedOrigins "$statusUrl,$canonical" `
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

    Assert-Throws -Action {
        & (Join-Path $PSScriptRoot 'staging-release.ps1') `
            -Operation CANDIDATE -ProjectId $project -ProjectNumber $projectNumber -Region $region -Service $service `
            -Stage BACKEND_FIRST -GitHead $head -ApprovedOrigins $originPair `
            -SupabaseUrl $supabaseUrl -WorkerControllerUrl $controllerUrl `
            -FrozenEdgeImage $frozenEdge -RuntimeImage $mutableRuntimeTag `
            -PreReleaseStatePath $preReleaseState `
            -RevisionSuffix $backendIdentity.revision_suffix -CandidateTag $backendIdentity.candidate_tag `
            -OutputDirectory (Join-Path $testRoot 'reject-a-mutable-runtime')
    } -Message 'Revision A candidate accepted a mutable runtime image input.'
    Assert-Throws -Action {
        & (Join-Path $PSScriptRoot 'staging-release.ps1') `
            -Operation CANDIDATE -ProjectId $project -ProjectNumber $projectNumber -Region $region -Service $service `
            -Stage FINAL_FRONTEND -GitHead $head -ApprovedOrigins $originPair `
            -SupabaseUrl $supabaseUrl -WorkerControllerUrl $controllerUrl `
            -FinalEdgeImage $mutableEdgeTag -RuntimeImage $runtimeA `
            -ValidatedRevisionAEdgeImage $frozenEdge -ValidatedRevisionARuntimeImage $runtimeA `
            -RevisionSuffix $frontendIdentity.revision_suffix -CandidateTag $frontendIdentity.candidate_tag `
            -OutputDirectory (Join-Path $testRoot 'reject-b-mutable-edge')
    } -Message 'Revision B candidate accepted a mutable edge image input.'
    Assert-Throws -Action {
        & (Join-Path $PSScriptRoot 'staging-release.ps1') `
            -Operation CANDIDATE -ProjectId $project -ProjectNumber $projectNumber -Region $region -Service $service `
            -Stage BACKEND_FIRST -GitHead $head -ApprovedOrigins $originPair `
            -SupabaseUrl $supabaseUrl -WorkerControllerUrl $controllerUrl `
            -FrozenEdgeImage $frozenEdge -RuntimeImage $runtimeA `
            -PreReleaseStatePath $preReleaseState `
            -CapturedServiceJsonPath $revisionAPreflightPath `
            -RevisionSuffix $backendIdentity.revision_suffix -CandidateTag $backendIdentity.candidate_tag `
            -OutputDirectory (Join-Path $testRoot 'reject-missing-active-revision-capture')
    } -Message 'Candidate preflight accepted a service capture without the exact active revision capture.'

    $backendOutput = Join-Path $testRoot 'backend'
    Assert-Throws -Action {
        & (Join-Path $PSScriptRoot 'staging-release.ps1') `
            -Operation CANDIDATE -ProjectId $project -ProjectNumber $projectNumber -Region $region -Service $service `
            -Stage BACKEND_FIRST -GitHead $head -ApprovedOrigins $originPair `
            -SupabaseUrl $supabaseUrl -WorkerControllerUrl $controllerUrl `
            -FrozenEdgeImage $frozenEdge -RuntimeImage $runtimeA `
            -CapturedServiceJsonPath $revisionAPreflightPath `
            -CapturedActiveRevisionJsonPath $revisionAActiveRevisionPath `
            -RevisionSuffix $backendIdentity.revision_suffix -CandidateTag $backendIdentity.candidate_tag `
            -GcloudPath $mustNotRunGcloud -OutputDirectory (Join-Path $testRoot 'backend-missing-baseline')
    } -Message 'Revision A candidate generation accepted a missing persisted rollback baseline.'
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
        -PreReleaseStatePath $preReleaseState `
        -CapturedServiceJsonPath $revisionAPreflightPath `
        -CapturedActiveRevisionJsonPath $revisionAActiveRevisionPath `
        -RevisionSuffix $backendIdentity.revision_suffix `
        -CandidateTag $backendIdentity.candidate_tag `
        -GcloudPath (Join-Path $testRoot 'must-not-run-gcloud.cmd') `
        -OutputDirectory $backendOutput | Out-Null

    $backendPlan = Get-Content -Raw -LiteralPath (Join-Path $backendOutput 'candidate-backend-first.json') | ConvertFrom-Json
    $backendArguments = @($backendPlan.gcloud.arguments)
    Assert-Equal -Actual $backendPlan.dry_run -Expected $true -Message 'Candidate default must be dry-run.'
    Assert-Equal -Actual $backendPlan.cloud_mutation -Expected $false -Message 'Dry-run must report no Cloud mutation.'
    Assert-Equal -Actual $backendPlan.zero_traffic -Expected $true -Message 'Candidate plan must declare zero traffic.'
    Assert-Equal -Actual $backendPlan.production_traffic_percent -Expected ([long]0) -Message 'Candidate plan must declare zero production traffic.'
    Assert-Equal -Actual $backendPlan.service_preflight.evaluated -Expected $true -Message 'Offline Revision A preflight was not evaluated.'
    Assert-Equal -Actual $backendPlan.service_preflight.result.contract_valid -Expected $true -Message 'Offline Revision A preflight did not pass.'
    Assert-Equal -Actual $backendPlan.service_preflight.result.active_revision_ready -Expected $true -Message 'Offline Revision A preflight did not prove the active revision Ready.'
    Assert-Equal -Actual $backendPlan.service_preflight.result.active_image_source -Expected 'resolved active revision' -Message 'Offline Revision A preflight did not identify resolved revision images as authoritative.'
    Assert-Equal -Actual $backendPlan.service_preflight.result.observed_edge_image -Expected $frozenEdge -Message 'Offline Revision A preflight used the service template edge instead of the resolved active revision edge.'
    Assert-Equal -Actual $backendPlan.service_preflight.result.observed_runtime_image -Expected $runtimeB -Message 'Offline Revision A preflight used the mutable service template runtime instead of the resolved active revision runtime.'
    Assert-Equal -Actual $backendPlan.rollback_target -Expected 'pnl-web-pre-release-fixture' -Message 'Revision A candidate lost the explicit pre-release rollback target.'
    Assert-Equal -Actual $backendPlan.rollback_baseline.active_revision -Expected 'pnl-web-pre-release-fixture' -Message 'Revision A candidate did not validate the release-bound rollback baseline.'
    Assert-True -Condition ($backendArguments -contains '--no-traffic') -Message 'Candidate command omitted --no-traffic.'
    Assert-True -Condition ($backendArguments -contains "--revision-suffix=$($backendIdentity.revision_suffix)") -Message 'Candidate command omitted deterministic revision suffix.'
    Assert-True -Condition ($backendArguments -contains "--tag=$($backendIdentity.candidate_tag)") -Message 'Candidate command omitted deterministic tag.'
    Assert-True -Condition ($backendArguments -contains '--container=edge') -Message 'Candidate command omitted edge container.'
    Assert-True -Condition ($backendArguments -contains '--container=bff') -Message 'Candidate command omitted BFF container.'
    Assert-True -Condition ($backendArguments -contains '--port=8080') -Message 'Candidate command omitted explicit edge port.'
    Assert-True -Condition ($backendArguments -contains '--depends-on=bff') -Message 'Candidate command omitted explicit edge-to-BFF dependency.'
    $quietIndex = [Array]::IndexOf($backendArguments, '--quiet')
    $firstContainerIndex = [Array]::IndexOf($backendArguments, '--container=edge')
    Assert-Equal -Actual @($backendArguments | Where-Object { $_ -eq '--quiet' }).Count -Expected 1 -Message 'Candidate command must contain exactly one --quiet flag.'
    Assert-True -Condition ($quietIndex -ge 0 -and $quietIndex -lt $firstContainerIndex) -Message 'Candidate command must place --quiet before the first --container flag for gcloud 580.'
    Assert-True -Condition (-not ($backendArguments -contains '--platform=managed')) -Message 'Candidate command used unsupported --platform.'
    Assert-True -Condition ($backendArguments -contains "--image=$frozenEdge") -Message 'Backend candidate omitted frozen edge digest.'
    Assert-True -Condition ($backendArguments -contains "--image=$runtimeA") -Message 'Backend candidate omitted runtime digest.'
    $originArgument = @($backendArguments | Where-Object { $_ -like '--update-env-vars=*BFF_ALLOWED_ORIGINS=*' })
    Assert-Equal -Actual $originArgument.Count -Expected 1 -Message 'Candidate command must contain one allowed-origin update.'
    Assert-True -Condition ($originArgument[0].EndsWith("BFF_ALLOWED_ORIGINS=$originPair", [StringComparison]::Ordinal)) -Message 'Candidate command altered the approved origin pair.'
    Assert-True -Condition ($originArgument[0].StartsWith('--update-env-vars=^@^', [StringComparison]::Ordinal)) -Message 'Candidate plan did not retain the canonical alternate delimiter.'
    if ([Environment]::OSVersion.Platform -eq [PlatformID]::Win32NT) {
        $windowsArguments = @($backendPlan.gcloud.windows_cmd_arguments)
        $windowsOriginArgument = @($windowsArguments | Where-Object { $_ -like '--update-env-vars=*BFF_ALLOWED_ORIGINS=*' })
        Assert-Equal -Actual $windowsOriginArgument.Count -Expected 1 -Message 'Windows execution arguments lost the origin update.'
        Assert-True -Condition ($windowsOriginArgument[0].StartsWith('--update-env-vars=^^^^@^^^^', [StringComparison]::Ordinal)) -Message 'Windows gcloud dictionary delimiter is not escaped as installed help requires.'
        Assert-True -Condition ($backendPlan.gcloud.command.Contains('^^^^@^^^^BFF_ALLOWED_ORIGINS=', [StringComparison]::Ordinal)) -Message 'Human-readable Windows command did not retain safe delimiter escaping.'
        $fakeGcloud = Join-Path $testRoot 'fake-gcloud.cmd'
        [IO.File]::WriteAllText(
            $fakeGcloud,
            "@echo off`r`nsetlocal DisableDelayedExpansion`r`necho %*`r`n",
            [Text.ASCIIEncoding]::new()
        )
        $resolvedFakeGcloud = Resolve-PnlGcloudExecutable -GcloudPath $fakeGcloud
        Assert-Equal -Actual $resolvedFakeGcloud -Expected ([IO.Path]::GetFullPath($fakeGcloud)) -Message 'Explicit gcloud .cmd resolution failed.'
        $propagated = (& $resolvedFakeGcloud $windowsOriginArgument[0] 2>&1 | Out-String).Trim()
        Assert-Equal -Actual $LASTEXITCODE -Expected 0 -Message "Windows command parser split the escaped gcloud dictionary argument. Output=[$propagated]"
        Assert-True -Condition ($propagated.Contains('^@^BFF_ALLOWED_ORIGINS=', [StringComparison]::Ordinal)) -Message 'Windows command parser did not deliver gcloud alternate-delimiter syntax.'
        Assert-True -Condition ($propagated.EndsWith($originPair, [StringComparison]::Ordinal)) -Message 'Windows command parser altered the approved origin pair.'
        $parserCompatibleFakeGcloud = Join-Path $testRoot 'fake-gcloud-580-parser.cmd'
        [IO.File]::WriteAllText(
            $parserCompatibleFakeGcloud,
            "@echo off`r`nsetlocal EnableExtensions DisableDelayedExpansion`r`nset `"seenContainer=`"`r`n:next`r`nif `"%~1`"==`"`" goto pass`r`nif /I `"%~1`"==`"--container=edge`" set `"seenContainer=1`"`r`nif /I `"%~1`"==`"--container=bff`" set `"seenContainer=1`"`r`nif /I `"%~1`"==`"--quiet`" if defined seenContainer exit /b 87`r`nshift`r`ngoto next`r`n:pass`r`necho GCLOUD580_PARSER_COMPATIBLE`r`nexit /b 0`r`n",
            [Text.ASCIIEncoding]::new()
        )
        $resolvedParserCompatibleFakeGcloud = Resolve-PnlGcloudExecutable -GcloudPath $parserCompatibleFakeGcloud
        $parserOutput = (& $resolvedParserCompatibleFakeGcloud @windowsArguments 2>&1 | Out-String).Trim()
        Assert-Equal -Actual $LASTEXITCODE -Expected 0 -Message "Windows fake gcloud rejected candidate service flags after the first container. Output=[$parserOutput]"
        Assert-True -Condition ($parserOutput.Contains('GCLOUD580_PARSER_COMPATIBLE', [StringComparison]::Ordinal)) -Message 'Windows fake gcloud did not complete the gcloud 580 parser-compatible candidate path.'
    }
    Assert-True -Condition (-not (($backendArguments -join ' ').Contains('services replace', [StringComparison]::OrdinalIgnoreCase))) -Message 'Candidate command used unsafe services replace.'
    Assert-Equal -Actual $backendPlan.gcloud.executable_resolved -Expected ([IO.Path]::GetFullPath($mustNotRunGcloud)) -Message 'Dry-run did not record the explicitly resolved gcloud executable.'
    Assert-True -Condition (-not (Test-Path -LiteralPath $gcloudInvocationMarker)) -Message 'Dry-run invoked the resolved gcloud executable.'
    Write-Output 'REVISION_A_DRY_RUN=PASS traffic=0 cloud_mutation=NONE'

    Assert-Throws -Action {
        & (Join-Path $PSScriptRoot 'staging-release.ps1') `
            -Operation CANDIDATE -ProjectId $project -ProjectNumber $projectNumber -Region $region -Service $service `
            -Stage BACKEND_FIRST -GitHead $head -ApprovedOrigins $originPair `
            -SupabaseUrl $supabaseUrl -WorkerControllerUrl $controllerUrl `
            -FrozenEdgeImage $frozenEdge -RuntimeImage $runtimeA `
            -PreReleaseStatePath $preReleaseState -CapturedServiceJsonPath $baselineMismatchPath `
            -CapturedActiveRevisionJsonPath $baselineMismatchActiveRevisionPath `
            -RevisionSuffix $backendIdentity.revision_suffix -CandidateTag $backendIdentity.candidate_tag `
            -GcloudPath $mustNotRunGcloud -OutputDirectory (Join-Path $testRoot 'backend-baseline-mismatch')
    } -Message 'Revision A candidate accepted a live active revision different from its persisted rollback baseline.'

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
        -ValidatedRevisionAEdgeImage $frozenEdge `
        -ValidatedRevisionARuntimeImage $runtimeA `
        -CapturedServiceJsonPath $revisionBPreflightPath `
        -CapturedActiveRevisionJsonPath $revisionBActiveRevisionPath `
        -RevisionSuffix $frontendIdentity.revision_suffix `
        -CandidateTag $frontendIdentity.candidate_tag `
        -GcloudPath (Join-Path $testRoot 'must-not-run-gcloud.cmd') `
        -OutputDirectory $finalOutput | Out-Null
    $finalPlan = Get-Content -Raw -LiteralPath (Join-Path $finalOutput 'candidate-final-frontend.json') | ConvertFrom-Json
    Assert-Equal -Actual $finalPlan.runtime_image -Expected $runtimeA -Message 'Final candidate runtime changed.'
    Assert-Equal -Actual $finalPlan.validated_revision_a -Expected $backendIdentity.revision_name -Message 'Final candidate did not preserve the existing same-HEAD Revision A fallback.'
    Assert-Equal -Actual $finalPlan.validated_revision_a_runtime_image -Expected $runtimeA -Message 'Final candidate lost the validated Revision A runtime.'
    Assert-Equal -Actual $finalPlan.validated_revision_a_edge_image -Expected $frozenEdge -Message 'Final candidate lost the validated Revision A edge.'
    Assert-Equal -Actual $finalPlan.revision_a_edge_lineage -Expected 'validated' -Message 'Final candidate did not report validated edge lineage.'
    Assert-Equal -Actual $finalPlan.service_preflight.evaluated -Expected $true -Message 'Offline Revision B preflight was not evaluated.'
    Assert-Equal -Actual $finalPlan.service_preflight.result.active_revision -Expected $backendIdentity.revision_name -Message 'Revision B preflight did not require active Revision A.'
    Assert-Equal -Actual $finalPlan.rollback_target -Expected $backendIdentity.revision_name -Message 'Final candidate same-HEAD rollback target changed.'
    Assert-Equal -Actual $finalPlan.revision_a_runtime_authority.resolution -Expected 'DIRECT_MANIFEST' -Message 'Direct Revision A runtime authority was not recorded.'
    Assert-True -Condition (@($finalPlan.gcloud.arguments) -contains "--image=$finalEdge") -Message 'Final candidate omitted final edge digest.'
    Write-Output 'REVISION_B_DRY_RUN=PASS traffic=0 runtime_lineage=PASS edge_lineage=PASS cloud_mutation=NONE'

    $explicitFinalOutput = Join-Path $testRoot 'final-explicit-revision-a'
    $explicitFinalPlan = Invoke-TestRevisionBCandidate `
        -CandidateGitHead $revisionBHead `
        -ExplicitRevisionA $explicitBackendIdentity.revision_name `
        -ServiceJsonPath $explicitRevisionAServicePath `
        -ActiveRevisionJsonPath $explicitRevisionAActiveRevisionPath `
        -GcloudPath $mustNotRunGcloud `
        -OutputDirectory $explicitFinalOutput
    Assert-Equal -Actual $explicitFinalPlan.source_commit -Expected $revisionBHead -Message 'Explicit Revision A changed the Revision B source identity.'
    Assert-Equal -Actual $explicitFinalPlan.revision_name -Expected $explicitFrontendIdentity.revision_name -Message 'Explicit Revision A changed the deterministic Revision B name.'
    Assert-Equal -Actual $explicitFinalPlan.validated_revision_a -Expected $explicitBackendIdentity.revision_name -Message 'Final candidate lost the explicit validated Revision A.'
    Assert-Equal -Actual $explicitFinalPlan.service_preflight.result.contract_valid -Expected $true -Message 'Explicit validated Revision A did not retain the service preservation contract.'
    Assert-Equal -Actual $explicitFinalPlan.service_preflight.result.active_revision -Expected $explicitBackendIdentity.revision_name -Message 'Explicit validated Revision A was not required to be the active revision.'
    Assert-Equal -Actual $explicitFinalPlan.service_preflight.result.active_revision_ready -Expected $true -Message 'Explicit validated Revision A did not prove Ready=True.'
    Assert-Equal -Actual $explicitFinalPlan.service_preflight.result.traffic_percent -Expected ([long]100) -Message 'Explicit validated Revision A did not prove 100-percent traffic.'
    Assert-Equal -Actual $explicitFinalPlan.service_preflight.result.observed_edge_image -Expected $frozenEdge -Message 'Explicit validated Revision A did not retain frozen-edge lineage.'
    Assert-Equal -Actual $explicitFinalPlan.revision_a_runtime_authority.resolution -Expected 'DIRECT_MANIFEST' -Message 'Explicit validated Revision A did not retain runtime lineage authority.'
    Assert-Equal -Actual $explicitFinalPlan.rollback_target -Expected $explicitBackendIdentity.revision_name -Message 'Revision B rollback target did not use the explicit validated Revision A.'

    Assert-Throws -Action {
        Invoke-TestRevisionBCandidate `
            -CandidateGitHead $revisionBHead `
            -ExplicitRevisionA $explicitBackendIdentity.revision_name `
            -ServiceJsonPath $explicitRevisionAServicePath `
            -ActiveRevisionJsonPath $revisionBActiveRevisionPath `
            -GcloudPath $mustNotRunGcloud `
            -OutputDirectory (Join-Path $testRoot 'reject-explicit-a-does-not-exist')
    } -Message 'Revision B accepted an explicit Revision A that could not be resolved by the exact active-revision evidence.'
    Assert-Throws -Action {
        Invoke-TestRevisionBCandidate `
            -CandidateGitHead $revisionBHead `
            -ExplicitRevisionA $explicitBackendIdentity.revision_name `
            -ServiceJsonPath $explicitRevisionANotActiveServicePath `
            -ActiveRevisionJsonPath $revisionBActiveRevisionPath `
            -GcloudPath $mustNotRunGcloud `
            -OutputDirectory (Join-Path $testRoot 'reject-explicit-a-not-active')
    } -Message 'Revision B accepted an explicit Revision A that was not the sole 100-percent active revision.'
    foreach ($wrongRevisionA in @(
        $explicitFrontendIdentity.revision_name,
        "wrong-service-pnlbe-$validatedRevisionAHead"
    )) {
        Assert-Throws -Action {
            Invoke-TestRevisionBCandidate `
                -CandidateGitHead $revisionBHead `
                -ExplicitRevisionA $wrongRevisionA `
                -ServiceJsonPath $explicitRevisionAServicePath `
                -ActiveRevisionJsonPath $explicitRevisionAActiveRevisionPath `
                -GcloudPath $mustNotRunGcloud `
                -OutputDirectory (Join-Path $testRoot ('reject-explicit-a-shape-' + [Guid]::NewGuid().ToString('N')))
        } -Message "Revision B accepted an explicit Revision A with the wrong service or revision type: $wrongRevisionA"
    }
    foreach ($lineageMismatch in @(
        @('edge', $explicitRevisionAEdgeMismatchPath),
        @('runtime', $explicitRevisionARuntimeMismatchPath)
    )) {
        Assert-Throws -Action {
            Invoke-TestRevisionBCandidate `
                -CandidateGitHead $revisionBHead `
                -ExplicitRevisionA $explicitBackendIdentity.revision_name `
                -ServiceJsonPath $explicitRevisionAServicePath `
                -ActiveRevisionJsonPath $lineageMismatch[1] `
                -GcloudPath $mustNotRunGcloud `
                -OutputDirectory (Join-Path $testRoot "reject-explicit-a-$($lineageMismatch[0])-lineage")
        } -Message "Revision B accepted an explicit Revision A with mismatched $($lineageMismatch[0]) lineage."
    }
    Assert-True -Condition (-not (Test-Path -LiteralPath $gcloudInvocationMarker)) -Message 'Explicit Revision A focused tests attempted a Cloud mutation.'
    Write-Output 'REVISION_B_EXPLICIT_A_DRY_RUN=PASS traffic=0 runtime_lineage=PASS edge_lineage=PASS cloud_mutation=NONE'

    $runtimeIndexPath = Join-Path $testRoot 'runtime-index.json'
    [IO.File]::WriteAllText($runtimeIndexPath, $runtimeIndexJson, [Text.UTF8Encoding]::new($false))
    $revisionBOciActiveRevisionPath = Join-Path $testRoot 'revision-b-oci-active-revision.json'
    [IO.File]::WriteAllText(
        $revisionBOciActiveRevisionPath,
        ((New-TestActiveRevisionDescription `
            -Revision $backendIdentity.revision_name `
            -ResolvedEdgeImage $frozenEdge `
            -ResolvedRuntimeImage $runtimeChild) | ConvertTo-Json -Depth 100),
        [Text.UTF8Encoding]::new($false)
    )
    $ociFinalOutput = Join-Path $testRoot 'final-oci-index'
    & (Join-Path $PSScriptRoot 'staging-release.ps1') `
        -Operation CANDIDATE -ProjectId $project -ProjectNumber $projectNumber -Region $region -Service $service `
        -Stage FINAL_FRONTEND -GitHead $head -ApprovedOrigins $originPair `
        -SupabaseUrl $supabaseUrl -WorkerControllerUrl $controllerUrl `
        -FinalEdgeImage $finalEdge -RuntimeImage $runtimeIndex `
        -ValidatedRevisionAEdgeImage $frozenEdge -ValidatedRevisionARuntimeImage $runtimeIndex `
        -CapturedServiceJsonPath $revisionBPreflightPath `
        -CapturedActiveRevisionJsonPath $revisionBOciActiveRevisionPath `
        -RuntimeManifestJsonPath $runtimeIndexPath `
        -RevisionSuffix $frontendIdentity.revision_suffix -CandidateTag $frontendIdentity.candidate_tag `
        -GcloudPath (Join-Path $testRoot 'must-not-run-gcloud.cmd') `
        -OutputDirectory $ociFinalOutput | Out-Null
    $ociFinalPlan = Get-Content -Raw -LiteralPath (Join-Path $ociFinalOutput 'candidate-final-frontend.json') | ConvertFrom-Json
    Assert-Equal -Actual $ociFinalPlan.revision_a_runtime_authority.requested_runtime_image -Expected $runtimeIndex -Message 'OCI authority lost the requested immutable index.'
    Assert-Equal -Actual $ociFinalPlan.revision_a_runtime_authority.resolved_runtime_image -Expected $runtimeChild -Message 'OCI authority lost the resolved linux/amd64 child.'
    Assert-Equal -Actual $ociFinalPlan.revision_a_runtime_authority.platform -Expected 'linux/amd64' -Message 'OCI authority lost the resolved platform.'
    Assert-Equal -Actual $ociFinalPlan.revision_a_runtime_authority.same_repository -Expected $true -Message 'OCI authority did not retain same-repository proof.'
    Assert-Equal -Actual $ociFinalPlan.revision_a_runtime_authority.parent_child_confirmed -Expected $true -Message 'OCI authority did not retain parent-child proof.'

    Assert-Throws -Action {
        & (Join-Path $PSScriptRoot 'staging-release.ps1') `
            -Operation CANDIDATE -ProjectId $project -ProjectNumber $projectNumber -Region $region -Service $service `
            -Stage FINAL_FRONTEND -GitHead $head -ApprovedOrigins $originPair `
            -SupabaseUrl $supabaseUrl -WorkerControllerUrl $controllerUrl `
            -FinalEdgeImage $finalEdge -RuntimeImage $runtimeA `
            -ValidatedRevisionAEdgeImage $frozenEdge -ValidatedRevisionARuntimeImage $runtimeA `
            -CapturedServiceJsonPath $revisionBMutableTemplatePath `
            -CapturedActiveRevisionJsonPath $revisionBActiveRevisionPath `
            -RevisionSuffix $frontendIdentity.revision_suffix -CandidateTag $frontendIdentity.candidate_tag `
            -OutputDirectory (Join-Path $testRoot 'reject-b-mutable-service-template')
    } -Message 'Revision B preflight inherited the legacy mutable service-template exception.'

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
            -ValidatedRevisionAEdgeImage $frozenEdge `
            -ValidatedRevisionARuntimeImage $runtimeA `
            -RevisionSuffix $frontendIdentity.revision_suffix `
            -CandidateTag $frontendIdentity.candidate_tag `
            -OutputDirectory (Join-Path $testRoot 'wrong-runtime')
    } -Message 'Revision B accepted a runtime digest different from Revision A.'

    Assert-Throws -Action {
        & (Join-Path $PSScriptRoot 'staging-release.ps1') `
            -Operation CANDIDATE -ProjectId $project -ProjectNumber $projectNumber -Region $region -Service $service `
            -Stage FINAL_FRONTEND -GitHead $head -ApprovedOrigins $originPair `
            -SupabaseUrl $supabaseUrl -WorkerControllerUrl $controllerUrl `
            -FinalEdgeImage $finalEdge -RuntimeImage $runtimeA `
            -ValidatedRevisionARuntimeImage $runtimeA `
            -RevisionSuffix $frontendIdentity.revision_suffix -CandidateTag $frontendIdentity.candidate_tag `
            -OutputDirectory (Join-Path $testRoot 'missing-a-edge')
    } -Message 'Revision B accepted a missing validated Revision A edge digest.'

    Assert-Throws -Action {
        & (Join-Path $PSScriptRoot 'staging-release.ps1') `
            -Operation CANDIDATE -ProjectId $project -ProjectNumber $projectNumber -Region $region -Service $service `
            -Stage FINAL_FRONTEND -GitHead $head -ApprovedOrigins $originPair `
            -SupabaseUrl $supabaseUrl -WorkerControllerUrl $controllerUrl `
            -FinalEdgeImage $finalEdge -RuntimeImage $runtimeA `
            -ValidatedRevisionAEdgeImage $frozenEdge `
            -RevisionSuffix $frontendIdentity.revision_suffix -CandidateTag $frontendIdentity.candidate_tag `
            -OutputDirectory (Join-Path $testRoot 'missing-a-runtime')
    } -Message 'Revision B accepted a missing validated Revision A runtime digest.'

    Assert-Throws -Action {
        & (Join-Path $PSScriptRoot 'staging-release.ps1') `
            -Operation CANDIDATE -ProjectId $project -ProjectNumber $projectNumber -Region $region -Service $service `
            -Stage FINAL_FRONTEND -GitHead $head -ApprovedOrigins $originPair `
            -SupabaseUrl $supabaseUrl -WorkerControllerUrl $controllerUrl `
            -FinalEdgeImage $frozenEdge -RuntimeImage $runtimeA `
            -ValidatedRevisionAEdgeImage $frozenEdge -ValidatedRevisionARuntimeImage $runtimeA `
            -RevisionSuffix $frontendIdentity.revision_suffix -CandidateTag $frontendIdentity.candidate_tag `
            -OutputDirectory (Join-Path $testRoot 'same-edge')
    } -Message 'Revision B accepted a final edge equal to the validated Revision A edge.'

    $lineageFixtures = @(
        @(
            'live-a-edge-mismatch',
            (New-TestServiceDescription -ObservedEdgeImage $frozenEdge -ObservedRuntimeImage $runtimeA -ActiveRevision $backendIdentity.revision_name),
            (New-TestActiveRevisionDescription -Revision $backendIdentity.revision_name -ResolvedEdgeImage $finalEdge -ResolvedRuntimeImage $runtimeA)
        ),
        @(
            'live-a-runtime-mismatch',
            (New-TestServiceDescription -ObservedEdgeImage $frozenEdge -ObservedRuntimeImage $runtimeA -ActiveRevision $backendIdentity.revision_name),
            (New-TestActiveRevisionDescription -Revision $backendIdentity.revision_name -ResolvedEdgeImage $frozenEdge -ResolvedRuntimeImage $runtimeB)
        ),
        @(
            'active-a-mismatch',
            (New-TestServiceDescription -ObservedEdgeImage $frozenEdge -ObservedRuntimeImage $runtimeA -ActiveRevision 'pnl-web-unexpected-active'),
            (New-TestActiveRevisionDescription -Revision 'pnl-web-unexpected-active' -ResolvedEdgeImage $frozenEdge -ResolvedRuntimeImage $runtimeA)
        )
    )
    foreach ($lineageFixture in $lineageFixtures) {
        $lineagePath = Join-Path $testRoot "$($lineageFixture[0]).json"
        $lineageActiveRevisionPath = Join-Path $testRoot "$($lineageFixture[0])-active-revision.json"
        [IO.File]::WriteAllText(
            $lineagePath,
            ($lineageFixture[1] | ConvertTo-Json -Depth 100),
            [Text.UTF8Encoding]::new($false)
        )
        [IO.File]::WriteAllText(
            $lineageActiveRevisionPath,
            ($lineageFixture[2] | ConvertTo-Json -Depth 100),
            [Text.UTF8Encoding]::new($false)
        )
        Assert-Throws -Action {
            & (Join-Path $PSScriptRoot 'staging-release.ps1') `
                -Operation CANDIDATE -ProjectId $project -ProjectNumber $projectNumber -Region $region -Service $service `
                -Stage FINAL_FRONTEND -GitHead $head -ApprovedOrigins $originPair `
                -SupabaseUrl $supabaseUrl -WorkerControllerUrl $controllerUrl `
                -FinalEdgeImage $finalEdge -RuntimeImage $runtimeA `
                -ValidatedRevisionAEdgeImage $frozenEdge -ValidatedRevisionARuntimeImage $runtimeA `
                -CapturedServiceJsonPath $lineagePath `
                -CapturedActiveRevisionJsonPath $lineageActiveRevisionPath `
                -RevisionSuffix $frontendIdentity.revision_suffix -CandidateTag $frontendIdentity.candidate_tag `
                -OutputDirectory (Join-Path $testRoot "reject-$($lineageFixture[0])")
        } -Message "Revision B accepted invalid live Revision A lineage: $($lineageFixture[0])"
    }

    $sameRuntimeAPath = Join-Path $testRoot 'revision-a-same-runtime.json'
    $sameRuntimeAActiveRevisionPath = Join-Path $testRoot 'revision-a-same-runtime-active-revision.json'
    [IO.File]::WriteAllText(
        $sameRuntimeAPath,
        ((New-TestServiceDescription `
            -ObservedEdgeImage $frozenEdge `
            -ObservedRuntimeImage $runtimeA `
            -ActiveRevision 'pnl-web-pre-release-fixture') | ConvertTo-Json -Depth 100),
        [Text.UTF8Encoding]::new($false)
    )
    [IO.File]::WriteAllText(
        $sameRuntimeAActiveRevisionPath,
        ((New-TestActiveRevisionDescription `
            -Revision 'pnl-web-pre-release-fixture' `
            -ResolvedEdgeImage $frozenEdge `
            -ResolvedRuntimeImage $runtimeA) | ConvertTo-Json -Depth 100),
        [Text.UTF8Encoding]::new($false)
    )
    Assert-Throws -Action {
        & (Join-Path $PSScriptRoot 'staging-release.ps1') `
            -Operation CANDIDATE -ProjectId $project -ProjectNumber $projectNumber -Region $region -Service $service `
            -Stage BACKEND_FIRST -GitHead $head -ApprovedOrigins $originPair `
            -SupabaseUrl $supabaseUrl -WorkerControllerUrl $controllerUrl `
            -FrozenEdgeImage $frozenEdge -RuntimeImage $runtimeA `
            -PreReleaseStatePath $preReleaseState `
            -CapturedServiceJsonPath $sameRuntimeAPath `
            -CapturedActiveRevisionJsonPath $sameRuntimeAActiveRevisionPath `
            -RevisionSuffix $backendIdentity.revision_suffix -CandidateTag $backendIdentity.candidate_tag `
            -OutputDirectory (Join-Path $testRoot 'reject-a-same-runtime')
    } -Message 'Revision A accepted a runtime digest equal to the active runtime.'

    $badTopology = New-TestServiceDescription `
        -ObservedEdgeImage $frozenEdge `
        -ObservedRuntimeImage $runtimeB `
        -ActiveRevision 'pnl-web-pre-release-fixture'
    $badTopology.spec.template.spec.containers = @($badTopology.spec.template.spec.containers | Where-Object { $_.name -eq 'edge' })
    $badTopologyPath = Join-Path $testRoot 'bad-topology.json'
    [IO.File]::WriteAllText($badTopologyPath, ($badTopology | ConvertTo-Json -Depth 100), [Text.UTF8Encoding]::new($false))
    Assert-Throws -Action {
        & (Join-Path $PSScriptRoot 'staging-release.ps1') `
            -Operation CANDIDATE -ProjectId $project -ProjectNumber $projectNumber -Region $region -Service $service `
            -Stage BACKEND_FIRST -GitHead $head -ApprovedOrigins $originPair `
            -SupabaseUrl $supabaseUrl -WorkerControllerUrl $controllerUrl `
            -FrozenEdgeImage $frozenEdge -RuntimeImage $runtimeA `
            -PreReleaseStatePath $preReleaseState `
            -CapturedServiceJsonPath $badTopologyPath `
            -CapturedActiveRevisionJsonPath $revisionAActiveRevisionPath `
            -RevisionSuffix $backendIdentity.revision_suffix -CandidateTag $backendIdentity.candidate_tag `
            -OutputDirectory (Join-Path $testRoot 'reject-topology')
    } -Message 'Service preflight accepted a missing BFF container.'

    $badStartupDelay = New-TestServiceDescription `
        -ObservedEdgeImage $finalEdge `
        -ObservedRuntimeImage $mutableRuntimeTag `
        -ActiveRevision 'pnl-web-pre-release-fixture'
    $badStartupDelay.spec.template.spec.containers[0].startupProbe | Add-Member -NotePropertyName initialDelaySeconds -NotePropertyValue 1
    $badStartupDelayPath = Join-Path $testRoot 'bad-startup-delay.json'
    [IO.File]::WriteAllText($badStartupDelayPath, ($badStartupDelay | ConvertTo-Json -Depth 100), [Text.UTF8Encoding]::new($false))
    Assert-Throws -Action {
        & (Join-Path $PSScriptRoot 'staging-release.ps1') `
            -Operation CANDIDATE -ProjectId $project -ProjectNumber $projectNumber -Region $region -Service $service `
            -Stage BACKEND_FIRST -GitHead $head -ApprovedOrigins $originPair `
            -SupabaseUrl $supabaseUrl -WorkerControllerUrl $controllerUrl `
            -FrozenEdgeImage $frozenEdge -RuntimeImage $runtimeA `
            -PreReleaseStatePath $preReleaseState `
            -CapturedServiceJsonPath $badStartupDelayPath `
            -CapturedActiveRevisionJsonPath $revisionAActiveRevisionPath `
            -RevisionSuffix $backendIdentity.revision_suffix -CandidateTag $backendIdentity.candidate_tag `
            -OutputDirectory (Join-Path $testRoot 'reject-startup-delay')
    } -Message 'Service preflight accepted a nonzero startup-probe initial delay.'

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
    Assert-Throws -Action {
        & (Join-Path $PSScriptRoot 'staging-release.ps1') `
            -Operation CAPTURE_ACTIVE -ProjectId $project -ProjectNumber $projectNumber -Region $region -Service $service `
            -GitHead $head -PreReleaseStatePath (Join-Path $PSScriptRoot 'unsafe-state.json') `
            -OutputDirectory (Join-Path $testRoot 'capture-unsafe-path')
    } -Message 'Active-revision capture accepted state output outside deploy/gcp/rendered.'
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
    Assert-Equal -Actual $capturePlan.resolved_active_revision_capture_required -Expected $true -Message 'Capture plan did not require exact active-revision resolution.'
    Assert-True -Condition ($capturePlan.resolved_active_revision_capture_operation -match 'run revisions describe') -Message 'Capture plan omitted the read-only exact revision describe.'

    $captureExecuteOutput = Join-Path $testRoot 'capture-execute-read-only'
    $readOnlyGcloud = Join-Path $testRoot 'read-only-gcloud.ps1'
    $unexpectedMutationMarker = Join-Path $testRoot 'unexpected-cloud-mutation.txt'
    [IO.File]::WriteAllText(
        $readOnlyGcloud,
        @'
if ($args.Count -ge 3 -and $args[0] -ceq 'run' -and $args[1] -ceq 'services' -and $args[2] -ceq 'describe') {
    [IO.File]::ReadAllText($env:PNL_CAPTURE_TEST_SERVICE_JSON)
    exit 0
}
if ($args.Count -ge 3 -and $args[0] -ceq 'run' -and $args[1] -ceq 'revisions' -and $args[2] -ceq 'describe') {
    [IO.File]::ReadAllText($env:PNL_CAPTURE_TEST_REVISION_JSON)
    exit 0
}
[IO.File]::WriteAllText($env:PNL_CAPTURE_TEST_MUTATION_MARKER, ($args -join ' '))
exit 97
'@,
        [Text.UTF8Encoding]::new($false)
    )
    $env:PNL_CAPTURE_TEST_SERVICE_JSON = $revisionAPreflightPath
    $env:PNL_CAPTURE_TEST_REVISION_JSON = $revisionAActiveRevisionPath
    $env:PNL_CAPTURE_TEST_MUTATION_MARKER = $unexpectedMutationMarker
    try {
        & (Join-Path $PSScriptRoot 'staging-release.ps1') `
            -Operation CAPTURE_ACTIVE `
            -ProjectId $project `
            -ProjectNumber $projectNumber `
            -Region $region `
            -Service $service `
            -GitHead $head `
            -GcloudPath $readOnlyGcloud `
            -OutputDirectory $captureExecuteOutput `
            -Execute | Out-Null
    }
    finally {
        Remove-Item Env:\PNL_CAPTURE_TEST_SERVICE_JSON -ErrorAction SilentlyContinue
        Remove-Item Env:\PNL_CAPTURE_TEST_REVISION_JSON -ErrorAction SilentlyContinue
        Remove-Item Env:\PNL_CAPTURE_TEST_MUTATION_MARKER -ErrorAction SilentlyContinue
    }
    $capturedBaseline = Get-Content -Raw -LiteralPath (Join-Path $captureExecuteOutput 'captured-active-resolved-baseline.json') | ConvertFrom-Json
    Assert-Equal -Actual $capturedBaseline.active_revision -Expected 'pnl-web-pre-release-fixture' -Message 'Read-only active capture selected the wrong revision.'
    Assert-Equal -Actual $capturedBaseline.ready -Expected $true -Message 'Read-only active capture did not prove Ready=True.'
    Assert-Equal -Actual $capturedBaseline.resolved_edge_image -Expected $frozenEdge -Message 'Read-only active capture did not persist the resolved edge digest.'
    Assert-Equal -Actual $capturedBaseline.resolved_runtime_image -Expected $runtimeB -Message 'Read-only active capture did not persist the resolved runtime digest.'
    Assert-Equal -Actual $capturedBaseline.cloud_mutation -Expected $false -Message 'Read-only active capture reported a Cloud mutation.'
    Assert-True -Condition (Test-Path -LiteralPath (Join-Path $captureExecuteOutput 'captured-active-service.json')) -Message 'Read-only active capture omitted the service evidence JSON.'
    Assert-True -Condition (Test-Path -LiteralPath (Join-Path $captureExecuteOutput 'captured-active-revision.json')) -Message 'Read-only active capture omitted the revision evidence JSON.'
    Assert-True -Condition (-not (Test-Path -LiteralPath $unexpectedMutationMarker)) -Message 'Read-only active capture attempted a non-describe gcloud command.'

    $promotionOutput = Join-Path $testRoot 'promotion'
    Assert-Throws -Action {
        & (Join-Path $PSScriptRoot 'staging-release.ps1') `
            -Operation PROMOTE -ProjectId $project -ProjectNumber $projectNumber -Region $region -Service $service `
            -Stage BACKEND_FIRST -GitHead $head -Revision $backendIdentity.revision_name `
            -OutputDirectory (Join-Path $testRoot 'promotion-without-smoke')
    } -Message 'Promotion command generation accepted a missing SmokeGate.'
    Assert-Throws -Action {
        & (Join-Path $PSScriptRoot 'staging-release.ps1') `
            -Operation PROMOTE -ProjectId $project -ProjectNumber $projectNumber -Region $region -Service $service `
            -Stage BACKEND_FIRST -GitHead $head -Revision $backendIdentity.revision_name `
            -SmokeGate failed -OutputDirectory (Join-Path $testRoot 'promotion-failed-smoke')
    } -Message 'Promotion command generation accepted a failed SmokeGate.'
    foreach ($ambiguousTarget in @('latest', 'newest', 'current', 'candidate')) {
        Assert-Throws -Action {
            & (Join-Path $PSScriptRoot 'staging-release.ps1') `
                -Operation PROMOTE -ProjectId $project -ProjectNumber $projectNumber -Region $region -Service $service `
                -Stage BACKEND_FIRST -GitHead $head -Revision $ambiguousTarget -SmokeGate passed `
                -OutputDirectory (Join-Path $testRoot "promotion-$ambiguousTarget")
        } -Message "Promotion command generation accepted ambiguous target: $ambiguousTarget"
    }
    Assert-Throws -Action {
        & (Join-Path $PSScriptRoot 'staging-release.ps1') `
            -Operation PROMOTE -ProjectId $project -ProjectNumber $projectNumber -Region $region -Service $service `
            -Stage BACKEND_FIRST -GitHead $head -Revision $backendIdentity.revision_name -SmokeGate passed `
            -CapturedServiceJsonPath $revisionAPreflightPath -GcloudPath $mustNotRunGcloud `
            -OutputDirectory (Join-Path $testRoot 'promotion-a-missing-baseline')
    } -Message 'Revision A promotion command generation accepted a missing persisted rollback baseline.'
    & (Join-Path $PSScriptRoot 'staging-release.ps1') `
        -Operation PROMOTE `
        -ProjectId $project `
        -ProjectNumber $projectNumber `
        -Region $region `
        -Service $service `
        -Stage BACKEND_FIRST `
        -GitHead $head `
        -Revision $backendIdentity.revision_name `
        -SmokeGate passed `
        -PreReleaseStatePath $preReleaseState `
        -CapturedServiceJsonPath $revisionAPreflightPath `
        -GcloudPath (Join-Path $testRoot 'must-not-run-gcloud.cmd') `
        -OutputDirectory $promotionOutput | Out-Null
    $promotionPlan = Get-Content -Raw -LiteralPath (Join-Path $promotionOutput 'promote-backend-first.json') | ConvertFrom-Json
    Assert-Equal -Actual $promotionPlan.capture_current_100_percent_revision_before_promotion -Expected $true -Message 'Promotion did not require dynamic active-revision capture.'
    Assert-Equal -Actual $promotionPlan.smoke_gate -Expected 'passed' -Message 'Promotion plan lost the passed smoke gate.'
    Assert-Equal -Actual $promotionPlan.promotion_time_active_recapture.evaluated -Expected $true -Message 'Offline promotion-time recapture was not evaluated.'
    Assert-Equal -Actual $promotionPlan.promotion_time_active_recapture.active_revision -Expected 'pnl-web-pre-release-fixture' -Message 'Revision A promotion recapture used the wrong active revision.'
    Assert-Equal -Actual $promotionPlan.rollback_target -Expected 'pnl-web-pre-release-fixture' -Message 'Revision A promotion lost the explicit pre-release rollback target.'
    Assert-Equal -Actual $promotionPlan.rollback_baseline.active_revision -Expected 'pnl-web-pre-release-fixture' -Message 'Revision A promotion did not validate the release-bound rollback baseline.'
    Assert-True -Condition (@($promotionPlan.gcloud.arguments) -contains "--to-revisions=$($backendIdentity.revision_name)=100") -Message 'Promotion did not target the explicit Revision A name.'
    Assert-True -Condition (-not (@($promotionPlan.gcloud.arguments) -contains '--to-latest')) -Message 'Promotion used latest revision selection.'
    Assert-Throws -Action {
        & (Join-Path $PSScriptRoot 'staging-release.ps1') `
            -Operation PROMOTE -ProjectId $project -ProjectNumber $projectNumber -Region $region -Service $service `
            -Stage BACKEND_FIRST -GitHead $head -Revision $backendIdentity.revision_name -SmokeGate passed `
            -PreReleaseStatePath $preReleaseState -CapturedServiceJsonPath $baselineMismatchPath `
            -GcloudPath $mustNotRunGcloud -OutputDirectory (Join-Path $testRoot 'promotion-a-baseline-mismatch')
    } -Message 'Revision A promotion accepted a recaptured active revision different from the persisted rollback baseline.'

    $promotionBOutput = Join-Path $testRoot 'promotion-b'
    & (Join-Path $PSScriptRoot 'staging-release.ps1') `
        -Operation PROMOTE -ProjectId $project -ProjectNumber $projectNumber -Region $region -Service $service `
        -Stage FINAL_FRONTEND -GitHead $head -Revision $frontendIdentity.revision_name `
        -SmokeGate passed -CapturedServiceJsonPath $revisionBPreflightPath `
        -GcloudPath (Join-Path $testRoot 'must-not-run-gcloud.cmd') -OutputDirectory $promotionBOutput | Out-Null
    $promotionBPlan = Get-Content -Raw -LiteralPath (Join-Path $promotionBOutput 'promote-final-frontend.json') | ConvertFrom-Json
    Assert-Equal -Actual $promotionBPlan.promotion_time_active_recapture.active_revision -Expected $backendIdentity.revision_name -Message 'Revision B promotion did not require active Revision A.'
    Assert-Equal -Actual $promotionBPlan.validated_revision_a -Expected $backendIdentity.revision_name -Message 'Revision B promotion did not preserve same-HEAD Revision A fallback.'
    Assert-Equal -Actual $promotionBPlan.rollback_target -Expected $backendIdentity.revision_name -Message 'Same-HEAD Revision B promotion lost its Revision A rollback target.'
    Assert-Equal -Actual $promotionBPlan.rollback_operation_type -Expected 'REVISION_B_TO_A' -Message 'Revision B promotion lost the B-to-A rollback meaning.'

    $explicitPromotionOutput = Join-Path $testRoot 'promotion-b-explicit-a'
    $explicitPromotionPlan = Invoke-TestRevisionBPromotion `
        -CandidateGitHead $revisionBHead `
        -ExplicitRevisionA $explicitBackendIdentity.revision_name `
        -ServiceJsonPath $explicitRevisionAServicePath `
        -ActiveRevisionJsonPath $explicitRevisionAActiveRevisionPath `
        -GcloudPath $mustNotRunGcloud `
        -OutputDirectory $explicitPromotionOutput
    Assert-Equal -Actual $explicitPromotionPlan.target_revision -Expected $explicitFrontendIdentity.revision_name -Message 'Explicit Revision A promotion changed the existing Revision B identity.'
    Assert-Equal -Actual $explicitPromotionPlan.validated_revision_a -Expected $explicitBackendIdentity.revision_name -Message 'Explicit Revision A promotion lost its authoritative Revision A.'
    Assert-Equal -Actual $explicitPromotionPlan.rollback_target -Expected $explicitBackendIdentity.revision_name -Message 'Explicit Revision A promotion lost its rollback target.'
    Assert-Equal -Actual $explicitPromotionPlan.promotion_time_active_recapture.active_revision -Expected $explicitBackendIdentity.revision_name -Message 'Explicit Revision A promotion recaptured the wrong active revision.'
    Assert-Equal -Actual $explicitPromotionPlan.promotion_revision_a_validation.evaluated -Expected $true -Message 'Explicit Revision A promotion did not validate Ready and lineage evidence.'
    Assert-Equal -Actual $explicitPromotionPlan.promotion_revision_a_validation.result.active_revision_ready -Expected $true -Message 'Explicit Revision A promotion did not prove Ready=True.'
    Assert-Equal -Actual $explicitPromotionPlan.promotion_revision_a_validation.result.observed_edge_image -Expected $frozenEdge -Message 'Explicit Revision A promotion did not preserve edge lineage evidence.'
    Assert-Equal -Actual $explicitPromotionPlan.promotion_revision_a_validation.result.observed_runtime_image -Expected $runtimeA -Message 'Explicit Revision A promotion did not preserve runtime lineage evidence.'
    Assert-True -Condition (@($explicitPromotionPlan.gcloud.arguments) -contains "--to-revisions=$($explicitFrontendIdentity.revision_name)=100") -Message 'Explicit Revision A promotion did not target the exact existing Revision B.'

    Assert-Throws -Action {
        Invoke-TestRevisionBPromotion `
            -CandidateGitHead $revisionBHead `
            -ExplicitRevisionA $explicitBackendIdentity.revision_name `
            -ServiceJsonPath $explicitRevisionAServicePath `
            -ActiveRevisionJsonPath (Join-Path $testRoot 'nonexistent-explicit-a.json') `
            -GcloudPath $mustNotRunGcloud `
            -OutputDirectory (Join-Path $testRoot 'promotion-b-explicit-a-nonexistent')
    } -Message 'Revision B promotion accepted a nonexistent explicit Revision A.'
    Assert-Throws -Action {
        Invoke-TestRevisionBPromotion `
            -CandidateGitHead $revisionBHead `
            -ExplicitRevisionA $explicitBackendIdentity.revision_name `
            -ServiceJsonPath $explicitRevisionANotActiveServicePath `
            -ActiveRevisionJsonPath $explicitRevisionAActiveRevisionPath `
            -GcloudPath $mustNotRunGcloud `
            -OutputDirectory (Join-Path $testRoot 'promotion-b-explicit-a-not-active')
    } -Message 'Revision B promotion accepted an explicit Revision A that was not active at 100 percent.'
    foreach ($lineageMismatch in @(
        @('edge', $explicitRevisionAInvalidEdgePath),
        @('runtime', $explicitRevisionAInvalidRuntimePath)
    )) {
        Assert-Throws -Action {
            Invoke-TestRevisionBPromotion `
                -CandidateGitHead $revisionBHead `
                -ExplicitRevisionA $explicitBackendIdentity.revision_name `
                -ServiceJsonPath $explicitRevisionAServicePath `
                -ActiveRevisionJsonPath $lineageMismatch[1] `
                -GcloudPath $mustNotRunGcloud `
                -OutputDirectory (Join-Path $testRoot "promotion-b-explicit-a-$($lineageMismatch[0])-mismatch")
        } -Message "Revision B promotion accepted invalid explicit Revision A $($lineageMismatch[0]) lineage."
    }
    Write-Output 'REVISION_B_PROMOTION_EXPLICIT_A_DRY_RUN=PASS cloud_mutation=NONE'

    Assert-Throws -Action {
        & (Join-Path $PSScriptRoot 'staging-release.ps1') `
            -Operation PROMOTE -ProjectId $project -ProjectNumber $projectNumber -Region $region -Service $service `
            -Stage FINAL_FRONTEND -GitHead $head -Revision $frontendIdentity.revision_name `
            -SmokeGate passed -CapturedServiceJsonPath $revisionAPreflightPath `
            -OutputDirectory (Join-Path $testRoot 'promotion-b-without-active-a')
    } -Message 'Revision B promotion accepted a recaptured active revision other than Revision A.'

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
    Assert-Equal -Actual $rollbackPlan.rollback_kind -Expected 'REVISION_B_TO_A' -Message 'Revision B rollback lost its explicit operation type.'
    Assert-Throws -Action {
        & (Join-Path $PSScriptRoot 'staging-release.ps1') `
            -Operation ROLLBACK -ProjectId $project -ProjectNumber $projectNumber -Region $region -Service $service `
            -RollbackKind GENERIC -GitHead $head -OutputDirectory (Join-Path $testRoot 'generic-rollback')
    } -Message 'A generic rollback kind was accepted.'
    Assert-Throws -Action {
        & (Join-Path $PSScriptRoot 'staging-release.ps1') `
            -Operation ROLLBACK -ProjectId $project -ProjectNumber $projectNumber -Region $region -Service $service `
            -RollbackKind REVISION_A_TO_PRE_RELEASE -GitHead $head `
            -PreReleaseStatePath (Join-Path $rollbackOutput 'missing-state.json') `
            -OutputDirectory $rollbackOutput
    } -Message 'Revision A rollback accepted missing persisted capture metadata.'

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
    Assert-True -Condition (@($preReleasePlan.gcloud.arguments) -contains '--to-revisions=pnl-web-pre-release-fixture=100') -Message 'Pre-release rollback did not use captured state.'
    Assert-Equal -Actual $preReleasePlan.rollback_kind -Expected 'REVISION_A_TO_PRE_RELEASE' -Message 'Revision A rollback lost its explicit operation type.'

    $invalidState = Get-Content -Raw -LiteralPath $preReleaseState | ConvertFrom-Json
    $invalidState.valid = $false
    $invalidStatePath = Join-Path $rollbackOutput 'invalid-captured-pre-release.json'
    [IO.File]::WriteAllText($invalidStatePath, ($invalidState | ConvertTo-Json -Depth 10), [Text.UTF8Encoding]::new($false))
    Assert-Throws -Action {
        & (Join-Path $PSScriptRoot 'staging-release.ps1') `
            -Operation ROLLBACK -ProjectId $project -ProjectNumber $projectNumber -Region $region -Service $service `
            -RollbackKind REVISION_A_TO_PRE_RELEASE -GitHead $head -PreReleaseStatePath $invalidStatePath `
            -OutputDirectory $rollbackOutput
    } -Message 'Revision A rollback accepted capture metadata marked invalid.'

    Assert-Throws -Action {
        & (Join-Path $PSScriptRoot 'staging-release.ps1') `
            -Operation ROLLBACK -ProjectId $project -ProjectNumber $projectNumber -Region $region -Service $service `
            -RollbackKind GOLDEN -GitHead $head -OutputDirectory $rollbackOutput
    } -Message 'Golden incident fallback command generation succeeded without incident approval.'
    & (Join-Path $PSScriptRoot 'staging-release.ps1') `
        -Operation ROLLBACK -ProjectId $project -ProjectNumber $projectNumber -Region $region -Service $service `
        -RollbackKind GOLDEN -GitHead $head `
        -IncidentApproval APPROVE_GOLDEN_INCIDENT_ROLLBACK `
        -GcloudPath (Join-Path $testRoot 'must-not-run-gcloud.cmd') -OutputDirectory $rollbackOutput | Out-Null
    $goldenPlan = Get-Content -Raw -LiteralPath (Join-Path $rollbackOutput 'rollback-golden.json') | ConvertFrom-Json
    Assert-Equal -Actual $goldenPlan.target_revision -Expected 'pnl-web-golden-1e478b6' -Message 'Golden rollback target changed.'
    Assert-Equal -Actual $goldenPlan.incident_approval_required -Expected $true -Message 'Golden rollback lost incident approval gate.'
    Assert-True -Condition (-not (Test-Path -LiteralPath $gcloudInvocationMarker)) -Message 'An offline capture, promotion, or rollback dry-run invoked gcloud.'
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
