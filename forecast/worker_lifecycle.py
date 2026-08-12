from __future__ import annotations

import logging
import re
import time
from dataclasses import asdict, dataclass
from typing import Any, Mapping, Protocol

import httpx


LOGGER = logging.getLogger(__name__)
SAFE_ERROR_CODE = re.compile(r"^[A-Z0-9_]{1,64}$")
METADATA_ROOT = "http://metadata.google.internal/computeMetadata/v1"


class WorkerControlUnavailable(RuntimeError):
    """The durable job is safe, but lifecycle control needs reconciliation."""


class WorkerBusyError(RuntimeError):
    """Safe stop was rejected because worker-required work still exists."""


class WorkerControlPending(WorkerControlUnavailable):
    """Cloud Run accepted a change but has not proved terminal success yet."""


@dataclass(frozen=True)
class WorkerLifecycleSnapshot:
    desired_instance_count: int
    generation: int
    observed_instance_count: int | None
    queue_depth: int
    claimable_count: int
    pending_count: int
    processing_count: int
    active_lease_count: int
    active_heartbeat_count: int
    recovery_pending_count: int
    work_exists: bool
    idle_seconds: int
    last_worker_activity_at: str
    last_wake_requested_at: str | None = None
    last_sleep_requested_at: str | None = None
    last_scaling_at: str | None = None
    last_scaling_result: str | None = None
    last_scaling_error_code: str | None = None

    @classmethod
    def from_mapping(cls, row: Mapping[str, Any]) -> "WorkerLifecycleSnapshot":
        desired = int(row["desired_instance_count"])
        observed_raw = row.get("observed_instance_count")
        observed = None if observed_raw is None else int(observed_raw)
        if desired not in (0, 1) or observed not in (None, 0, 1):
            raise ValueError("worker lifecycle count is outside the V1 zero/one policy")
        return cls(
            desired_instance_count=desired,
            generation=int(row["generation"]),
            observed_instance_count=observed,
            queue_depth=int(row["queue_depth"]),
            claimable_count=int(row["claimable_count"]),
            pending_count=int(row["pending_count"]),
            processing_count=int(row["processing_count"]),
            active_lease_count=int(row["active_lease_count"]),
            active_heartbeat_count=int(row["active_heartbeat_count"]),
            recovery_pending_count=int(row["recovery_pending_count"]),
            work_exists=bool(row["work_exists"]),
            idle_seconds=max(0, int(row["idle_seconds"])),
            last_worker_activity_at=str(row["last_worker_activity_at"]),
            last_wake_requested_at=_optional_text(row.get("last_wake_requested_at")),
            last_sleep_requested_at=_optional_text(row.get("last_sleep_requested_at")),
            last_scaling_at=_optional_text(row.get("last_scaling_at")),
            last_scaling_result=_optional_text(row.get("last_scaling_result")),
            last_scaling_error_code=_optional_text(row.get("last_scaling_error_code")),
        )


@dataclass(frozen=True)
class WorkerPoolObservation:
    configured_instance_count: int
    observed_instance_count: int | None
    reconciling: bool
    ready: bool
    terminal_state: str = ""

    @property
    def terminal_failed(self) -> bool:
        return self.terminal_state == "CONDITION_FAILED"


@dataclass(frozen=True)
class WorkerControlResult:
    snapshot: WorkerLifecycleSnapshot
    pool: WorkerPoolObservation
    scaling_result: str

    def public_dict(self) -> dict[str, Any]:
        value = asdict(self.snapshot)
        value.update({
            "configured_instance_count": self.pool.configured_instance_count,
            "actual_instance_count": self.pool.observed_instance_count,
            "platform_reconciling": self.pool.reconciling,
            "platform_ready": self.pool.ready,
            "scaling_result": self.scaling_result,
            "operating_policy": "DEMAND_ONLY",
            "idle_policy_seconds": 1800,
            "dto_version": "1",
        })
        return value


class WorkerLifecycleGateway(Protocol):
    def snapshot(self) -> WorkerLifecycleSnapshot: ...
    def reconcile(self) -> WorkerLifecycleSnapshot: ...
    def emergency_wake(self) -> WorkerLifecycleSnapshot: ...
    def safe_stop(self) -> WorkerLifecycleSnapshot: ...
    def record_scaling_result(
        self,
        generation: int,
        observed_instance_count: int | None,
        result: str,
        error_code: str | None,
    ) -> bool: ...


