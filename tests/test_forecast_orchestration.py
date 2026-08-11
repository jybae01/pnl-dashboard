from __future__ import annotations

import hashlib
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from forecast.bff.auth import AccessCodeSessionService
from forecast.bff.errors import ApiErrorCode, BffError
from forecast.bff.forecast_orchestration import (
    ForecastFinalizeUncertainError, ForecastGenerateRequest, ForecastGenerationService, ForecastMonthInput,
    ForecastQuantityInput, ForecastReservation, ForecastSalesInput,
)
from forecast.provenance import ResultProvenance


BASE_ID = "11111111-1111-4111-8111-111111111111"
MODEL_ID = "22222222-2222-4222-8222-222222222222"
GENERATION_ID = "33333333-3333-4333-8333-333333333333"


class Gateway:
    def __init__(self):
        self.fingerprint = None
        self.saved = None
        self.uploaded = b""
        self.lock = threading.Lock()
        self.reservations = 0

    def reserve(self, *, fingerprint, **kwargs):
        with self.lock:
            if self.fingerprint is not None and self.fingerprint != fingerprint:
                raise RuntimeError("IDEMPOTENCY_CONFLICT")
            self.fingerprint = fingerprint
            self.reservations += 1
            status = "completed" if self.saved else "reserved"
        return ForecastReservation(GENERATION_ID, MODEL_ID, status,
            None if status == "completed" else "44444444-4444-4444-8444-444444444444",
            status == "completed", "pnl-models", f"models/{BASE_ID}/source.xlsx", "a" * 64)

    def download_base(self, reservation): return b"base"
    def upload_generated(self, model_id, path, sha256): self.uploaded = path.read_bytes()
    def verify_generated(self, model_id, sha256): assert hashlib.sha256(self.uploaded).hexdigest() == sha256
    def finalize(self, reservation, **values):
        self.saved = {"id": MODEL_ID, "name": values["name"], "model_year": values["model_year"],
            "start_month": 1, "end_month": 12, "is_published": False, "is_default": False,
            "workbook_sha256": values["sha256"], "source_kind": "forecast_generated",
            "source_model_id": BASE_ID, "forecast_generation_id": GENERATION_ID,
            "generation_input_fingerprint": self.fingerprint}
        return self.saved
    def remove_generated(self, model_id): self.uploaded = b""
    def record_failure(self, *args, **kwargs): pass
    def get_model(self, model_id): return self.saved


class Engine:
    def __init__(self, source, mapping): self.source = Path(source)
    def run(self, request, destination):
        Path(destination).write_bytes(self.source.read_bytes() + bytes([request.month]))
        return SimpleNamespace(validations=[{"ok": True}])


def service(gateway: Gateway):
    sessions = AccessCodeSessionService(viewer_code="viewer", admin_code="admin",
        actor_namespace_secret="x" * 32)
    ticket = sessions.login("admin")
    mapping = {"sales": {"LC": {}}, "production": {"LC": 1, "FS_SW": 2},
               "mcm": {}, "manufacturing_input_rows": [], "sga_input_rows": []}
    return ForecastGenerationService(sessions, gateway,
        ResultProvenance("1.1.0", "analysis-v1", "b" * 64, "1"), "mapping.json", mapping), ticket.session_id


def request(*, key="key", amount=100):
    return ForecastGenerateRequest(BASE_ID, "2026 Forecast", 2026, "V1", 7, 7,
        (ForecastMonthInput(7, (ForecastSalesInput("LC", 10, amount),
            ForecastSalesInput("UF_MBR", 0, 0), ForecastSalesInput("IX", 0, 0),
            ForecastSalesInput("OTHER", 0, 0)),
            (ForecastQuantityInput("LC", 8), ForecastQuantityInput("FS_SW", 3))),), key)


@patch("forecast.bff.forecast_orchestration.infer_workbook_year", return_value=2026)
@patch("forecast.bff.forecast_orchestration.extract_period_types", return_value={"7": "추정"})
@patch("forecast.bff.forecast_orchestration.mapping_hash", return_value="b" * 64)
@patch("forecast.bff.forecast_orchestration.ForecastEngine", Engine)
def test_exact_generated_bytes_sha_draft_and_idempotent_replay(_mapping_hash, _periods, _year):
    gateway = Gateway(); target, session = service(gateway)
    gateway.download_base = lambda reservation: b"base"
    # Reservation pins this hash; update the fixture to the exact downloaded bytes.
    original_reserve = gateway.reserve
    def reserve(**kwargs):
        value = original_reserve(**kwargs)
        return ForecastReservation(value.generation_id, value.model_id, value.status,
            value.lease_token, value.replayed, value.base_bucket, value.base_path,
            hashlib.sha256(b"base").hexdigest())
    gateway.reserve = reserve
    first = target.generate(session, request())
    assert first.model_id == MODEL_ID
    assert first.is_published is False and first.is_default is False
    assert first.workbook_sha256 == hashlib.sha256(b"base\x07").hexdigest()
    second = target.generate(session, request())
    assert second.model_id == first.model_id and second.idempotency_replayed
    assert gateway.reservations == 2


