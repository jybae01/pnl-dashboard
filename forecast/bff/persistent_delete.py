from __future__ import annotations

import uuid
from collections.abc import Sequence as RuntimeSequence
from dataclasses import dataclass
from typing import Any, Mapping, Protocol, Sequence

from .auth import AccessCodeSessionService
from .errors import ApiErrorCode, BffError


MAX_DELETE_BATCH = 100
MODEL_BUCKET = "pnl-models"
_PREPARE_STATUSES = {
    "READY_FOR_STORAGE",
    "CLEANUP_REQUIRED",
    "DELETED",
    "BLOCKED_IN_USE",
    "BLOCKED_NON_TERMINAL",
    "BLOCKED_PROTECTED",
    "NOT_FOUND",
    "NOT_COMMITTED",
    "PREPARE_UNCERTAIN",
    "FAILED",
}


class PersistentDeleteGatewayError(RuntimeError):
    pass


def _is_explicit_storage_not_found(error: Exception) -> bool:
    """Accept an absent retry only when Storage authoritatively reported 404."""
    status = getattr(error, "status", None)
    if status is None:
        response = getattr(error, "response", None)
        status = getattr(response, "status_code", None)
    try:
        return int(status) == 404
    except (TypeError, ValueError):
        return False


def _storage_object_exists(storage: Any, path: str) -> bool:
    parent, name = path.rsplit("/", 1)
    page_size = 100
    offset = 0
    while offset < 1000:
        rows = storage.list(
            parent,
            {"search": name, "limit": page_size, "offset": offset},
        )
        if (
            not isinstance(rows, RuntimeSequence)
            or isinstance(rows, (str, bytes))
            or any(not isinstance(row, Mapping) for row in rows)
            or any(
                not isinstance(row.get("name"), str) or not row.get("name")
                for row in rows
            )
        ):
            raise PersistentDeleteGatewayError(
                "storage cleanup verification returned invalid data"
            )
        if any(row.get("name") == name for row in rows):
            return True
        if len(rows) < page_size:
            return False
        offset += len(rows)
    raise PersistentDeleteGatewayError(
        "storage cleanup verification exceeded pagination limit"
    )


class PersistentDeleteGateway(Protocol):
    def prepare_model_delete(self, model_id: str) -> Mapping[str, Any]: ...

    def prepare_analysis_delete(self, job_id: str) -> Mapping[str, Any]: ...

    def lookup_delete(self, resource_type: str, resource_id: str) -> Mapping[str, Any]: ...

    def list_recoverable(self, resource_type: str) -> Sequence[Mapping[str, Any]]: ...

    def storage_required(self, resource_type: str, resource_id: str) -> bool: ...

    def delete_storage_object(self, bucket: str, path: str) -> None: ...

    def complete_delete(self, resource_type: str, resource_id: str) -> None: ...

    def record_cleanup_failure(
        self, resource_type: str, resource_id: str, error_code: str
    ) -> None: ...


@dataclass(frozen=True)
class PersistentDeleteItemResult:
    resource_id: str
    status: str
    reason: str
    reference_counts: Mapping[str, Any]
    idempotent_replayed: bool


@dataclass(frozen=True)
class PersistentDeleteBatchResult:
    resource_type: str
    requested_count: int
    deleted_count: int
    blocked_count: int
    failed_count: int
    items: tuple[PersistentDeleteItemResult, ...]
    cleanup_required_count: int = 0
    uncertain_count: int = 0
    dto_version: str = "1"


