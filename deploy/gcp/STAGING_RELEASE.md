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
- Rendered `BFF_ALLOWED_ORIGINS`: the two values above, in that canonical order
  and separated by one comma with no whitespace

`*`, localhost, HTTP, a third-party origin, a duplicate, a third origin, and an
untrimmed list all fail closed. Either input order for the exact two-origin set
is accepted and normalized to the canonical value above; no other input is.

## Installed CLI capability decision

The locally installed Google Cloud SDK 580.0.0 `gcloud run deploy --help`
exposes `--revision-suffix`, `--tag`, `--no-traffic`, `--container`, `--image`,
`--port`, and `--depends-on`.
Its `--no-traffic` help explicitly states that the deployed revision receives
no traffic. The installed `gcloud run services replace --help` exposes only
`--async`, `--dry-run`, and `--region` for this purpose; it has no explicit
zero-traffic candidate flag. Therefore an established staging `pnl-web`
candidate must use `gcloud run deploy --no-traffic`. Do not substitute
`gcloud run services replace` and do not infer traffic preservation.

The release wrapper resolves the actual executable before help probing or
execution. The installed `gcloud topic escaping` also requires every `^` in an alternate
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

Never use `LATEST`, `latest`, `newest`, `current`, `candidate`, `--to-latest`,
or a most-recent revision query as a promotion or rollback target.

## Deterministic identities and tags

The identity token is the complete 40-character lowercase release HEAD. For
`pnl-web`, the resulting revisions are 54 characters and the tags are 46
characters, within the source-controlled 63-character validation bound.

| Stage | Revision suffix | Full revision | Candidate tag |
| --- | --- | --- | --- |
| Backend-first (Revision A) | `pnlbe-<full-head>` | `pnl-web-pnlbe-<full-head>` | `pnlbe-<full-head>` |
| Final frontend (Revision B) | `pnlfe-<full-head>` | `pnl-web-pnlfe-<full-head>` | `pnlfe-<full-head>` |

The stage token makes Revision A and B identities and tags distinct even when
both are produced from the same commit. A caller-supplied suffix or tag that
does not equal this policy is rejected. No truncated-prefix identity remains.

## Safe command setup

Use exact OCI digest references. Mutable tags are not deploy inputs.

```powershell
$ProjectId = 'pnl-dashboard-staging'
$ProjectNumber = '498160536475'
$Region = 'asia-southeast1'
$Service = 'pnl-web'
$ReleaseHead = '<FULL_40_CHARACTER_LOWERCASE_GIT_HEAD>'
$ApprovedOrigins = 'https://pnl-web-498160536475.asia-southeast1.run.app,https://pnl-web-t4n4rdoznq-as.a.run.app'
$SupabaseUrl = 'https://<STAGING_PROJECT_REF>.supabase.co'
$WorkerControllerUrl = 'https://pnl-worker-controller-498160536475.asia-southeast1.run.app'
$FrozenEdgeImage = '<FROZEN_EDGE_OCI_DIGEST_REFERENCE>'
$RuntimeImageA = '<NEW_RUNTIME_OCI_DIGEST_REFERENCE>'
$FinalEdgeImage = '<FINAL_EDGE_OCI_DIGEST_REFERENCE>'
$ValidatedRevisionAEdgeImage = $FrozenEdgeImage
$ValidatedRevisionARuntimeImage = $RuntimeImageA
$RevisionASuffix = "pnlbe-$ReleaseHead"
$RevisionA = "$Service-$RevisionASuffix"
$RevisionATag = $RevisionASuffix
$RevisionBSuffix = "pnlfe-$ReleaseHead"
$RevisionB = "$Service-$RevisionBSuffix"
$RevisionBTag = $RevisionBSuffix
$PreReleaseState = "deploy/gcp/rendered/staging-release/pre-release-$ReleaseHead.json"

$Target = @{
    ProjectId = $ProjectId
    ProjectNumber = $ProjectNumber
    Region = $Region
    Service = $Service
}
```

All examples first omit `-Execute`. That mode renders and validates manifests,
optionally validates an offline captured service JSON, saves a JSON plan plus a
readable command under ignored `deploy/gcp/rendered/staging-release/`, and
performs zero Cloud calls and zero traffic changes.

## Authoritative release flow

This is the only staging release sequence. Later steps never imply approval for
an earlier Cloud, database, image, or traffic mutation.

### 1. Preflight and verify the full release HEAD

Run `git rev-parse HEAD`, `git branch --show-current`, `git status --short`,
`git diff --check`, the PowerShell release tests, Google Cloud readiness tests,
and the PowerShell parser check. Require the approved branch, clean worktree,
full 40-character HEAD, corrected-template hash, and all release gates. Verify
the installed `gcloud run deploy --help` still exposes every required flag.

