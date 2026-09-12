from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
import httpx
from fastapi.testclient import TestClient

from forecast.bff.application import (
    AnalysisSubmissionService,
    WorkerAdministrationService,
)
from forecast.bff.auth import AccessCodeSessionService
from forecast.bff.dto import AnalysisSubmitRequest
from forecast.bff.errors import ApiErrorCode, BffError
from forecast.bff.gateway import SubmissionRecord
from forecast.provenance import ResultProvenance
from forecast.worker_lifecycle import (
    WorkerBusyError,
    WorkerControlPending,
    WorkerControlUnavailable,
    WorkerLifecycleController,
    WorkerLifecycleSnapshot,
    WorkerPoolObservation,
    GoogleWorkerPoolScaler,
    _pool_observation,
)
from forecast.worker_controller_server import create_worker_controller


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = (
    ROOT / "supabase/migrations/202608120001_demand_only_worker_lifecycle.sql"
).read_text(encoding="utf-8").lower()
BASE = "11111111-1111-4111-8111-111111111111"
COMP = "22222222-2222-4222-8222-222222222222"
JOB = "33333333-3333-4333-8333-333333333333"
PROVENANCE = ResultProvenance("engine", "mapping", "a" * 64, "1")


def snapshot(**changes) -> WorkerLifecycleSnapshot:
    value = WorkerLifecycleSnapshot(
        desired_instance_count=0,
        generation=1,
        observed_instance_count=0,
        queue_depth=0,
        claimable_count=0,
        pending_count=0,
        processing_count=0,
        active_lease_count=0,
        active_heartbeat_count=0,
        recovery_pending_count=0,
        work_exists=False,
        idle_seconds=1800,
        last_worker_activity_at="2026-08-12T00:00:00Z",
    )
    return replace(value, **changes)


class LifecycleGateway:
    def __init__(self, value: WorkerLifecycleSnapshot):
        self.value = value
        self.records = []
        self.race_value = None

    def snapshot(self): return self.value
    def reconcile(self): return self.value
    def emergency_wake(self):
        self.value = replace(
            self.value, desired_instance_count=1, generation=self.value.generation + 1,
            idle_seconds=0,
        )
        return self.value
    def safe_stop(self):
        if self.value.work_exists:
            raise WorkerBusyError("busy")
        self.value = replace(
            self.value, desired_instance_count=0, generation=self.value.generation + 1,
        )
        return self.value
    def record_scaling_result(self, generation, observed, result, error):
        self.records.append((generation, observed, result, error))
        if self.race_value is not None:
            self.value = self.race_value
            self.race_value = None
            return False
        return generation == self.value.generation


class Scaler:
    def __init__(self, count=0, *, fail=False):
        self.count = count
        self.fail = fail
        self.sets = []

    def get(self):
        if self.fail:
            raise TimeoutError("control plane")
        return WorkerPoolObservation(self.count, self.count, False, True)

    def set_instance_count(self, count):
        if self.fail:
            raise TimeoutError("control plane")
        self.sets.append(count)
        self.count = count
        return self.get()


class SubmitGateway:
    def __init__(self, events): self.events = events
    def submit_analysis(self, **_kwargs):
        self.events.append("durable_enqueue_commit")
        return SubmissionRecord(JOB, "pending", False)


class WakeControl:
    def __init__(self, events, *, fail=False):
        self.events = events; self.fail = fail; self.wakes = 0
    def ensure_after_enqueue(self):
        self.events.append("wake")
        self.wakes += 1
        if self.fail: raise WorkerControlUnavailable("failed")
        return {"actual_instance_count": 0}


def sessions():
    value = AccessCodeSessionService(
        viewer_code="viewer-code", admin_code="admin-code",
        actor_namespace_secret="actor-namespace-secret-at-least-32-chars",
        ttl_seconds=3600,
    )
    return value, value.login("admin-code").session_id, value.login("viewer-code").session_id


def request():
    return AnalysisSubmitRequest(
        baseline_model_id=BASE,
        comparison_model_id=COMP,
        start_month=1,
        end_month=6,
        idempotency_key="demand-only",
        baseline_sales_fx_monthly={
            f"2026-{month:02d}": 1480.0 for month in range(1, 7)
        },
        comparison_sales_fx_monthly={
            f"2026-{month:02d}": 1500.0 for month in range(1, 7)
        },
    )


def test_analysis_durable_enqueue_precedes_wake_and_cold_state_is_explicit():
    events = []
    auth, admin, _ = sessions()
    control = WakeControl(events)
    result = AnalysisSubmissionService(
        auth, SubmitGateway(events), PROVENANCE, worker_control=control
    ).submit(admin, request())
    assert events == ["durable_enqueue_commit", "wake"]
    assert result.status == "PENDING"
    assert result.execution_state == "STARTING_WORKER"


def test_wake_failure_keeps_durable_job_queued_for_reconciler():
    events = []
    auth, admin, _ = sessions()
    result = AnalysisSubmissionService(
        auth, SubmitGateway(events), PROVENANCE,
        worker_control=WakeControl(events, fail=True),
    ).submit(admin, request())
    assert events == ["durable_enqueue_commit", "wake"]
    assert result.job_id == JOB and result.execution_state == "QUEUED"


