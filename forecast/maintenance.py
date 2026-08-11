from __future__ import annotations

import argparse
import json
import os
import uuid
from pathlib import Path
from typing import Any, Mapping

from .persistence.factory import create_repository_bundle
from .temp_artifacts import TempArtifactPolicy


def cleanup(*, root: Path, quota_bytes: int, dry_run: bool, client: Any | None = None) -> dict[str, Any]:
    policy = TempArtifactPolicy(root, quota_bytes)
    report: dict[str, Any] = {"dry_run": dry_run, "temp": policy.sweep(dry_run=dry_run), "recovery": []}
    if client is not None:
        if not dry_run:
            report["auth_state"] = _rows(client.rpc("cleanup_bff_auth_state", {
                "p_retention_seconds": int(os.getenv("BFF_AUTH_RETENTION_SECONDS", "604800")),
            }).execute())
        for queue_name, claim_name, id_name, complete_name in (
            ("get_model_ingestion_recovery_queue", "claim_model_ingestion_cleanup", "ingestion_id", "complete_model_ingestion_cleanup"),
            ("get_forecast_generation_recovery_queue", "claim_forecast_generation_cleanup", "generation_id", "complete_forecast_generation_cleanup"),
        ):
            rows = _rows(client.rpc(queue_name if dry_run else claim_name, {}).execute())
            for row in rows:
                operation_id = str(uuid.UUID(str(row[id_name])))
                model_id = str(uuid.UUID(str(row["model_id"])))
                item = {"queue": queue_name, "operation_id": operation_id, "model_id": model_id,
                        "action": "would_cleanup" if dry_run else "cleanup_confirmed"}
                report["recovery"].append(item)
                if dry_run:
                    continue
                # A committed Model makes deletion unsafe regardless of queue state.
                existing = _rows(client.table("models").select("id").eq("id", model_id).limit(1).execute())
                if existing:
                    item["action"] = "preserved_committed_model"
                    raise RuntimeError(f"recovery claim references committed model {operation_id}")
                source = f"models/{model_id}/source.xlsx"
                bucket = client.storage.from_("pnl-models")
                bucket.remove([source])
                parent, name = source.rsplit("/", 1)
                remaining = bucket.list(parent, {"search": name, "limit": 10}) or []
                if any(str(value.get("name")) == name for value in remaining):
                    raise RuntimeError(f"storage cleanup could not be verified for {operation_id}")
                client.rpc(complete_name, {
                    f"p_{id_name}": operation_id,
                    "p_recovery_token": str(uuid.UUID(str(row["recovery_token"]))),
                }).execute()
                client.rpc("append_bff_audit_event", {
                    "p_event_type": "cleanup_acknowledged",
                    "p_principal_id": "maintenance-v1",
                    "p_role": "admin",
                    "p_session_ref": None,
                    "p_correlation_id": str(uuid.uuid4()),
                    "p_operation_type": "cleanup_recovery",
                    "p_operation_id": operation_id,
                    "p_outcome": "success",
                    "p_error_code": None,
                }).execute()
    return report


def _rows(response: Any) -> list[Mapping[str, Any]]:
    value = response.data if hasattr(response, "data") else response
    if isinstance(value, Mapping):
        value = value.get("data", value)
    if not value:
        return []
    return list(value) if isinstance(value, list) else [value]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m forecast.maintenance")
    sub = parser.add_subparsers(dest="command", required=True)
    command = sub.add_parser("cleanup", help="sweep owned temp and durable recovery queues")
    command.add_argument("--apply", action="store_true", help="perform verified cleanup (default dry-run)")
    command.add_argument("--temp-root", default=os.getenv("BFF_TEMP_ROOT", ""))
    command.add_argument("--quota-bytes", type=int,
                         default=int(os.getenv("BFF_TEMP_QUOTA_BYTES", str(2 * 1024**3))))
    args = parser.parse_args(argv)
    if not args.temp_root:
        parser.error("--temp-root or BFF_TEMP_ROOT is required")
    client = None
    if os.getenv("PNL_REPOSITORY_BACKEND", "local").strip().lower() == "supabase":
        client = create_repository_bundle(Path("data"), backend="supabase").models.client
    result = cleanup(root=Path(args.temp_root), quota_bytes=args.quota_bytes,
                     dry_run=not args.apply, client=client)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
