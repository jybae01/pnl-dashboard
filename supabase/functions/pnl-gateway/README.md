# P&L gateway (Phase 1)

This Edge Function is a control/security gateway only. It does not import an
Excel library and does not run the deterministic Python calculation engine.

Routes:

- `POST /uploads/init`: administrator JWT, atomically creates model/job rows,
  then returns an exact-path signed Storage upload token.
- `GET /jobs/{job_id}`: owner/admin status read.
- `POST /jobs/{job_id}/uploaded`: owner/admin confirms the signed upload; the
  gateway verifies the exact object exists before making the pending job claimable.
- `POST /jobs/claim`: worker token, claims one durable job lease.
- `POST /jobs/{job_id}/heartbeat|complete|fail`: worker token, delegates the
  guarded DB lifecycle RPCs.

Required secrets: `SUPABASE_URL`, `SUPABASE_ANON_KEY`,
`SUPABASE_SERVICE_ROLE_KEY`, `WORKER_GATEWAY_TOKEN`, `ENGINE_VERSION`,
`RESULT_SCHEMA_VERSION`, and a comma-separated `ALLOWED_ORIGINS` allowlist.

The client uploads with Supabase Storage's `uploadToSignedUrl`; it must never
send the workbook bytes to this function.