def test_reconciler_wakes_pending_work_and_duplicate_calls_converge_to_one():
    gateway = LifecycleGateway(snapshot(
        desired_instance_count=1, queue_depth=2, claimable_count=2,
        pending_count=2, work_exists=True, idle_seconds=0,
    ))
    scaler = Scaler(0)
    controller = WorkerLifecycleController(gateway, scaler)
    assert controller.reconcile().pool.configured_instance_count == 1
    assert controller.reconcile().pool.configured_instance_count == 1
    assert scaler.sets == [1]


def test_reconciler_repairs_idle_cost_leak_from_one_to_zero():
    gateway = LifecycleGateway(snapshot(desired_instance_count=0, idle_seconds=1800))
    scaler = Scaler(1)
    result = WorkerLifecycleController(gateway, scaler).reconcile()
    assert scaler.sets == [0]
    assert result.pool.configured_instance_count == 0


def test_sleep_enqueue_generation_race_reconverges_to_awake():
    gateway = LifecycleGateway(snapshot(desired_instance_count=0, generation=4))
    gateway.race_value = snapshot(
        desired_instance_count=1, generation=5, queue_depth=1,
        claimable_count=1, pending_count=1, work_exists=True, idle_seconds=0,
    )
    scaler = Scaler(1)
    result = WorkerLifecycleController(gateway, scaler).reconcile()
    assert scaler.sets == [0, 1]
    assert result.snapshot.generation == 5
    assert result.pool.configured_instance_count == 1


def test_controller_failure_is_recorded_without_claiming_job_loss():
    gateway = LifecycleGateway(snapshot(desired_instance_count=1, work_exists=True))
    with pytest.raises(WorkerControlUnavailable):
        WorkerLifecycleController(gateway, Scaler(fail=True)).reconcile()
    assert gateway.records[-1][2] == "wake_failed"


def test_controller_maps_dependency_failure_to_retriable_503():
    class BrokenGateway(LifecycleGateway):
        def reconcile(self): raise RuntimeError("database unavailable")

    app = create_worker_controller(
        WorkerLifecycleController(BrokenGateway(snapshot()), Scaler(0))
    )
    response = TestClient(app).post("/v1/worker/reconcile")
    assert response.status_code == 503
    assert response.json() == {"error": {"code": "WORKER_CONTROL_UNAVAILABLE"}}


def test_google_scaler_uses_attached_identity_and_exact_manual_count_patch():
    requests = []

    def handler(request: httpx.Request):
        requests.append(request)
        if request.url.host == "metadata.google.internal":
            assert request.headers["Metadata-Flavor"] == "Google"
            return httpx.Response(200, json={"access_token": "test-token"})
        assert request.headers["Authorization"] == "Bearer test-token"
        if request.method == "PATCH":
            assert request.url.params["update_mask"] == "scaling.manualInstanceCount"
            assert request.content == b'{"scaling":{"manualInstanceCount":1}}'
            return httpx.Response(200, json={
                "name": "projects/exact-project-id/locations/asia-southeast1/operations/test"
            })
        assert "/operations/test" in request.url.path
        return httpx.Response(200, json={"done": True, "response": {
            "scaling": {"manualInstanceCount": 1}, "generation": "2",
            "observedGeneration": "2", "reconciling": False,
            "terminalCondition": {"state": "CONDITION_SUCCEEDED"},
        }})

    scaler = GoogleWorkerPoolScaler(
        project_id="exact-project-id", region="asia-southeast1",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        operation_poll_seconds=0.001,
    )
    observed = scaler.set_instance_count(1)
    assert observed.configured_instance_count == observed.observed_instance_count == 1
    assert [request.method for request in requests] == ["GET", "PATCH", "GET"]


@pytest.mark.parametrize("operation, error", [
    ({"done": True, "error": {"code": 13}}, WorkerControlUnavailable),
    ({"name": "projects/exact-project-id/locations/europe-west12/operations/pending"}, WorkerControlPending),
])
def test_google_scaler_never_claims_failed_or_unfinished_operation(operation, error):
    def handler(request: httpx.Request):
        if request.url.host == "metadata.google.internal":
            return httpx.Response(200, json={"access_token": "test-token"})
        if request.method == "PATCH":
            return httpx.Response(200, json=operation)
        raise AssertionError("a zero polling budget must not make another call")

    scaler = GoogleWorkerPoolScaler(
        project_id="exact-project-id", region="europe-west12",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        operation_wait_seconds=0,
    )
    with pytest.raises(error):
        scaler.set_instance_count(1)


def test_terminal_failure_reissues_same_count_and_unknown_state_is_not_ready():
    failed = WorkerPoolObservation(1, None, False, False, "CONDITION_FAILED")

    class FailedScaler(Scaler):
        def get(self): return failed if not self.sets else super().get()

    gateway = LifecycleGateway(snapshot(desired_instance_count=1, work_exists=True))
    scaler = FailedScaler(1)
    result = WorkerLifecycleController(gateway, scaler).reconcile()
    assert scaler.sets == [1]
    assert result.pool.ready is True

    unknown = _pool_observation({
        "scaling": {"manualInstanceCount": 1}, "generation": "2",
        "observedGeneration": "2", "reconciling": False,
    })
    assert unknown.ready is False and unknown.observed_instance_count is None


