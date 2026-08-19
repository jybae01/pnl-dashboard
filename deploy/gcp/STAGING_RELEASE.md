# P&L Reporting staging release runbook

This runbook is the source-controlled release path for the existing Cloud Run
service `pnl-web`. It prepares two zero-traffic candidates from one Git HEAD and
keeps candidate creation, promotion, and rollback as separate operator actions.
Nothing in the dry-run path calls Google Cloud. Do not run an `-Execute` example
without the separate release approval for that exact mutation.

The corrected P&L workbook remains candidate-only until the user explicitly
approves it. While that gate is pending, stop before migration, image build,
candidate creation, or traffic work.

## Frozen staging target and origin contract

- Project: `pnl-dashboard-staging` (`498160536475`)
- Region: `asia-southeast1`
- Service: `pnl-web`
- Approved origin 1 (canonical):
  `https://pnl-web-498160536475.asia-southeast1.run.app`
- Approved origin 2 (`status.url`):
  `https://pnl-web-t4n4rdoznq-as.a.run.app`
- Rendered `BFF_ALLOWED_ORIGINS`: the two values above, in that order and
  separated by one comma with no whitespace

`*`, localhost, HTTP, a third-party origin, a duplicate, a third origin, and an
untrimmed list all fail closed. `staging-release-contract.ps1` permits either
approved origin as a single lower-level value, while the staging renderer
requires the exact ordered pair.

## Installed CLI capability decision

The locally installed `gcloud run deploy --help` exposes
`--revision-suffix`, `--tag`, `--no-traffic`, `--container`, and `--image`.
Its `--no-traffic` help explicitly states that the deployed revision receives
no traffic. The installed `gcloud run services replace --help` exposes only
`--async`, `--dry-run`, and `--region` for this purpose; it has no explicit
zero-traffic candidate flag. Therefore an established staging `pnl-web`
candidate must use `gcloud run deploy --no-traffic`. Do not substitute
`gcloud run services replace` and do not infer traffic preservation.

The installed `gcloud topic escaping` also requires every `^` in an alternate
dictionary delimiter to be repeated four times when PowerShell invokes the
installed `gcloud.cmd` wrapper. The release script selects escaping from the
explicit gcloud executable type when it passes the comma-containing
`BFF_ALLOWED_ORIGINS` value. It uses `@` as the alternate delimiter because it
does not occur in either origin and is not a Windows command-pipeline operator;
operators must not hand-rewrite that argument.

Promotion and rollback use the installed, supported command:

```text
gcloud run services update-traffic pnl-web --project=pnl-dashboard-staging --region=asia-southeast1 --to-revisions=<EXPLICIT_REVISION>=100 --quiet
```

Never use `LATEST`, `--to-latest`, or a most-recent revision query as a
promotion target.

## Deterministic identities and tags

The first 12 lowercase hex characters of the full release HEAD are
`<short-head>`.

| Stage | Revision suffix | Full revision | Candidate tag |
| --- | --- | --- | --- |
| Backend-first (Revision A) | `pnlbe-<short-head>` | `pnl-web-pnlbe-<short-head>` | `pnlbe-<short-head>` |
| Final frontend (Revision B) | `pnlfe-<short-head>` | `pnl-web-pnlfe-<short-head>` | `pnlfe-<short-head>` |

The stage token makes Revision A and B identities and tags distinct even when
both are produced from the same commit. A caller-supplied suffix or tag that
does not equal this policy is rejected.

## Safe command setup

Use exact OCI digest references. Mutable tags are not deploy inputs.

```powershell
$ProjectId = 'pnl-dashboard-staging'
$ProjectNumber = '498160536475'
$Region = 'asia-southeast1'
$Service = 'pnl-web'
$ReleaseHead = '<FULL_40_CHARACTER_LOWERCASE_GIT_HEAD>'
$ShortHead = $ReleaseHead.Substring(0, 12)
$ApprovedOrigins = 'https://pnl-web-498160536475.asia-southeast1.run.app,https://pnl-web-t4n4rdoznq-as.a.run.app'
$SupabaseUrl = 'https://<STAGING_PROJECT_REF>.supabase.co'
$WorkerControllerUrl = 'https://pnl-worker-controller-498160536475.asia-southeast1.run.app'
$FrozenEdgeImage = '<FROZEN_EDGE_OCI_DIGEST_REFERENCE>'
$RuntimeImageA = '<NEW_RUNTIME_OCI_DIGEST_REFERENCE>'
$FinalEdgeImage = '<FINAL_EDGE_OCI_DIGEST_REFERENCE>'
$RevisionASuffix = "pnlbe-$ShortHead"
$RevisionA = "$Service-$RevisionASuffix"
$RevisionATag = $RevisionASuffix
$RevisionBSuffix = "pnlfe-$ShortHead"
$RevisionB = "$Service-$RevisionBSuffix"
$RevisionBTag = $RevisionBSuffix

$Target = @{
    ProjectId = $ProjectId
    ProjectNumber = $ProjectNumber
    Region = $Region
    Service = $Service
}
```