class WorkerPoolScaler(Protocol):
    def get(self) -> WorkerPoolObservation: ...
    def set_instance_count(self, count: int) -> WorkerPoolObservation: ...


class SupabaseWorkerLifecycleGateway:
    def __init__(self, client: Any) -> None:
        self._client = client

    def snapshot(self) -> WorkerLifecycleSnapshot:
        return self._snapshot_rpc("get_worker_lifecycle_snapshot")

    def reconcile(self) -> WorkerLifecycleSnapshot:
        return self._snapshot_rpc("reconcile_worker_lifecycle", {"p_idle_seconds": 1800})

    def emergency_wake(self) -> WorkerLifecycleSnapshot:
        return self._snapshot_rpc("emergency_wake_worker")

    def safe_stop(self) -> WorkerLifecycleSnapshot:
        try:
            return self._snapshot_rpc("safe_stop_worker")
        except Exception as exc:
            if "WORKER_BUSY" in str(exc):
                raise WorkerBusyError("worker-required activity is active") from exc
            raise

    def record_scaling_result(
        self,
        generation: int,
        observed_instance_count: int | None,
        result: str,
        error_code: str | None,
    ) -> bool:
        try:
            response = self._client.rpc("record_worker_scaling_result", {
                "p_generation": generation,
                "p_observed_instance_count": observed_instance_count,
                "p_result": result,
                "p_error_code": error_code,
            }).execute()
            return bool(_response_data(response))
        except Exception as exc:
            raise WorkerControlUnavailable("lifecycle state is unavailable") from exc

    def _snapshot_rpc(
        self, name: str, params: Mapping[str, Any] | None = None
    ) -> WorkerLifecycleSnapshot:
        try:
            response = self._client.rpc(name, dict(params or {})).execute()
            value = _response_data(response)
            if not isinstance(value, Mapping):
                raise ValueError("invalid lifecycle snapshot")
            return WorkerLifecycleSnapshot.from_mapping(value)
        except WorkerBusyError:
            raise
        except Exception as exc:
            if "WORKER_BUSY" in str(exc):
                raise WorkerBusyError("worker-required activity is active") from exc
            raise WorkerControlUnavailable("lifecycle state is unavailable") from exc


class GoogleWorkerPoolScaler:
    """Minimal Worker Pools v2 client using attached service identity only."""

    def __init__(
        self,
        *,
        project_id: str,
        region: str,
        worker_pool: str = "pnl-worker",
        client: httpx.Client | None = None,
        operation_wait_seconds: float = 8.0,
        operation_poll_seconds: float = 0.5,
    ) -> None:
        if not re.fullmatch(r"[a-z][a-z0-9-]{4,61}[a-z0-9]", project_id):
            raise ValueError("invalid Google Cloud project ID")
        if not re.fullmatch(r"[a-z]+-[a-z]+[0-9]+", region):
            raise ValueError("invalid Google Cloud region")
        if not re.fullmatch(r"[a-z][a-z0-9-]{0,61}[a-z0-9]", worker_pool):
            raise ValueError("invalid Worker Pool name")
        if operation_wait_seconds < 0 or operation_poll_seconds <= 0:
            raise ValueError("invalid operation polling budget")
        self._client = client or httpx.Client(timeout=4.0)
        self._operation_wait_seconds = operation_wait_seconds
        self._operation_poll_seconds = operation_poll_seconds
        self._resource_parent = f"projects/{project_id}/locations/{region}"
        self._url = (
            "https://run.googleapis.com/v2/projects/"
            f"{project_id}/locations/{region}/workerPools/{worker_pool}"
        )

    def get(self) -> WorkerPoolObservation:
        return self._get_with_headers(self._headers())

    def _get_with_headers(self, headers: Mapping[str, str]) -> WorkerPoolObservation:
        response = self._client.get(self._url, headers=headers)
        response.raise_for_status()
        return _pool_observation(response.json())

    def set_instance_count(self, count: int) -> WorkerPoolObservation:
        if count not in (0, 1):
            raise ValueError("V1 Worker Pool count must be zero or one")
        headers = {**self._headers(), "Content-Type": "application/json"}
        response = self._client.patch(
            self._url,
            params={"update_mask": "scaling.manualInstanceCount"},
            headers=headers,
            json={"scaling": {"manualInstanceCount": count}},
        )
        response.raise_for_status()
        operation = response.json()
        if not isinstance(operation, Mapping):
            raise WorkerControlUnavailable("Cloud Run operation response is invalid")
        return self._wait_for_operation(operation, headers)

    def _wait_for_operation(
        self, operation: Mapping[str, Any], headers: Mapping[str, str]
    ) -> WorkerPoolObservation:
        deadline = time.monotonic() + self._operation_wait_seconds
        current = operation
        while True:
            if bool(current.get("done")):
                if current.get("error") is not None:
                    raise WorkerControlUnavailable("Cloud Run operation failed")
                resource = current.get("response")
                if isinstance(resource, Mapping):
                    return _pool_observation(resource)
                return self._get_with_headers(headers)
            name = str(current.get("name") or "")
            expected = f"{self._resource_parent}/operations/"
            if not name.startswith(expected):
                raise WorkerControlUnavailable("Cloud Run operation name is invalid")
            if time.monotonic() >= deadline:
                raise WorkerControlPending("Cloud Run operation is still pending")
            time.sleep(min(self._operation_poll_seconds, max(0.0, deadline - time.monotonic())))
            response = self._client.get(
                f"https://run.googleapis.com/v2/{name}", headers=headers
            )
            response.raise_for_status()
            value = response.json()
            if not isinstance(value, Mapping):
                raise WorkerControlUnavailable("Cloud Run operation response is invalid")
            current = value

    def _headers(self) -> dict[str, str]:
        token = _metadata_value(
            self._client,
            "/instance/service-accounts/default/token",
            json_field="access_token",
        )
        return {"Authorization": f"Bearer {token}"}


