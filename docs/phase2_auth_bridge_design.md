# Phase 2 Streamlit–Supabase Auth Bridge design

Status: Option A is the V1 implementation target. This change connects no live
credentials and performs no deployment.

## Decision

Keep the existing `VIEWER_CODE` / `ADMIN_CODE` UX and `st.session_state.role`.
The trusted Streamlit server performs authorization and calls narrow Supabase
gateways. Do not add a Supabase login screen or mint a Supabase Auth session/JWT
for each access-code user.

Use a server-only Streamlit bridge secret (`SUPABASE_SECRET_KEY`, preferably a
separate `sb_secret_...` key; legacy `SUPABASE_SERVICE_ROLE_KEY` is a compatibility
fallback). The worker has separate server-only configuration. Neither secret may
enter browser JavaScript, browser storage, query parameters, widget state, logs,
result payloads, or `st.session_state`.

Supabase secret/service-role keys bypass RLS. Viewer/Admin gateway separation is
a code capability boundary, not database credential isolation. A compromise of
the Streamlit process can therefore compromise every capability held by that
process; separate keys mainly improve rotation and auditability.

## Alternatives

| Option | Boundary | Burden | V1 decision |
|---|---|---|---|
| A. Trusted Streamlit backend | Existing access-code role is authoritative; server calls named Supabase operations | Lowest | Selected |
| B. Internal Supabase service user/session/JWT | Supabase Auth token and server-controlled `app_metadata` role are authoritative | Highest: bootstrap, refresh, revocation, rotation, recovery | Deferred until per-user identity/SSO is required |
| C. Dedicated Edge BFF | Edge verifies a distinct Streamlit-to-Edge credential | Medium: another protocol, secret, deployment, replay controls, monitoring | Optional future boundary |

Option B must never authorize from `user_metadata`. If adopted, only
server-controlled `app_metadata` may contain an admin role and token staleness,
revocation, and role changes need explicit contracts.

## Trust and authorization boundary

1. The browser submits only the access code over the existing Streamlit
   connection.
2. Streamlit performs a constant-time server comparison, deletes the
   `forecast_access_code` widget key after both success and failure, reruns, and
   keeps only `viewer` or `admin` in session state.
3. Every privileged callback independently executes `require_role("admin")`.
   Button visibility is not authorization.
4. `ViewerSupabaseGateway` returns shaped DTOs only when all predicates hold:
   job status is `completed`; result is published; result `model_id` equals job
   `model_id`; result mapping version/hash equals published `app_config`.
5. `AdminSupabaseGateway` exposes only named initialize/upload, publish, and
   default-change methods. Direct generic table/SQL/RPC/Edge methods are not
   exposed to presentation code.
6. Worker completion is always unpublished and non-default. A separate
   Admin-only RPC publishes or changes default; `analysis_request.publish` and
   `make_default` never authorize the worker.
7. `WorkerSupabaseGateway` alone claims, heartbeats, completes, or fails pgmq
   jobs. No worker execution endpoint is added back to Edge.

## V1 request flow

```text
Browser
  -> trusted Streamlit server
     viewer -> ViewerSupabaseGateway -> published completed DTOs only
     admin  -> ViewerSupabaseGateway + AdminSupabaseGateway
             -> initialize -> private server upload -> mark uploaded

Independent worker
  -> WorkerSupabaseGateway -> pgmq claim / heartbeat / complete / fail
  -> unchanged deterministic engine
```

The Admin upload is a saga, not a database transaction: initialize metadata,
upload bytes server-side to the canonical private path, then mark the upload
complete. The contract requires idempotent retry, pending-job TTL cleanup, and
orphan-object cleanup. No Storage credential or signed-upload token is returned
to the browser.

The local repository remains the default backend. Supabase activates only with
an explicit backend setting and complete server configuration; partial settings
fail closed and never mix local writes with remote reads.

The current JWT `pnl-gateway` is optional for a future Supabase Auth client. It
is not the V1 browser upload path.

## Authorization matrix

| Operation | Viewer | Admin | Worker |
|---|---:|---:|---:|
| Read published completed result | Allow | Allow | Not required |
| Read unpublished/failed/processing result | Deny | Deny by default | Narrow RPC only |
| Initialize/upload private workbook | Deny | Allow | Deny |
| Publish result / change default | Deny | Allow | Deny |
| Claim/heartbeat/complete/fail queue job | Deny | Deny | Allow |
| Direct update/delete/truncate of protected tables | Deny | Deny | Deny |

## Mandatory controls

- Rate-limit failed access-code attempts where deployment infrastructure permits;
  clear roles on logout and define inactivity expiry.
- Never log access codes, secrets, `Authorization`/`apikey` headers, signed URLs,
  claim tokens, or raw request headers.
- Preserve database-enforced canonical private Storage paths, published mapping
  provenance validation, immutable calculation-result provenance, append-only
  `audit_logs`, and revocation of broad mutation privileges.
- Record application role and a server-generated correlation ID. Access codes do
  not identify an individual human and audit reports must not imply otherwise.
- Rotate secrets through deployment configuration only.
- Viewer presentation/callback code receives no admin capability, and every
  admin method independently rejects Viewer context. Python import separation
  alone is not a security boundary.

## Acceptance tests before live E2E

1. Forged Viewer callbacks fail every Admin operation.
2. Viewer queries omit unpublished, non-completed, failed, mismatched-model, and
   stale-mapping rows.
3. Worker completion cannot publish or set default.
4. Admin mutations use only named narrow RPCs and methods.
5. Browser/network/session inspection exposes no secret, signed URL, or worker
   token.
6. Local remains default; incomplete Supabase configuration fails closed.
7. Edge contains no worker claim/complete/fail route.
8. Post-migration negative tests prove Storage path validation, publication
   provenance, immutable result provenance, append-only audit, and broad
   mutation revocation.

Revisit B or C only when individual identity, immediate revocation, SSO,
multiple trusted frontends, compliance attribution, or secret separation from
the Streamlit host becomes necessary.