All examples first omit `-Execute`. That mode renders and validates manifests,
saves a JSON plan plus a readable command under ignored
`deploy/gcp/rendered/staging-release/`, and performs zero Cloud calls.

## Finalized release flow

### 1. Verify Final Release HEAD

Run `git rev-parse HEAD`, `git branch --show-current`, `git status --short`,
`git diff --check`, and `git worktree list`. Require the approved final HEAD,
branch, and a clean worktree. Stop on any mismatch; never reset, stash, clean,
or substitute a different commit during the release.

### 2. Pass the template and E2E release gate

Require explicit user approval of the corrected template, exact promotion of
the approved bytes, bundled-template PLAN and ACTUAL-through-1/6/12 parser
passes, zero metadata mismatches, endpoint exact-byte proof, packaging proof,
and a regenerated 16-workbook staging E2E dataset pack. Ordinary input-only
population must pass; QA metadata normalization is forbidden.

Stop while template approval is pending, on any byte/hash difference, parser
or registry change, metadata mismatch, endpoint mismatch, or E2E pack failure.

### 3. Migrate staging from 22 to 25 only under migration approval

First run the local read-only verifier and compare remote migration history by
a read-only list/history operation:

```powershell
./deploy/gcp/verify-v1-migrations.ps1
```

Require remote 22/22 before applying exactly migrations 23 through 25 in
lexical order:

1. `202608190001_pnl_reporting_persistence_slice_b.sql`
2. `202608190002_pnl_reporting_viewer_read_slice_c.sql`
3. `202608190003_pnl_reporting_viewer_year_bootstrap.sql`

Migration application is a separately approved release mutation and is not
performed by `staging-release.ps1`. Stop unless the remote state, local
digests, approval, and post-apply 25/25 proof all match.

### 4. Build and resolve the runtime digest

Build from the exact release HEAD outside the deploy command, push only under
separate approval, then resolve the immutable runtime OCI digest. Candidate
commands never build or push an image. Preserve the resulting exact reference
as `$RuntimeImageA`; it is the Revision A evidence and the only allowed runtime
input for Revision B.

Stop if source labels, architecture, repository, image name, or digest proof do
not match the release HEAD.

### 5. Render Backend-first Revision A at zero traffic

```powershell
./deploy/gcp/staging-release.ps1 @Target `
  -Operation CANDIDATE `
  -Stage BACKEND_FIRST `
  -GitHead $ReleaseHead `
  -ApprovedOrigins $ApprovedOrigins `
  -SupabaseUrl $SupabaseUrl `
  -WorkerControllerUrl $WorkerControllerUrl `
  -FrozenEdgeImage $FrozenEdgeImage `
  -RuntimeImage $RuntimeImageA `
  -RevisionSuffix $RevisionASuffix `
  -CandidateTag $RevisionATag
```

Review the manifest and plan. The emitted candidate command contains exactly
two containers, the frozen edge image, the new runtime digest,
`--revision-suffix=$RevisionASuffix`, `--tag=$RevisionATag`, and
`--no-traffic`. It updates only the BFF allowed-origin value and source labels;
execute mode first reads and validates the live required service configuration
so missing containers, secret references, cookie settings, volumes, limits,
concurrency, or timeout block deployment. It also requires
`$FrozenEdgeImage` to equal the current live edge digest.

Only after the plan is approved may an operator repeat the same invocation
with:

```text
-Execute -MutationApproval APPROVE_STAGING_CANDIDATE
```

### 6. Smoke Backend-first Revision A

Invoke the distinct tag URL, not the canonical URL. Verify live/ready, React
shell continuity through the frozen edge, localhost BFF connectivity, runtime
source/digest, database/read model, Admin/Viewer/anonymous authorization,
template endpoint contract, secret-file references, cookie and CSRF behavior,
and UID 10001 volume canaries. Confirm service traffic still assigns 0% to
Revision A before promotion.

Stop on any smoke failure, identity mismatch, origin mismatch, secret exposure,
or nonzero candidate traffic. Do not promote and do not roll traffic as part of
the smoke command.

### 7. Capture the current active revision and promote Revision A

The read-only capture operation resolves the sole revision currently serving
100%; it does not use a historical hardcoded revision:

```powershell
./deploy/gcp/staging-release.ps1 @Target `
  -Operation CAPTURE_ACTIVE `
  -GitHead $ReleaseHead
```

Review its command, then add `-Execute` to perform only the read and save the
rollback state. Promotion also repeats the live capture immediately before its
traffic mutation:

```powershell
./deploy/gcp/staging-release.ps1 @Target `
  -Operation PROMOTE `
  -Stage BACKEND_FIRST `
  -GitHead $ReleaseHead `
  -Revision $RevisionA
```

After approval, add
`-Execute -MutationApproval APPROVE_STAGING_PROMOTION -SmokeGate passed`. The
only traffic target is `$RevisionA=100`; execute mode rejects promotion without
the candidate-specific smoke gate.

### 8. Build and resolve the final edge digest

Build the edge image from the exact same release HEAD, outside the deploy
command, and resolve its immutable OCI digest as `$FinalEdgeImage`. Do not
rebuild or change `$RuntimeImageA`.

