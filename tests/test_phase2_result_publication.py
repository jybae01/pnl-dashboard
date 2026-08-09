import json

import pytest

from forecast.persistence.contracts import CalculationResultWrite
from forecast.persistence.local import (
    LocalCalculationJobRepository,
    LocalResultPublicationRepository,
    LocalResultRepositoryAdapter,
)
from forecast.persistence.publication import AdminResultPublicationGateway
from forecast.provenance import ResultProvenance
from forecast.storage import ResultStore


PROVENANCE = ResultProvenance("engine-2", "mapping-2", "a" * 64, "2")


def _completed_result(tmp_path):
    queue = LocalCalculationJobRepository(tmp_path / "jobs")
    queue.enqueue(
        model_id="model-1", storage_bucket="pnl-models",
        storage_path="models/model-1/source.xlsx", provenance=PROVENANCE,
        analysis_request={"publish": True, "make_default": True},
    )
    claim = queue.claim_next("worker")
    result_id = queue.complete(
        claim,
        CalculationResultWrite(
            payload={"amount": 1}, provenance=PROVENANCE,
            publish=True, make_default=True,
        ),
    )
    return result_id


def _complete_another(queue):
    queue.enqueue(
        model_id="model-1", storage_bucket="pnl-models",
        storage_path="models/model-1/second.xlsx", provenance=PROVENANCE,
    )
    claim = queue.claim_next("worker")
    return queue.complete(
        claim, CalculationResultWrite(payload={"amount": 2}, provenance=PROVENANCE)
    )


def test_admin_publication_is_separate_and_preserves_payload_provenance(tmp_path):
    result_id = _completed_result(tmp_path)
    repository = LocalResultPublicationRepository(tmp_path / "jobs")
    gateway = AdminResultPublicationGateway(repository, lambda: None)
    viewer = LocalResultRepositoryAdapter(ResultStore(tmp_path))
    result_path = next((tmp_path / "jobs" / "calculation_results").glob("*.json"))
    before = json.loads(result_path.read_text(encoding="utf-8"))
    assert before["is_published"] is False and before["is_default"] is False
    assert viewer.load_completed() is None

    after = gateway.set_publication(result_id, is_published=True, is_default=True)

    assert after["is_published"] is True and after["is_default"] is True
    assert viewer.load_completed()["id"] == result_id
    for key in ("result", "engine_version", "mapping_version", "mapping_hash", "result_schema_version"):
        assert after[key] == before[key]


def test_viewer_capability_cannot_publish(tmp_path):
    result_id = _completed_result(tmp_path)
    gateway = AdminResultPublicationGateway(
        LocalResultPublicationRepository(tmp_path / "jobs"),
        lambda: (_ for _ in ()).throw(PermissionError("admin required")),
    )
    with pytest.raises(PermissionError, match="admin required"):
        gateway.set_publication(result_id, is_published=True)


def test_unpublished_result_cannot_be_default(tmp_path):
    result_id = _completed_result(tmp_path)
    gateway = AdminResultPublicationGateway(LocalResultPublicationRepository(tmp_path / "jobs"), lambda: None)
    with pytest.raises(ValueError, match="must be published"):
        gateway.set_publication(result_id, is_published=False, is_default=True)


@pytest.mark.parametrize("status", ["processing", "failed"])
def test_noncompleted_job_result_cannot_be_published(tmp_path, status):
    result_id = _completed_result(tmp_path)
    jobs_path = tmp_path / "jobs" / "calculation_jobs.json"
    jobs = json.loads(jobs_path.read_text(encoding="utf-8"))
    jobs[0]["status"] = status
    jobs_path.write_text(json.dumps(jobs), encoding="utf-8")
    gateway = AdminResultPublicationGateway(
        LocalResultPublicationRepository(tmp_path / "jobs"), lambda: None
    )
    with pytest.raises(ValueError, match="completed"):
        gateway.set_publication(result_id, is_published=True)


def test_new_default_atomically_clears_previous_default(tmp_path):
    first = _completed_result(tmp_path)
    queue = LocalCalculationJobRepository(tmp_path / "jobs")
    second = _complete_another(queue)
    gateway = AdminResultPublicationGateway(
        LocalResultPublicationRepository(tmp_path / "jobs"), lambda: None
    )
    gateway.set_publication(first, is_published=True, is_default=True)
    gateway.set_publication(second, is_published=True, is_default=True)
    rows = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in (tmp_path / "jobs" / "calculation_results").glob("*.json")
    ]
    assert [row["id"] for row in rows if row["is_default"]] == [second]