class SupabasePersistentDeleteGateway:
    """Trusted-server adapter over service-role-only delete coordination RPCs."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def prepare_model_delete(self, model_id: str) -> Mapping[str, Any]:
        return self._prepare("prepare_model_persistent_delete", "p_model_id", model_id)

    def prepare_analysis_delete(self, job_id: str) -> Mapping[str, Any]:
        return self._prepare("prepare_analysis_persistent_delete", "p_job_id", job_id)

    def lookup_delete(self, resource_type: str, resource_id: str) -> Mapping[str, Any]:
        return self._mapping_rpc(
            "get_persistent_delete_status",
            {"p_resource_type": resource_type, "p_resource_id": resource_id},
            "persistent delete status lookup",
        )

    def list_recoverable(self, resource_type: str) -> Sequence[Mapping[str, Any]]:
        try:
            response = self._client.rpc(
                "list_persistent_delete_recovery",
                {"p_resource_type": resource_type},
            ).execute()
            value = response.data if hasattr(response, "data") else response
        except Exception as exc:
            raise PersistentDeleteGatewayError(
                "persistent delete recovery list failed"
            ) from exc
        if not isinstance(value, list) or any(not isinstance(row, Mapping) for row in value):
            raise PersistentDeleteGatewayError(
                "persistent delete recovery list returned invalid data"
            )
        return tuple(dict(row) for row in value)

    def storage_required(self, resource_type: str, resource_id: str) -> bool:
        try:
            response = self._client.rpc(
                "persistent_delete_storage_required",
                {"p_resource_type": resource_type, "p_resource_id": resource_id},
            ).execute()
            value = response.data if hasattr(response, "data") else response
        except Exception as exc:
            raise PersistentDeleteGatewayError(
                "persistent delete storage requirement lookup failed"
            ) from exc
        if isinstance(value, list):
            value = value[0] if len(value) == 1 else None
        if isinstance(value, Mapping) and len(value) == 1:
            value = next(iter(value.values()))
        if not isinstance(value, bool):
            raise PersistentDeleteGatewayError(
                "persistent delete storage requirement returned invalid data"
            )
        return value

    def _prepare(self, rpc_name: str, parameter: str, resource_id: str) -> Mapping[str, Any]:
        return self._mapping_rpc(
            rpc_name,
            {parameter: resource_id},
            "persistent delete prepare",
        )

    def _mapping_rpc(
        self,
        rpc_name: str,
        params: Mapping[str, Any],
        operation: str,
    ) -> Mapping[str, Any]:
        try:
            response = self._client.rpc(rpc_name, dict(params)).execute()
            value = response.data if hasattr(response, "data") else response
        except Exception as exc:
            raise PersistentDeleteGatewayError(f"{operation} failed") from exc
        if isinstance(value, list):
            value = value[0] if len(value) == 1 else None
        if not isinstance(value, Mapping):
            raise PersistentDeleteGatewayError(f"{operation} returned invalid data")
        return dict(value)

    def delete_storage_object(self, bucket: str, path: str) -> None:
        if bucket != MODEL_BUCKET or not path:
            raise PersistentDeleteGatewayError("storage ownership is invalid")
        remove_error: Exception | None = None
        try:
            storage = self._client.storage.from_(bucket)
            storage.remove([path])
        except Exception as exc:
            remove_error = exc
        try:
            exists = _storage_object_exists(storage, path)
        except Exception as exc:
            raise PersistentDeleteGatewayError(
                "storage cleanup verification failed"
            ) from exc
        if remove_error is not None and not _is_explicit_storage_not_found(remove_error):
            raise PersistentDeleteGatewayError(
                "storage cleanup outcome is uncertain"
            ) from remove_error
        if exists:
            raise PersistentDeleteGatewayError("storage cleanup failed") from remove_error
    def complete_delete(self, resource_type: str, resource_id: str) -> None:
        self._receipt_rpc(
            "complete_persistent_delete",
            {"p_resource_type": resource_type, "p_resource_id": resource_id},
        )

    def record_cleanup_failure(
        self, resource_type: str, resource_id: str, error_code: str
    ) -> None:
        self._receipt_rpc(
            "record_persistent_delete_cleanup_failure",
            {
                "p_resource_type": resource_type,
                "p_resource_id": resource_id,
                "p_error_code": error_code,
            },
        )

    def _receipt_rpc(self, rpc_name: str, params: Mapping[str, Any]) -> None:
        try:
            response = self._client.rpc(rpc_name, dict(params)).execute()
            value = response.data if hasattr(response, "data") else response
        except Exception as exc:
            raise PersistentDeleteGatewayError("persistent delete receipt update failed") from exc
        if isinstance(value, list):
            value = value[0] if len(value) == 1 else None
        if isinstance(value, Mapping) and len(value) == 1:
            value = next(iter(value.values()))
        if value is not True:
            raise PersistentDeleteGatewayError("persistent delete receipt update was not acknowledged")


class PersistentDeleteService:
    def __init__(
        self,
        sessions: AccessCodeSessionService,
        gateway: PersistentDeleteGateway,
    ) -> None:
        self._sessions = sessions
        self._gateway = gateway

    def delete_models(
        self, session_id: str, resource_ids: Sequence[str]
    ) -> PersistentDeleteBatchResult:
        self._sessions.require_admin(session_id)
        normalized = _normalize_ids(resource_ids)
        return self._delete_batch("model", normalized)

    def delete_analyses(
        self, session_id: str, resource_ids: Sequence[str]
    ) -> PersistentDeleteBatchResult:
        self._sessions.require_admin(session_id)
        normalized = _normalize_ids(resource_ids)
        return self._delete_batch("analysis", normalized)

    def list_model_recoveries(self, session_id: str) -> PersistentDeleteBatchResult:
        self._sessions.require_admin(session_id)
        return self._list_recoveries("model")

    def list_analysis_recoveries(self, session_id: str) -> PersistentDeleteBatchResult:
        self._sessions.require_admin(session_id)
        return self._list_recoveries("analysis")

    def retry_model_cleanup(
        self, session_id: str, resource_ids: Sequence[str]
    ) -> PersistentDeleteBatchResult:
        self._sessions.require_admin(session_id)
        return self._recover_batch("model", _normalize_ids(resource_ids))

    def retry_analysis_cleanup(
        self, session_id: str, resource_ids: Sequence[str]
    ) -> PersistentDeleteBatchResult:
        self._sessions.require_admin(session_id)
        return self._recover_batch("analysis", _normalize_ids(resource_ids))

    def _delete_batch(
        self, resource_type: str, resource_ids: tuple[str, ...]
    ) -> PersistentDeleteBatchResult:
        items = tuple(self._safe_delete_one(resource_type, resource_id) for resource_id in resource_ids)
        return _batch_result(resource_type, items)

    def _recover_batch(
        self, resource_type: str, resource_ids: tuple[str, ...]
    ) -> PersistentDeleteBatchResult:
        items = tuple(self._safe_recover_one(resource_type, resource_id) for resource_id in resource_ids)
        return _batch_result(resource_type, items)

    def _list_recoveries(self, resource_type: str) -> PersistentDeleteBatchResult:
        try:
            rows = self._gateway.list_recoverable(resource_type)
            items_list: list[PersistentDeleteItemResult] = []
            for row in rows:
                resource_id = _require_resource_id(row)
                items_list.append(
                    self._result_from_prepared(
                        resource_type,
                        resource_id,
                        _validated_prepare(resource_type, resource_id, row),
                        cleanup=False,
                    )
                )
            items = tuple(items_list)
        except Exception as exc:
            raise BffError(
                ApiErrorCode.TRANSIENT_SYSTEM_ERROR,
                "Persistent delete recovery status is unavailable",
            ) from exc
        return _batch_result(resource_type, items)

    def _safe_delete_one(
        self, resource_type: str, resource_id: str
    ) -> PersistentDeleteItemResult:
        try:
            return self._delete_one(resource_type, resource_id)
        except Exception:
            return _item(resource_id, "PREPARE_UNCERTAIN", "DELETE_PREPARE_UNCERTAIN")

    def _safe_recover_one(
        self, resource_type: str, resource_id: str
    ) -> PersistentDeleteItemResult:
        try:
            return self._recover_one(resource_type, resource_id)
        except Exception:
            return _item(resource_id, "PREPARE_UNCERTAIN", "DELETE_PREPARE_UNCERTAIN")

    def _delete_one(
        self, resource_type: str, resource_id: str
    ) -> PersistentDeleteItemResult:
        try:
            prepared = (
                self._gateway.prepare_model_delete(resource_id)
                if resource_type == "model"
                else self._gateway.prepare_analysis_delete(resource_id)
            )
            status, owner_model_id, bucket, path, references, replayed = _validated_prepare(
                resource_type, resource_id, prepared
            )
        except Exception:
            return self._recover_after_prepare_error(resource_type, resource_id)

        return self._result_from_prepared(
            resource_type,
            resource_id,
            (status, owner_model_id, bucket, path, references, replayed),
        )

    def _recover_after_prepare_error(
        self, resource_type: str, resource_id: str
    ) -> PersistentDeleteItemResult:
        try:
            recovered = _validated_prepare(
                resource_type,
                resource_id,
                self._gateway.lookup_delete(resource_type, resource_id),
            )
        except Exception:
            return _item(resource_id, "PREPARE_UNCERTAIN", "DELETE_PREPARE_UNCERTAIN")
        if recovered[0] == "NOT_COMMITTED":
            return _item(resource_id, "FAILED", "DELETE_PREPARE_FAILED", recovered[4], recovered[5])
        return self._result_from_prepared(resource_type, resource_id, recovered)

    def _recover_one(
        self, resource_type: str, resource_id: str
    ) -> PersistentDeleteItemResult:
        try:
            recovered = _validated_prepare(
                resource_type,
                resource_id,
                self._gateway.lookup_delete(resource_type, resource_id),
            )
        except Exception:
            return _item(resource_id, "PREPARE_UNCERTAIN", "DELETE_PREPARE_UNCERTAIN")
        if recovered[0] == "NOT_COMMITTED":
            return _item(resource_id, "FAILED", "DELETE_RECEIPT_NOT_FOUND", recovered[4], recovered[5])
        return self._result_from_prepared(resource_type, resource_id, recovered)

    def _result_from_prepared(
        self,
        resource_type: str,
        resource_id: str,
        prepared: tuple[str, str, str | None, str | None, Mapping[str, Any], bool],
        *,
        cleanup: bool = True,
    ) -> PersistentDeleteItemResult:
        status, owner_model_id, bucket, path, references, replayed = prepared

        if status == "DELETED":
            return _item(resource_id, "DELETED", "ALREADY_DELETED", references, replayed)
        if status not in {"READY_FOR_STORAGE", "CLEANUP_REQUIRED"}:
            reason = {
                "BLOCKED_IN_USE": "MODEL_IN_USE",
                "BLOCKED_NON_TERMINAL": "NON_TERMINAL_ANALYSIS_DELETE_BLOCKED",
                "BLOCKED_PROTECTED": "DELETE_PROTECTED_RESOURCE",
                "NOT_FOUND": "RESOURCE_NOT_FOUND",
                "NOT_COMMITTED": "DELETE_RECEIPT_NOT_FOUND",
                "PREPARE_UNCERTAIN": "DELETE_PREPARE_UNCERTAIN",
                "FAILED": "DELETE_INTEGRITY_FAILED",
            }[status]
            if status == "BLOCKED_IN_USE" and references.get("analysis_storage_cleanup_required"):
                reason = "MODEL_ANALYSIS_STORAGE_CLEANUP_REQUIRED"
            return _item(resource_id, status, reason, references, replayed)

        if not cleanup:
            return _item(
                resource_id,
                "CLEANUP_REQUIRED",
                "DB_DELETED_STORAGE_CLEANUP_REQUIRED",
                references,
                replayed,
            )

        if resource_type == "analysis" and path is None:
            try:
                storage_required = self._gateway.storage_required(
                    resource_type, resource_id
                )
            except Exception:
                return _item(
                    resource_id,
                    "CLEANUP_REQUIRED",
                    "DELETE_STORAGE_PROVENANCE_UNCERTAIN",
                    references,
                    replayed,
                )
            if storage_required:
                return _item(
                    resource_id,
                    "CLEANUP_REQUIRED",
                    "DELETE_STORAGE_PROVENANCE_UNCERTAIN",
                    references,
                    replayed,
                )

        if path is not None:
            try:
                _require_owned_storage_path(
                    resource_type,
                    resource_id,
                    owner_model_id,
                    bucket,
                    path,
                )
                self._gateway.delete_storage_object(bucket, path)
            except Exception:
                try:
                    self._gateway.record_cleanup_failure(
                        resource_type, resource_id, "STORAGE_CLEANUP_FAILED"
                    )
                except Exception:
                    pass
                return _item(
                    resource_id,
                    "CLEANUP_REQUIRED",
                    "DB_DELETED_STORAGE_CLEANUP_REQUIRED",
                    references,
                    replayed,
                )

        try:
            self._gateway.complete_delete(resource_type, resource_id)
        except Exception:
            try:
                after_failure = _validated_prepare(
                    resource_type,
                    resource_id,
                    self._gateway.lookup_delete(resource_type, resource_id),
                )
                if after_failure[0] == "DELETED":
                    return _item(
                        resource_id,
                        "DELETED",
                        "DELETED",
                        after_failure[4],
                        True,
                    )
            except Exception:
                pass
            return _item(
                resource_id,
                "CLEANUP_REQUIRED",
                "DELETE_COMPLETE_UNCERTAIN",
                references,
                replayed,
            )
        return _item(resource_id, "DELETED", "DELETED", references, replayed)


def _normalize_ids(resource_ids: Sequence[str]) -> tuple[str, ...]:
    if isinstance(resource_ids, (str, bytes)) or not 1 <= len(resource_ids) <= MAX_DELETE_BATCH:
        raise BffError(
            ApiErrorCode.VALIDATION_ERROR,
            f"Delete batch must contain 1-{MAX_DELETE_BATCH} resource IDs",
        )
    normalized: list[str] = []
    for value in resource_ids:
        try:
            normalized.append(str(uuid.UUID(str(value))))
        except (TypeError, ValueError, AttributeError) as exc:
            raise BffError(
                ApiErrorCode.VALIDATION_ERROR,
                "Delete batch contains an invalid resource ID",
            ) from exc
    if len(set(normalized)) != len(normalized):
        raise BffError(
            ApiErrorCode.VALIDATION_ERROR,
            "Delete batch resource IDs must be unique",
        )
    return tuple(normalized)


def _validated_prepare(
    resource_type: str,
    resource_id: str,
    value: Mapping[str, Any],
) -> tuple[str, str, str | None, str | None, Mapping[str, Any], bool]:
    status = str(value.get("delete_status") or "")
    if status not in _PREPARE_STATUSES:
        raise PersistentDeleteGatewayError("persistent delete status is invalid")
    try:
        owner_model_id = str(uuid.UUID(str(value.get("owner_model_id"))))
    except (TypeError, ValueError, AttributeError) as exc:
        raise PersistentDeleteGatewayError("persistent delete owner is invalid") from exc
    bucket = value.get("storage_bucket")
    path = value.get("storage_path")
    if bucket is not None and not isinstance(bucket, str):
        raise PersistentDeleteGatewayError("persistent delete bucket is invalid")
    if path is not None and not isinstance(path, str):
        raise PersistentDeleteGatewayError("persistent delete path is invalid")
    references = value.get("reference_counts") or {}
    if not isinstance(references, Mapping):
        raise PersistentDeleteGatewayError("persistent delete references are invalid")
    safe_references: dict[str, Any] = {}
    for key, entry in references.items():
        if not isinstance(key, str) or not isinstance(entry, (str, int)) or isinstance(entry, bool):
            raise PersistentDeleteGatewayError("persistent delete references are invalid")
        if isinstance(entry, int) and entry < 0:
            raise PersistentDeleteGatewayError("persistent delete references are invalid")
        safe_references[key] = entry
    replayed = value.get("idempotent_replayed")
    if not isinstance(replayed, bool):
        raise PersistentDeleteGatewayError("persistent delete replay flag is invalid")
    if status in {"READY_FOR_STORAGE", "CLEANUP_REQUIRED"}:
        if (bucket is None) != (path is None):
            raise PersistentDeleteGatewayError("persistent delete storage pair is invalid")
        if resource_type == "model" and (bucket is None or path is None):
            raise PersistentDeleteGatewayError(
                "model persistent delete storage provenance is missing"
            )
    elif bucket is not None or path is not None:
        if status != "DELETED":
            raise PersistentDeleteGatewayError("blocked delete exposed storage data")
    return status, owner_model_id, bucket, path, safe_references, replayed


def _require_resource_id(value: Mapping[str, Any]) -> str:
    try:
        return str(uuid.UUID(str(value.get("resource_id"))))
    except (TypeError, ValueError, AttributeError) as exc:
        raise PersistentDeleteGatewayError("persistent delete resource ID is invalid") from exc


def _batch_result(
    resource_type: str,
    items: tuple[PersistentDeleteItemResult, ...],
) -> PersistentDeleteBatchResult:
    deleted = sum(item.status == "DELETED" for item in items)
    cleanup_required = sum(item.status == "CLEANUP_REQUIRED" for item in items)
    blocked = sum(item.status.startswith("BLOCKED_") for item in items)
    uncertain = sum(item.status == "PREPARE_UNCERTAIN" for item in items)
    failed = len(items) - deleted - cleanup_required - blocked - uncertain
    return PersistentDeleteBatchResult(
        resource_type=resource_type,
        requested_count=len(items),
        deleted_count=deleted,
        blocked_count=blocked,
        failed_count=failed,
        items=items,
        cleanup_required_count=cleanup_required,
        uncertain_count=uncertain,
    )


def _require_owned_storage_path(
    resource_type: str,
    resource_id: str,
    owner_model_id: str,
    bucket: str | None,
    path: str,
) -> None:
    expected = (
        f"models/{resource_id}/source.xlsx"
        if resource_type == "model"
        else f"models/{owner_model_id}/jobs/{resource_id}/result.xlsx"
    )
    if bucket != MODEL_BUCKET or path != expected:
        raise PersistentDeleteGatewayError("persistent delete storage ownership is invalid")
    if resource_type == "model" and owner_model_id != resource_id:
        raise PersistentDeleteGatewayError("persistent delete model owner is invalid")


def _item(
    resource_id: str,
    status: str,
    reason: str,
    references: Mapping[str, Any] | None = None,
    replayed: bool = False,
) -> PersistentDeleteItemResult:
    return PersistentDeleteItemResult(
        resource_id=resource_id,
        status=status,
        reason=reason,
        reference_counts=dict(references or {}),
        idempotent_replayed=replayed,
    )
