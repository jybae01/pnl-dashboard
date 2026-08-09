# Storage path contract

The `pnl-models` bucket is private. The Edge gateway is the preferred upload
entry point and returns a one-time signed upload token for an exact object key.

```text
models/{model_uuid}/source.xlsx
models/{model_uuid}/jobs/{job_uuid}/result.xlsx
```

- User-provided names are metadata only and never become object keys.
- Source uploads are `.xlsx`, at most 50 MiB, and `upsert` is disabled.
- The Edge gateway creates the model/job rows before signing the source path.
- Workers may write only the result path belonging to their claimed job.
- Authenticated reads are limited by the DB row owning the exact path; there is
  no general list/upload policy for clients.

The SQL helper `public.is_valid_pnl_storage_path` is the canonical validator
shared by table constraints and the Storage read policy.