class WorkerLifecycleController:
    def __init__(
        self,
        gateway: WorkerLifecycleGateway,
        scaler: WorkerPoolScaler,
        *,
        max_convergence_attempts: int = 2,
    ) -> None:
        self._gateway = gateway
        self._scaler = scaler
        self._attempts = max_convergence_attempts

    def status(self) -> WorkerControlResult:
        snapshot = self._gateway.snapshot()
        return WorkerControlResult(snapshot, self._scaler.get(), "noop")

    def reconcile(self) -> WorkerControlResult:
        return self._converge(self._gateway.reconcile())

    def emergency_wake(self) -> WorkerControlResult:
        return self._converge(self._gateway.emergency_wake())

    def safe_stop(self) -> WorkerControlResult:
        return self._converge(self._gateway.safe_stop())

    def _converge(self, snapshot: WorkerLifecycleSnapshot) -> WorkerControlResult:
        for _ in range(self._attempts):
            try:
                pool = self._scaler.get()
                result = "noop"
                if (
                    pool.configured_instance_count != snapshot.desired_instance_count
                    or pool.terminal_failed
                ):
                    pool = self._scaler.set_instance_count(snapshot.desired_instance_count)
                    result = "scaled"
                elif not pool.ready:
                    raise WorkerControlPending("Worker Pool reconciliation is pending")
                recorded = self._gateway.record_scaling_result(
                    snapshot.generation,
                    pool.observed_instance_count,
                    result,
                    None,
                )
            except Exception as exc:
                code = _safe_exception_code(exc)
                failure = "wake_failed" if snapshot.desired_instance_count else "sleep_failed"
                try:
                    self._gateway.record_scaling_result(
                        snapshot.generation, None, failure, code
                    )
                except Exception:
                    LOGGER.warning("worker lifecycle failure record was unavailable")
                LOGGER.warning(
                    "worker lifecycle scaling failed",
                    extra={
                        "desired_instance_count": snapshot.desired_instance_count,
                        "generation": snapshot.generation,
                        "error_code": code,
                    },
                )
                raise WorkerControlUnavailable("worker lifecycle scaling failed") from exc
            if recorded:
                LOGGER.info(
                    "worker lifecycle reconciled",
                    extra={
                        "desired_instance_count": snapshot.desired_instance_count,
                        "configured_instance_count": pool.configured_instance_count,
                        "observed_instance_count": pool.observed_instance_count,
                        "queue_depth": snapshot.queue_depth,
                        "processing_count": snapshot.processing_count,
                        "active_lease_count": snapshot.active_lease_count,
                        "recovery_pending_count": snapshot.recovery_pending_count,
                        "idle_seconds": snapshot.idle_seconds,
                        "generation": snapshot.generation,
                        "scaling_result": result,
                    },
                )
                return WorkerControlResult(snapshot, pool, result)
            # Activity raced with a sleep or another controller. Re-read durable
            # state and converge again; periodic reconciliation remains the final
            # recovery path if this request is interrupted.
            snapshot = self._gateway.reconcile()
        raise WorkerControlUnavailable("worker lifecycle did not converge")