Corrected-template and offline dataset-pack readiness evidence belongs to
preflight: require explicit approval of the corrected bytes, bundled-template
PLAN and ACTUAL-through-1/6/12 parser passes, zero metadata mismatches, endpoint
exact-byte proof, packaging proof, and the regenerated 16-workbook dataset
pack. The real staging E2E remains Step 14 after both promotions. Stop on any
mismatch; never reset, stash, clean, substitute a commit, or continue on a
partial preflight.

### 2. Capture the active pre-release revision

First render the read-only command, then under the later release approval add
`-Execute` to perform only `run services describe` and persist its strict
single-100%-revision result:

```powershell
./deploy/gcp/staging-release.ps1 @Target `
  -Operation CAPTURE_ACTIVE `
  -GitHead $ReleaseHead `
  -PreReleaseStatePath $PreReleaseState
```

The capture must identify the exact project, region, service, explicit revision,
integer 100% traffic, release identity, purpose, and validity. Split, tag-only,
missing-revision, malformed-percent, or ambiguous traffic fails closed.

### 3. Validate the rollback baseline

Inspect the captured JSON and generate the `REVISION_A_TO_PRE_RELEASE` rollback
plan without `-Execute`. It must bind to this full HEAD and service, be marked
valid, have purpose `pre-release rollback target`, and target the captured
explicit revision. Do not migrate or build until this dry-run plan passes.

### 4. Apply migrations later under separate approval

Run `./deploy/gcp/verify-v1-migrations.ps1`, compare remote history read-only,
and later apply only the separately approved migration sequence. Migration
application is not performed by this wrapper, is not automatic, and must stop
unless the expected before/after history and local digests match.

### 5. Build and resolve the runtime digest later

Build from the exact release HEAD outside the deploy command, push only under
separate approval, and resolve the approved staging `pnl-runtime` immutable OCI
digest. Preserve it as `$RuntimeImageA`; candidate commands never build or push
images. Stop on registry, project, image-role, architecture, label, or digest
drift.

### 6. Create Revision A at zero traffic

```powershell
./deploy/gcp/staging-release.ps1 @Target `
  -Operation CANDIDATE `
  -Stage BACKEND_FIRST `
  -GitHead $ReleaseHead `
  -PreReleaseStatePath $PreReleaseState `
  -ApprovedOrigins $ApprovedOrigins `
  -SupabaseUrl $SupabaseUrl `
  -WorkerControllerUrl $WorkerControllerUrl `
  -FrozenEdgeImage $FrozenEdgeImage `
  -RuntimeImage $RuntimeImageA `
  -CapturedServiceJsonPath '<OFFLINE_REVISION_A_SERVICE_JSON>' `
  -RevisionSuffix $RevisionASuffix `
  -CandidateTag $RevisionATag
```

Review the manifest and plan. The emitted candidate command contains exactly
two containers, the frozen edge image, the new runtime digest,
`--revision-suffix=$RevisionASuffix`, `--tag=$RevisionATag`, and
`--no-traffic`, with edge `--port=8080` and `--depends-on=bff`. It updates only
the BFF allowed-origin value and source labels;
execute mode first reads and validates the live required service configuration
so malformed traffic, missing containers, secret references, cookie settings,
volumes, limits, concurrency, or timeout block deployment. Candidate generation
also requires the release-bound pre-release rollback baseline and requires the
preflight active revision to match that baseline. The image contract requires
`$FrozenEdgeImage` to equal the current live edge digest and `$RuntimeImageA`
to differ from the current runtime digest. The captured JSON argument is
offline-only; execute mode always recaptures live state itself.

Only after the plan is approved may an operator repeat the same invocation
with:

```text
-Execute -MutationApproval APPROVE_STAGING_CANDIDATE
```

### 7. Smoke Revision A

Invoke the distinct tag URL, not the canonical URL. Verify live/ready, React
shell continuity through the frozen edge, localhost BFF connectivity, runtime
source/digest, database/read model, Admin/Viewer/anonymous authorization,
template endpoint contract, secret-file references, cookie and CSRF behavior,
and UID 10001 volume canaries. Confirm service traffic still assigns 0% to
Revision A before promotion.

Stop on any smoke failure, identity mismatch, origin mismatch, secret exposure,
or nonzero candidate traffic. Do not promote and do not roll traffic as part of
the smoke command.

### 8. Promote Revision A after recapture

Promotion command generation already requires the candidate-specific smoke
gate. It repeats the live capture immediately before traffic mutation and
requires the result to match the persisted pre-release rollback baseline:

```powershell
./deploy/gcp/staging-release.ps1 @Target `
  -Operation PROMOTE `
  -Stage BACKEND_FIRST `
  -GitHead $ReleaseHead `
  -Revision $RevisionA `
  -SmokeGate passed `
  -PreReleaseStatePath $PreReleaseState `
  -CapturedServiceJsonPath '<OFFLINE_REVISION_A_SERVICE_JSON>'
```

After approval, omit the offline JSON input and add
`-Execute -MutationApproval APPROVE_STAGING_PROMOTION`. The only traffic target
is `$RevisionA=100`; no implicit target or automatic rollback is permitted.

