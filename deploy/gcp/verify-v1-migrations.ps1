[CmdletBinding()]
param(
    [string] $MigrationDirectory = (Join-Path (Split-Path $PSScriptRoot -Parent | Split-Path -Parent) 'supabase\migrations')
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Get-Sha256Hex([byte[]] $Bytes) {
    $algorithm = [Security.Cryptography.SHA256]::Create()
    try {
        return ([BitConverter]::ToString($algorithm.ComputeHash($Bytes))).Replace('-', '').ToLowerInvariant()
    }
    finally {
        $algorithm.Dispose()
    }
}

$expected = [ordered]@{
    '202608090001_phase1_foundation.sql' = '45aac013b3c2e307fa17dccb87fbc916f236dd305f15645e5591a334ec9bf71e'
    '202608090002_phase2_queue_worker.sql' = 'bb45733fd10e31265d106f3b05f7039e2a198e63ce2bd07d6850e126be1793dd'
    '202608090003_phase2_publication_boundary.sql' = '1ad8584ddd546aec29b77896e34f8cb7a9230373dd131a004e075856efe1df42'
    '202608090004_phase25_analysis_inputs.sql' = 'e87a5ee48e0c4394227210ef5f5c30b87caff7e48ac1c81dbc90de5c2f30287d'
    '202608090005_bff_foundation.sql' = 'fe8e1e8547a05e558efc45566c131bf23cbb5ac23abfd236315b7b9617452145'
    '202608090006_react_core_vertical_slice.sql' = '24c77a962c5a67fb6facf20588027e6a29b1de197863933bf64e0b52b0d5029b'
    '202608090007_model_ingestion_vertical_slice.sql' = '8be4ee6fc2c48534a924404c6b5e349faa77d99067e153426b866f78349e716a'
    '202608090008_evidence_history_vertical_slice.sql' = '745e915adae66de72e69031f6da07e21b9af278b93eff6aadb1d81c38972ec5b'
    '202608090009_analysis_presentation_vertical_slice.sql' = 'f432b939596a8ccab626b4c27d6618dadabc0c14399f32195402df4d8e76f8a4'
    '202608090010_pnl_dashboard_vertical_slice.sql' = '7d285caffcd260278843ef6fe9b3c2748159980b86a7488608bbed35fb06871e'
    '202608090011_forecast_react_vertical_slice.sql' = '7794ad75649f946c6093a9ca81bbf0bbd797e19c0c734d2da3ac079f31645d15'
    '202608090012_production_hardening_foundation.sql' = '8de11df6626667e387546a065b7eac6fea060f0e9a4eed0273069fb75de50eac'
    '20260811085901_revoke_audit_trigger_rpc_013.sql' = 'b5c3ff5488a2327959bddfe6ec7ebf1fdfeb7ffed85c103c40cf2b6f1a45a948'
    '20260811091516_fix_shared_lockout_null_014.sql' = '09364af9acc169716354c618ddd683c8758dcf36a872d81d7965c3263805cfc7'
    '20260811145917_fix_analysis_month_series_pg17.sql' = '7908f848e6bab52cb6af059fb9597fed9d9661561fc7add35574867181d1f1c2'
    '20260811150705_align_pnl_dashboard_viewer_contract.sql' = '4a5ebd0bdbbdd2c52c628f13cb5d2e392aebe7a7fad4e742b7267dd75078883b'
    '20260811151052_restore_pnl_dashboard_default_contract.sql' = '08a326ddfe66844680e97c7d5507cdb56a78aa45827677f47011563d8fd1ff4a'
    '202608120001_demand_only_worker_lifecycle.sql' = '4f0483e36f2883561410e5e4708c2a5903d7d6e50c5018a066424d4e8087c6cb'
    '20260815023857_persistent_delete_slice3.sql' = '1e5c9237c6a03742fa915b5a5bc8e0c5ed79dec911e73bb1e26a24e17fb14931'
    '20260815050758_persistent_delete_recovery_slice3a.sql' = 'da63aef01016f6a1845fee04005820f9bd8705dcbc4a895048fd9c3455b37632'
    '20260815053855_persistent_delete_status_classification_slice3a.sql' = '8f16ee6a7914669714c5fbae2e46f9a6ccde0059a2e71d4682533e060823d09a'
    '20260815055055_persistent_delete_storage_requirement_slice3a.sql' = '3b93c47c8ccbef65d87b3e71b20cb1d7eb02970db620c27d852f51931abc35e6'
    '202608190001_pnl_reporting_persistence_slice_b.sql' = 'ad124609334dea962c52b8bf46a44dd1e1a9ff9b150d93fec2204c7319eaf9d9'
    '202608190002_pnl_reporting_viewer_read_slice_c.sql' = '1bf546d0619070609540cea0ccf94dff83f3dec39b10a258d83e8092b42dbcbd'
    '202608190003_pnl_reporting_viewer_year_bootstrap.sql' = '5f2345163b66979efe7b8a10b9bac695e360ae9ed3bd2b243bb2530dc94bb4b1'
    '202608210001_forecast_tariff_metadata_finalize_v11.sql' = '07c18cbad778a7dbaabe44ffe4fcfc553230891c78fdbd056a72bd75a87b02af'
}

$files = @(Get-ChildItem -LiteralPath $MigrationDirectory -File -Filter '*.sql' | Sort-Object Name)
if ($files.Count -ne $expected.Count) {
    throw "Expected $($expected.Count) V1 migrations, found $($files.Count)."
}

$records = @()
for ($index = 0; $index -lt $files.Count; $index++) {
    $file = $files[$index]
    $expectedName = @($expected.Keys)[$index]
    if ($file.Name -ne $expectedName) {
        throw "Migration order mismatch at index $index."
    }
    $actualBytes = [IO.File]::ReadAllBytes($file.FullName)
    $actualHash = Get-Sha256Hex $actualBytes
    $text = [Text.Encoding]::UTF8.GetString($actualBytes)
    $normalizedLf = $text.Replace("`r`n", "`n").Replace("`r", "`n")
    $normalizedLfHash = Get-Sha256Hex ([Text.Encoding]::UTF8.GetBytes($normalizedLf))
    $normalizedCrlfHash = Get-Sha256Hex ([Text.Encoding]::UTF8.GetBytes($normalizedLf.Replace("`n", "`r`n")))
    if ($expected[$expectedName] -notin @($actualHash, $normalizedLfHash, $normalizedCrlfHash)) {
        throw "Migration digest mismatch: $expectedName"
    }
    $records += [ordered]@{ order = $index + 1; name = $file.Name; sha256 = $expected[$expectedName] }
}

[ordered]@{
    status = 'PASS'
    migration_count = $records.Count
    first = $records[0].name
    latest = $records[-1].name
    migrations = $records
} | ConvertTo-Json -Depth 4