def test_validation_rejects_viewer_bad_period_unknown_product_and_negative_values():
    gateway = Gateway(); target, admin_session = service(gateway)
    viewer_session = target._sessions.login("viewer").session_id
    with patch("forecast.bff.forecast_orchestration.mapping_hash", return_value="b" * 64), pytest.raises(BffError) as denied:
        target.generate(viewer_session, request())
    assert denied.value.code == ApiErrorCode.FORBIDDEN
    bad = ForecastGenerateRequest(BASE_ID, "x", 2026, "V1", 8, 7,
        (ForecastMonthInput(8, (ForecastSalesInput("UNKNOWN", -1, 0),), ()),), "key")
    with patch("forecast.bff.forecast_orchestration.mapping_hash", return_value="b" * 64), pytest.raises(BffError) as invalid:
        target.generate(admin_session, bad)
    assert invalid.value.code == ApiErrorCode.VALIDATION_ERROR


def test_migration_011_is_additive_race_safe_private_and_strict_default():
    sql = Path("supabase/migrations/202608090011_forecast_react_vertical_slice.sql").read_text(encoding="utf-8").lower()
    assert "create table public.forecast_generation_requests" in sql
    assert "pg_advisory_xact_lock" in sql
    assert "unique (idempotency_actor, idempotency_key)" in sql
    assert "source_kind" in sql and "forecast_generated" in sql
    assert "false, false, false" in sql
    assert "available.is_default" in sql
    assert "order by available.is_default" not in sql
    assert "from public, anon, authenticated" in sql
    assert "to service_role" in sql
    assert "workbook_path" not in sql.split("create or replace function public.get_pnl_dashboard_viewer", 1)[1].split("revoke all", 1)[0]


@patch("forecast.bff.forecast_orchestration.infer_workbook_year", return_value=2026)
@patch("forecast.bff.forecast_orchestration.extract_period_types", return_value={"7": "추정"})
@patch("forecast.bff.forecast_orchestration.mapping_hash", return_value="b" * 64)
@patch("forecast.bff.forecast_orchestration.ForecastEngine", Engine)
def test_same_key_changed_payload_conflicts(_mapping_hash, _periods, _year):
    gateway = Gateway(); target, session = service(gateway)
    gateway.download_base = lambda reservation: b"base"
    original = gateway.reserve
    def reserve(**kwargs):
        value = original(**kwargs)
        return ForecastReservation(value.generation_id, value.model_id, value.status, value.lease_token,
            value.replayed, value.base_bucket, value.base_path, hashlib.sha256(b"base").hexdigest())
    gateway.reserve = reserve
    target.generate(session, request())
    with pytest.raises(BffError) as conflict:
        target.generate(session, request(amount=101))
    assert conflict.value.code == ApiErrorCode.IDEMPOTENCY_CONFLICT


@patch("forecast.bff.forecast_orchestration.infer_workbook_year", return_value=2026)
@patch("forecast.bff.forecast_orchestration.extract_period_types", return_value={"7": "추정"})
@patch("forecast.bff.forecast_orchestration.mapping_hash", return_value="b" * 64)
@patch("forecast.bff.forecast_orchestration.ForecastEngine", Engine)
def test_finalize_uncertainty_never_removes_possibly_committed_source(_mapping_hash, _periods, _year):
    gateway = Gateway(); target, session = service(gateway)
    gateway.download_base = lambda reservation: b"base"
    original = gateway.reserve
    gateway.reserve = lambda **kwargs: replace_reservation(original(**kwargs), hashlib.sha256(b"base").hexdigest())
    removed = []
    gateway.remove_generated = lambda model_id: removed.append(model_id)
    gateway.finalize = lambda *args, **kwargs: (_ for _ in ()).throw(ForecastFinalizeUncertainError())
    with pytest.raises(BffError) as uncertain:
        target.generate(session, request())
    assert uncertain.value.code == ApiErrorCode.INGESTION_CLEANUP_REQUIRED
    assert removed == []


def replace_reservation(value, sha):
    return ForecastReservation(value.generation_id, value.model_id, value.status, value.lease_token,
        value.replayed, value.base_bucket, value.base_path, sha)