class CloudRunWorkerControlClient:
    """BFF client for the private IAM-protected controller service."""

    def __init__(self, service_url: str, *, client: httpx.Client | None = None) -> None:
        value = service_url.rstrip("/")
        if not re.fullmatch(r"https://[^/]+", value):
            raise ValueError("worker controller URL must be an HTTPS origin")
        self._origin = value
        self._client = client or httpx.Client(timeout=15.0)

    def ensure_after_enqueue(self) -> Mapping[str, Any]:
        return self._request("POST", "/v1/worker/reconcile")

    def status(self) -> Mapping[str, Any]:
        return self._request("GET", "/v1/worker/status")

    def emergency_wake(self) -> Mapping[str, Any]:
        return self._request("POST", "/v1/worker/emergency-wake")

    def safe_stop(self) -> Mapping[str, Any]:
        return self._request("POST", "/v1/worker/safe-stop")

    def _request(self, method: str, path: str) -> Mapping[str, Any]:
        token = _metadata_value(
            self._client,
            "/instance/service-accounts/default/identity",
            params={"audience": self._origin},
        )
        response = self._client.request(
            method,
            f"{self._origin}{path}",
            headers={"Authorization": f"Bearer {token}"},
        )
        if response.status_code == 409:
            raise WorkerBusyError("worker-required activity is active")
        response.raise_for_status()
        value = response.json()
        if not isinstance(value, Mapping):
            raise WorkerControlUnavailable("worker controller response is invalid")
        return value


def _metadata_value(
    client: httpx.Client,
    path: str,
    *,
    params: Mapping[str, str] | None = None,
    json_field: str | None = None,
) -> str:
    response = client.get(
        f"{METADATA_ROOT}{path}",
        params=params,
        headers={"Metadata-Flavor": "Google"},
    )
    response.raise_for_status()
    value: Any = response.json().get(json_field) if json_field else response.text
    if not isinstance(value, str) or not value.strip():
        raise WorkerControlUnavailable("Google metadata credential is unavailable")
    return value.strip()


def _pool_observation(value: Mapping[str, Any]) -> WorkerPoolObservation:
    configured = int((value.get("scaling") or {}).get("manualInstanceCount", 0))
    if configured < 0:
        raise WorkerControlUnavailable("Worker Pool count is invalid")
    reconciling = bool(value.get("reconciling", False))
    generation = str(value.get("generation") or "")
    observed_generation = str(value.get("observedGeneration") or "")
    state = str((value.get("terminalCondition") or {}).get("state") or "")
    ready = (
        not reconciling
        and generation == observed_generation
        and state == "CONDITION_SUCCEEDED"
        and configured in (0, 1)
    )
    # Cloud Run exposes configured manual count plus reconciliation state, not a
    # live process counter. Treat the count as observed only after reconciliation.
    observed = configured if ready else None
    return WorkerPoolObservation(configured, observed, reconciling, ready, state)


def _response_data(response: Any) -> Any:
    return response.data if hasattr(response, "data") else response


def _optional_text(value: Any) -> str | None:
    return None if value is None else str(value)


def _safe_exception_code(exc: Exception) -> str:
    if isinstance(exc, WorkerControlPending):
        return "GOOGLE_OPERATION_PENDING"
    if isinstance(exc, WorkerControlUnavailable):
        return "WORKER_CONTROL_UNAVAILABLE"
    if isinstance(exc, httpx.TimeoutException):
        return "GOOGLE_API_TIMEOUT"
    if isinstance(exc, httpx.HTTPStatusError):
        return f"GOOGLE_API_HTTP_{exc.response.status_code}"
    name = re.sub(r"[^A-Z0-9_]", "_", type(exc).__name__.upper())[:64]
    return name if SAFE_ERROR_CODE.fullmatch(name) else "CONTROLLER_ERROR"
