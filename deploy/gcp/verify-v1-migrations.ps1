[CmdletBinding()]
param(
    [string] $MigrationDirectory = (Join-Path (Split-Path $PSScriptRoot -Parent | Split-Path -Parent) 'supabase\migrations')
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

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
    $actualHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $file.FullName).Hash.ToLowerInvariant()
    if ($actualHash -ne $expected[$expectedName]) {
        throw "Migration digest mismatch: $expectedName"
    }
    $records += [ordered]@{ order = $index + 1; name = $file.Name; sha256 = $actualHash }
}

[ordered]@{
    status = 'PASS'
    migration_count = $records.Count
    first = $records[0].name
    latest = $records[-1].name
    migrations = $records
} | ConvertTo-Json -Depth 4