### 9. Build and resolve the final edge digest later

Build the edge image from the exact same release HEAD, outside the deploy
command, and resolve its immutable OCI digest as `$FinalEdgeImage`. Do not
rebuild or change `$RuntimeImageA`.

### 10. Validate Revision B edge and runtime lineage

Freeze `$ValidatedRevisionAEdgeImage` from the validated Revision A evidence
and `$ValidatedRevisionARuntimeImage` from its runtime evidence. Recapture the
live service into an offline JSON evidence file. Before Revision B candidate
creation, require all of these simultaneously:

- deterministic Revision A is the sole 100% active revision;
- live Revision A edge equals `$ValidatedRevisionAEdgeImage`;
- live Revision A runtime equals `$ValidatedRevisionARuntimeImage`;
- Revision B runtime equals `$ValidatedRevisionARuntimeImage` exactly; and
- `$FinalEdgeImage` is immutable and differs from the validated Revision A edge.

Any missing value or edge/runtime drift stops the release.

### 11. Create Revision B at zero traffic

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
  -ValidatedRevisionAEdgeImage $ValidatedRevisionAEdgeImage `
  -ValidatedRevisionARuntimeImage $ValidatedRevisionARuntimeImage `
  -CapturedServiceJsonPath '<OFFLINE_VALIDATED_REVISION_A_SERVICE_JSON>' `
  -RevisionSuffix $RevisionBSuffix `
  -CandidateTag $RevisionBTag
```

Review the explicit lineage result and zero-traffic plan, then omit the offline
JSON input and add `-Execute -MutationApproval APPROVE_STAGING_CANDIDATE` only
after approval. Execute mode recaptures live Revision A and repeats every edge,
runtime, active-revision, origin, topology, provenance, and traffic check before
creating Revision B.

### 12. Smoke Revision B

Use Revision B's distinct tag URL. Verify ready/live, React assets and routing,
login/logout, Admin and Viewer boundaries, CSRF, the two approved origins,
template download, core read paths, and browser console/network cleanliness.
Confirm canonical traffic still serves Revision A and Revision B remains 0%.

### 13. Promote Revision B after recapture

```powershell
./deploy/gcp/staging-release.ps1 @Target `
  -Operation PROMOTE `
  -Stage FINAL_FRONTEND `
  -GitHead $ReleaseHead `
  -Revision $RevisionB `
  -SmokeGate passed `
  -CapturedServiceJsonPath '<OFFLINE_VALIDATED_REVISION_A_SERVICE_JSON>'
```

After approval, omit the offline JSON input and add
`-Execute -MutationApproval APPROVE_STAGING_PROMOTION`. The wrapper captures the
current 100% revision immediately before routing `$RevisionB=100` and fails
unless it is deterministic Revision A for the same full HEAD.

### 14. Run real staging E2E

Run the regenerated P&L E2E pack and the full relevant staging regression on
the canonical service. Require all 7 valid parser cases and all 9 invalid
expected-code cases, through-1/6/12, zero denominator, replacement A/B, and
manifest/README evidence.

### 15. Complete Browser QA

Exercise the release checklist in a clean browser session at both approved
service origins. Capture only redacted evidence; never capture access codes,
cookies, tokens, signed URLs, secret values, or source workbook bytes. The user
must explicitly accept the final UI at staging; a technical smoke is not visual
approval.

### 16. Final Audit

Record the full HEAD, Revision A/B names and tags, exact edge/runtime OCI
digests, validated A edge/runtime lineage, captured pre-release revision, 100%
active revision, canonical origin pair, migration proof, real E2E results,
Browser QA, and user approval. Keep unused revisions only for the approved
rollback window. Do not infer production approval.

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
  -GitHead $ReleaseHead `
  -IncidentApproval APPROVE_GOLDEN_INCIDENT_ROLLBACK
```

Even command generation requires the separate incident approval above.
Execution additionally requires `-MutationApproval APPROVE_STAGING_ROLLBACK`.
Golden is never selected automatically and is not a normal rollback target.

## Universal stop conditions

Stop without traffic mutation when any of these occurs:

- template approval, exact-byte authority, or regenerated E2E pack is missing;
- worktree, branch, HEAD, migration history, or image digest differs;
- the installed CLI lacks any required explicit safety flag;
- the origin pair is not exact;
- Revision A/B identity or tags do not match the deterministic policy;
- Revision B runtime is not exactly Revision A's validated runtime reference;
- Revision B live edge/runtime lineage differs from the stored validated A
  digests, or its final edge equals the frozen Revision A edge;
- the rendered or live configuration drops a container, secret reference,
  cookie setting, volume, resource limit, concurrency, or timeout;
- a candidate has nonzero traffic before promotion;
- smoke, E2E, Browser Self-QA, or User Visual QA fails;
- a plan contains a secret payload or a command selects `latest`, `newest`,
  `current`, `candidate`, or another implicit target.
