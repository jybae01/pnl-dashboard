# Phase 2 Streamlit–Supabase Auth Bridge design

Status: proposed implementation target; no live credentials or deployment in this change.

## Decision

Use option A for the current small internal deployment, with a capability-separated
server adapter. Keep the existing `VIEWER_CODE` / `ADMIN_CODE` login and
`st.session_state.role`. Do not create a Supabase login screen or a Supabase Auth
session for each Streamlit user.

The Supabase secret stays only in the Streamlit server process. Browser code,
browser storage, query parameters, widget state, logs, result payloads, and
`st.session_state` must never contain it. The adapter must expose only the
operations allowed to each application role; it must not expose a generic
`table()`, SQL, RPC, or Edge invocation method to UI code.

For this bridge, Streamlit calls Storage/Data API/RPCs from Python on the server.
It does not call the current JWT-protected `pnl-gateway` as if it were a user;
minting a synthetic Supabase user JWT solely to satisfy that Edge route would
turn option A into option B. The existing Edge route remains available for a
future Supabase-Auth client and must still contain no worker executor.

## Alternatives

| Option | Security boundary | Operations burden | Decision |
|---|---|---|---|
| A. Trusted Streamlit backend | Existing access-code role is authoritative; the server calls narrowly allowed Supabase operations | Lowest; one existing login UX and one server secret | Recommended now, with the controls below |
| B. Internal Supabase service user/session/JWT | Supabase Auth token and `app_metadata` become authoritative | Highest; account bootstrap, token refresh/revocation, rotation, and failure recovery without user login UX | Defer until per-user identity/audit or SSO is required |
| C. Dedicated Edge BFF with bridge credentials | Edge validates a separate Streamlit-to-Edge credential, then uses Supabase privileges | Medium; another secret/protocol, Edge deployment, rotation, replay protection, and monitoring | Consider when Streamlit must not hold a Supabase secret or multiple trusted apps are added |

Option B must never authorize from `user_metadata`; if adopted later, only
server-controlled `app_metadata` may carry an admin role. Token claims are stale
until refresh, so revocation and role-change behavior would also need an explicit
contract.

## Trust boundaries

1. The browser sends only the access code over the existing Streamlit connection.
2. Streamlit compares the configured code on the server and stores only
   `viewer` or `admin` in the user session. It never stores the submitted code.
3. Every privileged UI action calls `require_role("admin")` again at the action
   boundary. Hiding a button is not authorization.
4. `ViewerSupabaseGateway` can only list/read results satisfying all of:
   `calculation_jobs.status = 'completed'`, `calculation_results.is_published`,
   and a published model/mapping provenance relationship.
5. `AdminSupabaseGateway` can only invoke named upload, publish, and default-change
   operations. Lifecycle changes use the narrow database RPCs; direct broad
   table mutation is forbidden.
6. The independent worker retains its own server-only runtime configuration and
   continues to claim/heartbeat/complete/fail jobs through the Phase 2 pgmq/RPC
   boundary. No worker execution route is added back to the Edge gateway.

## Required implementation shape

Create a server-only composition root that reads `SUPABASE_URL` and a server
secret from process environment or Streamlit secrets. Pass already-constructed
capability objects to presentation code:

```text
Streamlit session role
  viewer -> ViewerSupabaseGateway -> published completed result reads only
  admin  -> ViewerSupabaseGateway + AdminSupabaseGateway
                                 -> initialize upload / publish / set default
Worker process -> WorkerSupabaseGateway -> pgmq claim / heartbeat / complete / fail
```

The Admin upload method performs one server-side transaction-shaped workflow:
resolve the published mapping provenance, generate model/job IDs and canonical
paths, invoke `initialize_calculation_upload`, upload the received workbook bytes
from the Streamlit server to the private bucket, then invoke
`mark_calculation_upload_completed`. It returns only model/job status to UI code;
no Storage credential or signed upload token is sent to the browser.

The Viewer read method returns a shaped DTO rather than raw table rows. It must
apply the completed + published + provenance predicates in the repository query
and validate the persisted payload schema again before rendering.

The default composition remains the local repository unless an explicit backend
setting selects Supabase and all required server configuration is present. A
partial or invalid Supabase configuration must fail closed; it must not silently
mix local writes with remote reads.

Use separate interfaces and constructors for viewer, admin, and worker
capabilities even if the first implementation reads the same server secret. This
prevents a Viewer callback from obtaining an admin method and makes later secret
separation possible without changing the UI contract.

## Authorization matrix

| Operation | Viewer | Admin | Worker |
|---|---:|---:|---:|
| Read published completed result | Allow | Allow | Not required |
| Read draft/unpublished/failed/processing result | Deny | Deny by default | Only when required by a narrow worker RPC |
| Initialize signed upload | Deny | Allow | Deny |
| Publish model/result/mapping | Deny | Allow | Deny |
| Change default | Deny | Allow | Deny |
| Claim/heartbeat/complete/fail queue job | Deny | Deny | Allow |
| Direct update/delete/truncate of protected tables | Deny | Deny | Deny |

## Mandatory controls

- Compare access codes with a constant-time comparison and rate-limit repeated
  failures at the application boundary where deployment infrastructure permits.
- Clear role state on logout and define an inactivity/session expiry policy.
- Never log access codes, Supabase secrets, Authorization/apikey headers, signed
  upload URLs, claim tokens, or raw exception request headers.
- Keep the private Storage canonical paths enforced in database triggers. The
  application must not be the sole path validator.
- Preserve published mapping provenance validation and immutable calculation
  result provenance in database functions/triggers.
- Preserve append-only `audit_logs` and the Phase 1 revocation of broad
  service-role update/delete/truncate privileges.
- Record application role and a server-generated request correlation ID in audit
  metadata. Access codes do not provide individual human identity; do not imply
  otherwise in audit reports.
- Rotate the server secret through deployment configuration, never through the
  repository. A leaked server secret invalidates this bridge's trust boundary.

## Acceptance tests before live E2E

1. A Viewer cannot construct, import, or receive an admin gateway.
2. Direct calls to every admin callback fail when the session role is Viewer,
   including forged widget/callback inputs.
3. Viewer queries omit unpublished, non-completed, failed, and processing rows.
4. Admin upload/publish/default operations succeed only through the named narrow
   methods and RPCs.
5. Browser/network inspection contains no secret, service-role key, signed URL,
   or worker claim token.
6. Local remains the default backend; explicit Supabase selection fails closed
   when configuration is incomplete.
7. Edge contains no claim/complete/fail worker execution endpoint.
8. Database negative tests prove canonical Storage binding, published mapping
   provenance, result provenance immutability, append-only audit logs, and broad
   mutation revocations after all migrations are applied.

## Revisit triggers

Move to B or C when individual employee identity, immediate revocation, SSO,
multiple trusted frontend services, compliance-grade attribution, or separation
of the Streamlit host from the Supabase secret becomes a requirement. Until then,
option A has the smallest failure surface and operating burden for the existing UX.
