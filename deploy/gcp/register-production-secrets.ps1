[CmdletBinding()]
param(
    [Parameter(Mandatory)] [string] $ProjectId,
    [Parameter(Mandatory)] [string] $ProjectNumber,
    [Parameter(Mandatory)] [string] $Configuration,
    [string] $GcloudPath = "$env:LOCALAPPDATA\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd"
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

& (Join-Path $PSScriptRoot 'assert-production-target.ps1') `
    -ProjectId $ProjectId `
    -ProjectNumber $ProjectNumber `
    -Configuration $Configuration `
    -GcloudPath $GcloudPath | Out-Null

function Test-SecurePrefix {
    param(
        [Parameter(Mandatory)] [Security.SecureString] $Value,
        [Parameter(Mandatory)] [string] $Prefix
    )
    if ($Value.Length -lt $Prefix.Length) { return $false }
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Value)
    try {
        for ($index = 0; $index -lt $Prefix.Length; $index++) {
            if ([char][Runtime.InteropServices.Marshal]::ReadInt16($pointer, $index * 2) -ne $Prefix[$index]) {
                return $false
            }
        }
        return $true
    }
    finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
    }
}

function Test-SecureEqual {
    param(
        [Parameter(Mandatory)] [Security.SecureString] $Left,
        [Parameter(Mandatory)] [Security.SecureString] $Right
    )
    if ($Left.Length -ne $Right.Length) { return $false }
    $leftPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Left)
    $rightPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Right)
    try {
        $difference = 0
        for ($index = 0; $index -lt $Left.Length; $index++) {
            $difference = $difference -bor (
                [Runtime.InteropServices.Marshal]::ReadInt16($leftPointer, $index * 2) -bxor
                [Runtime.InteropServices.Marshal]::ReadInt16($rightPointer, $index * 2)
            )
        }
        return $difference -eq 0
    }
    finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($leftPointer)
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($rightPointer)
    }
}

function New-RandomSecureString {
    param([Parameter(Mandatory)] [int] $ByteCount)
    $bytes = [byte[]]::new($ByteCount)
    $generator = [Security.Cryptography.RandomNumberGenerator]::Create()
    $encoded = $null
    try {
        $generator.GetBytes($bytes)
        $encoded = [Convert]::ToBase64String($bytes)
        $secure = [Security.SecureString]::new()
        foreach ($character in $encoded.ToCharArray()) { $secure.AppendChar($character) }
        $secure.MakeReadOnly()
        return $secure
    }
    finally {
        $encoded = $null
        [Array]::Clear($bytes, 0, $bytes.Length)
        $generator.Dispose()
    }
}

function Assert-EmptySecret {
    param([Parameter(Mandatory)] [string] $Name)
    & $GcloudPath secrets describe $Name `
        --configuration=$Configuration `
        --project=$ProjectId `
        --format='value(name)' | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Secret container $Name does not exist." }
    $versions = @(& $GcloudPath secrets versions list $Name `
        --configuration=$Configuration `
        --project=$ProjectId `
        --filter='state=ENABLED' `
        --format='value(name)')
    if ($LASTEXITCODE -ne 0) { throw "Could not inspect versions for $Name." }
    if (@($versions | Where-Object { $_ }).Count -ne 0) {
        throw "Refusing to add a second enabled version to $Name during bootstrap."
    }
}

function Add-SecretVersion {
    param(
        [Parameter(Mandatory)] [string] $Name,
        [Parameter(Mandatory)] [Security.SecureString] $Value
    )
    $startInfo = [Diagnostics.ProcessStartInfo]::new()
    $startInfo.FileName = $env:ComSpec
    $escapedGcloud = $GcloudPath.Replace('"', '""')
    $startInfo.Arguments = "/d /s /c `"`"$escapedGcloud`" secrets versions add $Name --data-file=- --configuration=$Configuration --project=$ProjectId --quiet`""
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.RedirectStandardInput = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $process = [Diagnostics.Process]::new()
    $process.StartInfo = $startInfo
    $pointer = [IntPtr]::Zero
    try {
        if (-not $process.Start()) { throw 'Failed to start gcloud.' }
        $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Value)
        for ($index = 0; $index -lt $Value.Length; $index++) {
            $process.StandardInput.Write([char][Runtime.InteropServices.Marshal]::ReadInt16($pointer, $index * 2))
        }
        $process.StandardInput.Close()
        $null = $process.StandardOutput.ReadToEnd()
        $stderr = $process.StandardError.ReadToEnd()
        $process.WaitForExit()
        if ($process.ExitCode -ne 0) {
            throw "gcloud failed while registering $Name (exit $($process.ExitCode)). $stderr"
        }
        Write-Output "${Name}: version registered"
    }
    finally {
        if ($pointer -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }
        $process.Dispose()
    }
}

$names = @(
    'pnl-supabase-secret-key',
    'pnl-viewer-code',
    'pnl-admin-code',
    'pnl-actor-namespace-secret',
    'pnl-csrf-secret'
)
foreach ($name in $names) { Assert-EmptySecret $name }

Write-Output "Target verified: $ProjectId ($ProjectNumber). Enter values only in no-echo prompts."
$supabaseSecret = Read-Host 'NEW Production Supabase server secret' -AsSecureString
if ($supabaseSecret.Length -lt 32 -or -not (Test-SecurePrefix $supabaseSecret 'sb_secret_')) {
    throw 'The Supabase value does not satisfy the server-secret contract.'
}
$viewerCode = Read-Host 'Production Viewer access code (minimum 12 characters)' -AsSecureString
$viewerCodeConfirm = Read-Host 'Confirm Production Viewer access code' -AsSecureString
if ($viewerCode.Length -lt 12 -or -not (Test-SecureEqual $viewerCode $viewerCodeConfirm)) {
    throw 'Viewer access code validation failed.'
}
$adminCode = Read-Host 'Production Admin access code (minimum 12 characters)' -AsSecureString
$adminCodeConfirm = Read-Host 'Confirm Production Admin access code' -AsSecureString
if ($adminCode.Length -lt 12 -or -not (Test-SecureEqual $adminCode $adminCodeConfirm)) {
    throw 'Admin access code validation failed.'
}
if (Test-SecureEqual $viewerCode $adminCode) { throw 'Viewer and Admin codes must differ.' }

$actorSecret = New-RandomSecureString 48
$csrfSecret = New-RandomSecureString 48
try {
    Add-SecretVersion 'pnl-supabase-secret-key' $supabaseSecret
    Add-SecretVersion 'pnl-viewer-code' $viewerCode
    Add-SecretVersion 'pnl-admin-code' $adminCode
    Add-SecretVersion 'pnl-actor-namespace-secret' $actorSecret
    Add-SecretVersion 'pnl-csrf-secret' $csrfSecret
    Write-Output 'All five Production Secret Manager versions are registered.'
}
finally {
    foreach ($secret in @(
        $supabaseSecret, $viewerCode, $viewerCodeConfirm,
        $adminCode, $adminCodeConfirm, $actorSecret, $csrfSecret
    )) {
        if ($null -ne $secret) { $secret.Dispose() }
    }
}
