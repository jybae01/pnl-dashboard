import time

from forecast.persistence import CalculationResultWrite, JobStatus
from forecast.persistence.local import LocalCalculationJobRepository
from forecast.provenance import ResultProvenance
from forecast.worker import WorkerJobControl
from forecast.worker_runtime import WorkerRunner


class RecordingQueue(LocalCalculationJobRepository):
    def __init__(self, directory):
        super().__init__(directory)
        self.heartbeats = []
        self.complete_started = None

    def heartbeat(self, claim, *, lease_seconds=300):
        self.heartbeats.append(time.monotonic())
        return super().heartbeat(claim, lease_seconds=lease_seconds)

    def complete(self, claim, result):
        self.complete_started = time.monotonic()
        return super().complete(claim, result)


class SlowExecutor:
    def __init__(self, provenance):
        self.provenance = provenance

    def execute(self, claim, *, heartbeat=None):
        time.sleep(0.45)
        return CalculationResultWrite(payload={"ok": True}, provenance=self.provenance)


def test_periodic_heartbeat_thread_joins_before_terminal_commit(tmp_path):
    provenance = ResultProvenance("engine-2", "mapping-2", "f" * 64, "2")
    queue = RecordingQueue(tmp_path)
    queue.enqueue(
        model_id="comparison",
        storage_bucket="pnl-models",
        storage_path="models/comparison/source.xlsx",
        provenance=provenance,
    )
    runner = WorkerRunner(
        WorkerJobControl(queue, "worker-a"),
        SlowExecutor(provenance),
        lease_seconds=1,
        poll_seconds=0,
    )

    outcome = runner.run_once()
    count_at_completion = len(queue.heartbeats)
    time.sleep(0.4)

    assert outcome.status is JobStatus.COMPLETED
    assert count_at_completion >= 2
    assert len(queue.heartbeats) == count_at_completion
    assert max(queue.heartbeats) <= queue.complete_started
