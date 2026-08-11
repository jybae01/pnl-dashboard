# React Core Vertical Slice

Baseline: `agent/react-core-vertical-slice` from BFF Foundation `3a8417a3a84e22186d37779d6c63b465f09ad1b9`.

## HTTP choice and boundary

FastAPI was selected because the repository had no HTTP framework and the adapter needs strict request validation, reusable dependency-based capability checks, response cookies, explicit CORS, and in-process HTTP tests. Handlers contain transport policy only and delegate authentication, submission, Job lookup, and Result lookup to `forecast.bff` application services.

Routes:

- `POST /api/session/login`
- `GET /api/session`
- `POST /api/session/logout`
- `GET /api/models` (Admin)
- `POST /api/analyses` (Admin)
- `GET /api/jobs/{job_id}` (Admin)
- `GET /api/admin/results/{result_id}` (Admin preview)
- `GET /api/viewer/results/{result_id}` (strict Viewer/Admin availability)

The browser receives no Supabase client, secret/service-role key, access code, session digest, claim token, queue receipt, or Storage path.

## Session and HTTP security

- The opaque session identifier is stored only in an HttpOnly cookie.
- Production configuration requires `Secure`; SameSite is `strict` by default.
- Authenticated mutations require a readable CSRF cookie plus matching header. The token is HMAC-bound to the HttpOnly session identifier.
- CORS is disabled unless an explicit origin allowlist is supplied; wildcard credentialed CORS is rejected.
- The default login limiter uses `request.client.host` and is process-local for development/test. Production startup rejects it and requires an injected shared limiter. Forwarded headers are not trusted by default.
- `AccessCodeSessionService` remains process-local. Multi-instance production needs shared session storage; restart intentionally invalidates sessions.

Server-only configuration:

| Name | Purpose |
|---|---|
| `PNL_REPOSITORY_BACKEND=supabase` | Explicit durable HTTP backend; secrets never select it |
| `VIEWER_CODE`, `ADMIN_CODE` | Access-code verification |
| `BFF_ACTOR_NAMESPACE_SECRET` | Stable credential-principal idempotency actor |
| `BFF_CSRF_SECRET` | HMAC-bound CSRF token |
| `SUPABASE_URL`, `SUPABASE_SECRET_KEY` (or legacy service role) | Trusted server Supabase client |
| `BFF_ALLOWED_ORIGINS` | Explicit browser origins when cross-origin |
| `BFF_COOKIE_SECURE`, `BFF_COOKIE_SAME_SITE`, `BFF_SESSION_TTL_SECONDS` | Cookie/session policy |

The existing local Streamlit workflow remains the default under `PNL_REPOSITORY_BACKEND=local`. Durable React HTTP analysis fails closed under local selection because the legacy local queue cannot satisfy pinned Base/Comparison provenance without runtime-default fallback.

## React behavior

The verified handoff was incorporated under `frontend/`. `App` verifies the server session before rendering protected routes. Viewer navigation cannot open Admin operations, and the server independently enforces every capability.

`CoreAnalysisView` uses canonical model IDs, contiguous start/end months, and both sales FX values. A UUID idempotency key is created once per logical payload and retained across retry. Polling uses Job state only, has bounded backoff/duration, stops at terminal state, aborts on unmount, and never invents stage/percentage.

Admin completion reads the stored unpublished Result through Admin preview. Viewer reads use strict availability; the frontend clears the previous Result before every fetch and after denial. `LOADING`, `READY`, `EMPTY`, `ERROR`, and `INVALID_PAYLOAD` are distinct.

The legacy fake timer, dummy history, and mock variance service remain only as out-of-scope handoff artifacts; the reachable core route does not execute them. Evidence download is absent until a real delivery contract exists.

## Additive database guard

Migration `202608090006_react_core_vertical_slice.sql` adds a BEFORE INSERT guard for BFF durable jobs. It locks both models in deterministic order and rejects unpublished models or workbook SHA snapshot mismatch. Migrations 001–005 are unchanged.
