[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [string]$ProjectId = "pnl-dashboard-staging",

    [Parameter(Mandatory = $false)]
    [string]$GcloudPath = "$env:LOCALAPPDATA\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Get-SecureStringLength {
    param([Parameter(Mandatory = $true)][Security.SecureString]$Value)
    return $Value.Length
}

function Test-SecureStringPrefix {
    param(
        [Parameter(Mandatory = $true)][Security.SecureString]$Value,
        [Parameter(Mandatory = $true)][string]$Prefix
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

function Test-SecureStringEqual {
    param(
        [Parameter(Mandatory = $true)][Security.SecureString]$Left,
        [Parameter(Mandatory = $true)][Security.SecureString]$Right
    )
    if ($Left.Length -ne $Right.Length) { return $false }
    $leftPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Left)
    $rightPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Right)
    try {
        $different = 0
        for ($index = 0; $index -lt $Left.Length; $index++) {
            $different = $different -bor (
                [Runtime.InteropServices.Marshal]::ReadInt16($leftPointer, $index * 2) -bxor
                [Runtime.InteropServices.Marshal]::ReadInt16($rightPointer, $index * 2)
            )
        }
        return $different -eq 0
    }
    finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($leftPointer)
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($rightPointer)
    }
}

function New-RandomSecureString {
    param([Parameter(Mandatory = $true)][int]$ByteCount)
    $bytes = [byte[]]::new($ByteCount)
    $generator = [Security.Cryptography.RandomNumberGenerator]::Create()
    $encoded = $null
    try {
        $generator.GetBytes($bytes)
        $encoded = [Convert]::ToBase64String($bytes)
        $secure = [Security.SecureString]::new()
        foreach ($character in $encoded.ToCharArray()) {
            $secure.AppendChar($character)
        }
        $secure.MakeReadOnly()
        return $secure
    }
    finally {
        $encoded = $null
        [Array]::Clear($bytes, 0, $bytes.Length)
        $generator.Dispose()
    }
}

function Add-SecretVersion {
    param(
        [Parameter(Mandatory = $true)][string]$SecretName,
        [Parameter(Mandatory = $true)][Security.SecureString]$Value
    )
    $startInfo = [Diagnostics.ProcessStartInfo]::new()
    $startInfo.FileName = $env:ComSpec
    $escapedGcloud = $GcloudPath.Replace('"', '""')
    $startInfo.Arguments = "/d /s /c `"`"$escapedGcloud`" secrets versions add $SecretName --data-file=- --project=$ProjectId --quiet`""
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.RedirectStandardInput = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true

    $process = [Diagnostics.Process]::new()
    $process.StartInfo = $startInfo
    $pointer = [IntPtr]::Zero
    try {
        if (-not $process.Start()) { throw "Failed to start gcloud." }
        $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Value)
        for ($index = 0; $index -lt $Value.Length; $index++) {
            $process.StandardInput.Write([char][Runtime.InteropServices.Marshal]::ReadInt16($pointer, $index * 2))
        }
        $process.StandardInput.Close()
        $stdout = $process.StandardOutput.ReadToEnd()
        $stderr = $process.StandardError.ReadToEnd()
        $process.WaitForExit()
        if ($process.ExitCode -ne 0) {
            throw "gcloud failed while registering $SecretName (exit $($process.ExitCode)). $stderr"
        }
        Write-Host "${SecretName}: version registered"
    }
    finally {
        if ($pointer -ne [IntPtr]::Zero) {
            [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
        }
        $process.Dispose()
    }
}

if (-not (Test-Path -LiteralPath $GcloudPath -PathType Leaf)) {
    throw "gcloud was not found at the expected path."
}

$configuredProject = (& $GcloudPath config get-value project 2>$null).Trim()
if ($configuredProject -ne $ProjectId -or $ProjectId -ne "pnl-dashboard-staging") {
    throw "Refusing to register secrets outside the exact staging project."
}

Write-Host "Target verified: pnl-dashboard-staging"
Write-Host "Enter values only in this local no-echo prompt. Nothing is written to disk."

$supabaseSecret = Read-Host "NEW staging Supabase server secret" -AsSecureString
if ((Get-SecureStringLength $supabaseSecret) -lt 32 -or -not (Test-SecureStringPrefix $supabaseSecret "sb_secret_")) {
    throw "The Supabase value does not satisfy the server-secret contract."
}

$viewerCode = Read-Host "Viewer access code (minimum 12 characters)" -AsSecureString
$viewerCodeConfirm = Read-Host "Confirm Viewer access code" -AsSecureString
if ($viewerCode.Length -lt 12 -or -not (Test-SecureStringEqual $viewerCode $viewerCodeConfirm)) {
    throw "Viewer access code validation failed."
}

$adminCode = Read-Host "Admin access code (minimum 12 characters)" -AsSecureString
$adminCodeConfirm = Read-Host "Confirm Admin access code" -AsSecureString
if ($adminCode.Length -lt 12 -or -not (Test-SecureStringEqual $adminCode $adminCodeConfirm)) {
    throw "Admin access code validation failed."
}
if (Test-SecureStringEqual $viewerCode $adminCode) {
    throw "Viewer and Admin access codes must differ."
}

$actorSecret = New-RandomSecureString 48
$csrfSecret = New-RandomSecureString 48
try {
    Add-SecretVersion "pnl-supabase-secret-key" $supabaseSecret
    Add-SecretVersion "pnl-viewer-code" $viewerCode
    Add-SecretVersion "pnl-admin-code" $adminCode
    Add-SecretVersion "pnl-actor-namespace-secret" $actorSecret
    Add-SecretVersion "pnl-csrf-secret" $csrfSecret
    Write-Host "All five Secret Manager versions are registered. Close this window."
}
finally {
    foreach ($secret in @(
        $supabaseSecret, $viewerCode, $viewerCodeConfirm,
        $adminCode, $adminCodeConfirm, $actorSecret, $csrfSecret
    )) {
        if ($null -ne $secret) { $secret.Dispose() }
    }
}
