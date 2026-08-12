# Google Cloud secret contract

Google Secret Manager is the only intended source for production server secrets.
No secret is a Docker build argument, image environment value, React/Vite value,
tracked `.env` value, service-account JSON key, or command-line literal.

| Secret Manager name | Runtime consumer | Mounted file | Application variable |
| --- | --- | --- | --- |
| `pnl-supabase-secret-key` | web, worker, maintenance, worker-controller | `supabase_secret_key` | `SUPABASE_SECRET_KEY_FILE` |
| `pnl-viewer-code` | web only | `viewer_code` | `VIEWER_CODE_FILE` |
| `pnl-admin-code` | web only | `admin_code` | `ADMIN_CODE_FILE` |
| `pnl-actor-namespace-secret` | web only | `actor_namespace_secret` | `BFF_ACTOR_NAMESPACE_SECRET_FILE` |
| `pnl-csrf-secret` | web only | `csrf_secret` | `BFF_CSRF_SECRET_FILE` |

Each secret is mounted under its own directory because a Secret Manager volume
mount owns its mount path. The existing `deploy/python-entrypoint.sh` reads the
file, exports the process-local value, and never prints it. Mounts use `latest`
so a new instance reads the newest version. Rotate by adding a version, deploying
or restarting every consumer, verifying health and login/queue behavior, and
only then disabling the prior version.

The dedicated runtime service accounts receive
`roles/secretmanager.secretAccessor` only on the exact secrets listed above.
The application does not use `GOOGLE_APPLICATION_CREDENTIALS` or service-account
key files. Only the private controller uses the Worker Pools get/update API via
its attached identity and exact custom role. Browser assets receive no Supabase
secret, Google credential, access code, or `_FILE` path.

Secret values must be entered interactively with `--data-file=-` in the approved
provisioning goal. Do not pass values in shell arguments. Do not enable Secret
Manager Data Access logs containing payloads; Secret Manager never returns
secret data in normal Admin Activity logs.