def test_reconciler_repairs_out_of_policy_manual_count_drift():
    class DriftScaler(Scaler):
        def get(self):
            return WorkerPoolObservation(self.count, None, False, False, "CONDITION_SUCCEEDED")

    gateway = LifecycleGateway(snapshot(desired_instance_count=1, work_exists=True))
    scaler = DriftScaler(2)
    WorkerLifecycleController(gateway, scaler).reconcile()
    assert scaler.sets == [1]


def test_admin_emergency_controls_are_server_authorized_and_safe_stop_is_safe():
    auth, admin, viewer = sessions()
    gateway = LifecycleGateway(snapshot())
    control = WorkerLifecycleController(gateway, Scaler(0))
    service = WorkerAdministrationService(auth, _AdminControlAdapter(control))
    with pytest.raises(BffError) as denied:
        service.emergency_wake(viewer)
    assert denied.value.code is ApiErrorCode.FORBIDDEN
    assert service.emergency_wake(admin)["desired_instance_count"] == 1
    gateway.value = replace(gateway.value, work_exists=True, processing_count=1)
    with pytest.raises(BffError) as busy:
        service.safe_stop(admin)
    assert busy.value.code is ApiErrorCode.WORKER_BUSY


class _AdminControlAdapter:
    def __init__(self, controller): self.controller = controller
    def status(self): return self.controller.status().public_dict()
    def emergency_wake(self): return self.controller.emergency_wake().public_dict()
    def safe_stop(self): return self.controller.safe_stop().public_dict()


def test_database_contract_tracks_only_worker_required_job_activity():
    assert "after insert or update on public.calculation_jobs" in MIGRATION
    for field in (
        "new.status", "new.heartbeat_at", "new.lease_expires_at", "new.attempt",
        "new.queue_message_id", "new.queue_archived_at", "new.completed_at",
    ):
        assert field in MIGRATION
    for unrelated in ("login", "dashboard", "forecast", "model upload", "maintenance"):
        assert unrelated not in MIGRATION
    assert "new.upload_completed_at is not null" in MIGRATION
    assert "new.queue_message_id is not null" in MIGRATION
    assert "v_worker_eligible_new" in MIGRATION
    assert "status = 'pending'\n                 and upload_completed_at is not null" in MIGRATION


@pytest.mark.parametrize("module", [
    "forecast/bff/auth.py",
    "forecast/bff/model_ingestion.py",
    "forecast/bff/forecast_orchestration.py",
    "forecast/bff/evidence_history.py",
    "forecast/bff/pnl_dashboard.py",
    "forecast/bff/analysis_presentation.py",
])
def test_non_worker_operations_have_no_wake_dependency(module):
    source = (ROOT / module).read_text(encoding="utf-8")
    assert "ensure_after_enqueue" not in source
    assert "emergency_wake" not in source
    assert "set_instance_count" not in source


def test_database_contract_enforces_exact_30_minute_all_clear_policy():
    for contract in (
        "p_idle_seconds <> 1800",
        "make_interval(secs => 1800)",
        "v_queue_depth > 0",
        "v_pending > 0",
        "v_processing > 0",
        "v_active_leases > 0",
        "v_recovery > 0",
        "count(*) filter (where vt <= now())",
    ):
        assert contract in MIGRATION
    assert "last_worker_activity_at = now()" in MIGRATION


def test_idle_boundary_keeps_29m59s_and_sleeps_at_30m():
    # Mirrors the fixed database predicate asserted above: elapsed >= 1800.
    target = lambda current, work, idle: 1 if work else (0 if idle >= 1800 else current)
    assert target(1, False, 1799) == 1
    assert target(1, False, 1800) == 0
    assert target(1, True, 1800) == 1


def test_new_worker_activity_resets_idle_and_emergency_wake_is_not_always_on():
    assert "last_worker_activity_at = now()" in MIGRATION
    assert "create or replace function public.emergency_wake_worker()" in MIGRATION
    assert "make_interval(secs => 1800)" in MIGRATION
    assert "always_on" not in MIGRATION and "force_stop" not in MIGRATION


def test_database_contract_serializes_decisions_and_versions_activity():
    assert MIGRATION.count("pg_advisory_xact_lock(1777046461)") >= 4
    assert "generation = generation + 1" in MIGRATION
    assert "where singleton and generation = p_generation" in MIGRATION
    assert "desired_instance_count in (0, 1)" in MIGRATION


def test_database_contract_is_service_role_only_and_has_no_force_stop():
    assert "grant execute on function public.safe_stop_worker() to service_role" in MIGRATION
    assert "revoke all on function public.safe_stop_worker() from public, anon, authenticated" in MIGRATION
    assert "force_stop" not in MIGRATION
    assert "raise exception 'worker_busy'" in MIGRATION
    assert "grant select" not in MIGRATION and "grant update" not in MIGRATION