### 9. Render Final-frontend Revision B at zero traffic

```powershell
./deploy/gcp/staging-release.ps1 @Target `
  -Operation CANDIDATE `
  -Stage FINAL_FRONTEND `
  -GitHead $ReleaseHead `
  -ApprovedOrigins $ApprovedOrigins `
  -SupabaseUrl $SupabaseUrl `
  -WorkerControllerUrl $WorkerControllerUrl `
  -FinalEdgeImage $FinalEdgeImage `
  -RuntimeImage $RuntimeImageA `
  -ValidatedRevisionARuntimeImage $RuntimeImageA `
  -RevisionSuffix $RevisionBSuffix `
  -CandidateTag $RevisionBTag
```

Any byte difference between `-RuntimeImage` and
`-ValidatedRevisionARuntimeImage` fails. Review the zero-traffic plan, then add
`-Execute -MutationApproval APPROVE_STAGING_CANDIDATE` only after approval.
Execute mode also requires the live service template to retain that same
Revision A runtime reference before Revision B can be created.

### 10. Browser/basic smoke Revision B

Use Revision B's distinct tag URL. Verify ready/live, React assets and routing,
login/logout, Admin and Viewer boundaries, CSRF, the two approved origins,
template download, core read paths, and browser console/network cleanliness.
Confirm canonical traffic still serves Revision A and Revision B remains 0%.

### 11. Promote Revision B

```powershell
./deploy/gcp/staging-release.ps1 @Target `
  -Operation PROMOTE `
  -Stage FINAL_FRONTEND `
  -GitHead $ReleaseHead `
  -Revision $RevisionB
```

After approval, add
`-Execute -MutationApproval APPROVE_STAGING_PROMOTION -SmokeGate passed`. The
wrapper captures the current 100% revision (expected Revision A) immediately
before routing `$RevisionB=100`. It fails if the current active revision is not
the deterministic Revision A for the same HEAD.

### 12. Run staging E2E

Run the regenerated P&L E2E pack and the full relevant staging regression on
the canonical service. Require all 7 valid parser cases and all 9 invalid
expected-code cases, through-1/6/12, zero denominator, replacement A/B, and
manifest/README evidence.

### 13. Run Browser Self-QA

Exercise the release checklist in a clean browser session at both approved
service origins. Capture only redacted evidence; never capture access codes,
cookies, tokens, signed URLs, secret values, or source workbook bytes.

### 14. Obtain User Visual QA

The user must explicitly accept the final UI at staging. A technical smoke is
not visual approval. Stop on any requested correction and restart at the
appropriate zero-traffic candidate stage.

### 15. Freeze

Record the final HEAD, Revision A/B names and tags, exact edge/runtime OCI
digests, captured pre-release revision, 100% active revision, origin pair,
migration 25/25 proof, test results, and user approval. Keep unused revisions
only for the approved rollback window. Do not infer production approval.

## Rollback paths

Rollback is never automatic and is always a separate invocation.

Revision B failure routes 100% to deterministic Revision A:

```powershell
./deploy/gcp/staging-release.ps1 @Target `
  -Operation ROLLBACK `
  -RollbackKind REVISION_B_TO_A `
  -GitHead $ReleaseHead
```

After approval, add `-Execute -MutationApproval APPROVE_STAGING_ROLLBACK`.

Revision A failure reads the dynamically captured pre-release state rather
than hardcoding the former baseline:

```powershell
$PreReleaseState = "deploy/gcp/rendered/staging-release/pre-release-$ShortHead.json"
./deploy/gcp/staging-release.ps1 @Target `
  -Operation ROLLBACK `
  -RollbackKind REVISION_A_TO_PRE_RELEASE `
  -GitHead $ReleaseHead `
  -PreReleaseStatePath $PreReleaseState
```

After approval, add `-Execute -MutationApproval APPROVE_STAGING_ROLLBACK`.

Only a severe incident with explicit incident approval may route to the frozen
golden revision `pnl-web-golden-1e478b6`:

```powershell
./deploy/gcp/staging-release.ps1 @Target `
  -Operation ROLLBACK `
  -RollbackKind GOLDEN `
  -GitHead $ReleaseHead
```

Execution additionally requires both
`-MutationApproval APPROVE_STAGING_ROLLBACK` and
`-IncidentApproval APPROVE_GOLDEN_INCIDENT_ROLLBACK`.

## Universal stop conditions

Stop without traffic mutation when any of these occurs:

- template approval, exact-byte authority, or regenerated E2E pack is missing;
- worktree, branch, HEAD, migration history, or image digest differs;
- the installed CLI lacks any required explicit safety flag;
- the origin pair is not exact;
- Revision A/B identity or tags do not match the deterministic policy;
- Revision B runtime is not exactly Revision A's validated runtime reference;
- the rendered or live configuration drops a container, secret reference,
  cookie setting, volume, resource limit, concurrency, or timeout;
- a candidate has nonzero traffic before promotion;
- smoke, E2E, Browser Self-QA, or User Visual QA fails;
- a plan contains a secret payload or a command selects `LATEST`.
