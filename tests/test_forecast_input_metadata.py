from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from openpyxl import Workbook

from forecast.bff.auth import AccessCodeSessionService
from forecast.bff.errors import ApiErrorCode, BffError
from forecast.bff.forecast_input_metadata import ForecastInputMetadataService
from forecast.provenance import ResultProvenance


BASE = "11111111-1111-4111-8111-111111111111"
PROVENANCE = ResultProvenance("engine", "mapping-v1", "a" * 64, "1")


class Repository:
    def __init__(self, path: Path) -> None:
        self._path = path
        self.model = SimpleNamespace(
            id=BASE,
            is_published=True,
            mapping_status="published",
            mapping_version=PROVENANCE.mapping_version,
            mapping_hash=PROVENANCE.mapping_hash,
            workbook_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        )

    def get(self, model_id: str):
        if model_id != BASE:
            raise KeyError(model_id)
        return self.model

    def path(self, model_id: str) -> Path:
        if model_id != BASE:
            raise KeyError(model_id)
        return self._path


def fixture(tmp_path: Path):
    path = tmp_path / "base.xlsx"
    workbook = Workbook()
    data = workbook.active
    data.title = "Data"
    data["D10"] = "노무비"
    data["E10"] = 1000
    data["F10"] = 2000
    data["B19"] = "판매비"
    data["D20"] = "운반비"
    data["E20"] = 500
    workbook.save(path)
    sessions = AccessCodeSessionService(
        viewer_code="viewer-code",
        admin_code="admin-code",
        actor_namespace_secret="actor-namespace-secret-at-least-32-chars",
    )
    service = ForecastInputMetadataService(
        sessions,
        Repository(path),
        {"manufacturing_input_rows": [10], "sga_input_rows": [20]},
        PROVENANCE,
    )
    return sessions, service


def test_admin_metadata_uses_opaque_keys_and_private_workbook_labels(tmp_path: Path):
    sessions, service = fixture(tmp_path)
    session = sessions.login("admin-code").session_id

    response = service.get(session, BASE)
    payload = asdict(response)

    expected_mfg_monthly = {month: (1000.0 if month == 1 else (2000.0 if month == 2 else 0.0)) for month in range(1, 13)}
    expected_sga_monthly = {month: (500.0 if month == 1 else 0.0) for month in range(1, 13)}

    assert payload["manufacturing"] == ({
        "adjustment_key": "manufacturing:000",
        "display_name": "노무비",
        "category": "manufacturing",
        "section": None,
        "unit": "KRW",
        "monthly_baseline_amounts": expected_mfg_monthly,
    },)
    assert payload["sga"][0]["adjustment_key"] == "sga:000"
    assert payload["sga"][0]["display_name"] == "운반비"
    assert payload["sga"][0]["section"] == "selling"
    assert payload["sga"][0]["monthly_baseline_amounts"] == expected_sga_monthly
    assert set(payload["manufacturing"][0]["monthly_baseline_amounts"].keys()) == set(range(1, 13))
    assert set(payload["sga"][0]["monthly_baseline_amounts"].keys()) == set(range(1, 13))
    serialized = json.dumps(payload, ensure_ascii=False)
    assert "row" not in serialized and "Data!" not in serialized
    assert "workbook" not in serialized.lower() and "sha" not in serialized.lower()

    assert service.resolve_adjustment_keys(
        session, BASE, "manufacturing", ("manufacturing:000",)
    ) == {"manufacturing:000": 10}
    assert service.resolve_adjustment_keys(
        session, BASE, "sga", ("sga:000",)
    ) == {"sga:000": 20}


def test_metadata_preserves_admin_and_integrity_boundaries(tmp_path: Path):
    sessions, service = fixture(tmp_path)
    viewer = sessions.login("viewer-code").session_id
    with pytest.raises(BffError) as forbidden:
        service.get(viewer, BASE)
    assert forbidden.value.code == ApiErrorCode.FORBIDDEN

    admin = sessions.login("admin-code").session_id
    with pytest.raises(BffError) as invalid:
        service.resolve_adjustment_keys(admin, BASE, "sga", ("sga:999",))
    assert invalid.value.code == ApiErrorCode.VALIDATION_ERROR

    service._repository.model.workbook_sha256 = "b" * 64
    with pytest.raises(BffError) as mismatch:
        service.get(admin, BASE)
    assert mismatch.value.code == ApiErrorCode.INPUT_INTEGRITY_MISMATCH
