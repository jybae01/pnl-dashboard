from dataclasses import dataclass
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from forecast.bff.application import (
    AnalysisModelListService,
    AnalysisSubmissionService,
    JobQueryService,
    ResultQueryService,
    TrustedBffApplication,
)
from forecast.bff.auth import AccessCodeSessionService
from forecast.bff.errors import ApiErrorCode, BffError
from forecast.bff.forecast_orchestration import ForecastQuantityInput
from forecast.bff.production_allocation import (
    BACK_PROCESS,
    CANONICAL_PRODUCTION_CODES,
    FRONT_PROCESS,
    UNIT_LENGTH_M,
    UNIT_PCS,
    BusinessProductionInput,
    CanonicalProductionQuantity,
    ProductionAllocationBatch,
    ProductionAllocationResult,
    allocate_production,
)
from forecast.bff.http import HttpBffSettings, create_http_bff
from forecast.provenance import ResultProvenance

from tests.test_bff_http import (
    BASE,
    COMP,
    Gateway,
    FakeEvidence,
    FakeForecast,
    FakeForecastMetadata,
    FakeHistory,
    FakePnlDashboard,
    FakePresentation,
)


PROVENANCE = ResultProvenance("engine", "mapping", "a" * 64, "1")


@dataclass
class AllocationDouble:
    result_factory: object
    calls: list[tuple[str, str, tuple[BusinessProductionInput, ...]]]

    def allocate(self, session_id, base_model_id, inputs):
        values = tuple(inputs)
        self.calls.append((session_id, base_model_id, values))
        return self.result_factory(values)


def _canonical(month: int, values: tuple[int, ...]):
    return ProductionAllocationResult(
        base_model_id=BASE,
        month=month,
        base_workbook_sha256="b" * 64,
        source_sw_pair=None,
        source_bw_pair=None,
        business_totals=(),
        canonical_quantities=tuple(
            CanonicalProductionQuantity(code, Decimal(quantity), UNIT_PCS if code != "FS_SW" and code != "FS_BW" and code != "FS_TW" else UNIT_LENGTH_M)
            for code, quantity in zip(CANONICAL_PRODUCTION_CODES, values)
        ),
    )


def make_business_fixture(allocation, forecast=None):
    sessions = AccessCodeSessionService(
        viewer_code="viewer-code", admin_code="admin-code",
        actor_namespace_secret="actor-namespace-secret-at-least-32-chars", ttl_seconds=3600,
    )
    gateway = Gateway()
    repository = SimpleNamespace(list=lambda: [
        SimpleNamespace(id=BASE, name="Base", model_type="PLAN", year=2026,
                        start_month=1, end_month=12, is_published=True,
                        is_default=True, workbook_sha256="b" * 64),
        SimpleNamespace(id=COMP, name="Comparison", model_type="ACTUAL", year=2026,
                        start_month=1, end_month=12, is_published=True,
                        is_default=False, workbook_sha256="c" * 64),
    ])
    forecast = forecast or FakeForecast()
    application = TrustedBffApplication(
        sessions,
        AnalysisSubmissionService(sessions, gateway, PROVENANCE),
        JobQueryService(sessions, gateway),
        ResultQueryService(sessions, gateway, supported_result_schema_versions=("1",)),
        AnalysisModelListService(sessions, repository),
        evidence=FakeEvidence(), history=FakeHistory(), presentation=FakePresentation(),
        pnl_dashboard=FakePnlDashboard(), forecast_generation=forecast,
        forecast_input_metadata=FakeForecastMetadata(),
        forecast_production_allocation=allocation,
    )
    app = create_http_bff(
        application,
        settings=HttpBffSettings(environment="test", csrf_secret="csrf-secret-at-least-32-characters"),
    )
    return TestClient(app), forecast


def _business_rows(quantity=1):
    return [
        {"process": FRONT_PROCESS, "product_group": "SW", "quantity": quantity, "unit": UNIT_LENGTH_M},
        {"process": FRONT_PROCESS, "product_group": "BW", "quantity": quantity, "unit": UNIT_LENGTH_M},
        {"process": FRONT_PROCESS, "product_group": "TW", "quantity": quantity, "unit": UNIT_LENGTH_M},
        {"process": BACK_PROCESS, "product_group": "SW", "quantity": quantity, "unit": UNIT_PCS},
        {"process": BACK_PROCESS, "product_group": "BW", "quantity": quantity, "unit": UNIT_PCS},
        {"process": BACK_PROCESS, "product_group": "LC", "quantity": quantity, "unit": UNIT_PCS},
    ]


def _body(months, month_overrides=None):
    month_overrides = month_overrides or {}
    return {
        "base_model_id": BASE, "name": "Forecast", "model_year": 2026,
        "version": "V1", "start_month": months[0], "end_month": months[-1],
        "months": [
            {"month": month, "sales": [], "mcm": [], **month_overrides.get(month, {})}
            for month in months
        ],
        "idempotency_key": "business-http-test",
    }


def test_legacy_canonical_path_remains_unchanged_and_does_not_allocate():
    allocation = AllocationDouble(lambda values: pytest.fail("legacy input must not allocate"), [])
    client, forecast = make_business_fixture(allocation)
    assert client.post("/api/session/login", json={"access_code": "admin-code"}).status_code == 200
    body = _body([7], {7: {"production": [{"product_code": code, "quantity": index} for index, code in enumerate(CANONICAL_PRODUCTION_CODES)]}})
    response = client.post("/api/admin/forecasts", json=body, headers={"X-CSRF-Token": client.cookies.get("pnl_csrf")})
    assert response.status_code == 200
    assert allocation.calls == []
    assert tuple(item.product_code for item in forecast.last_request.months[0].production) == CANONICAL_PRODUCTION_CODES


def test_business_path_allocates_once_with_exact_session_model_and_forwards_canonical():
    allocation = AllocationDouble(lambda values: _canonical(values[0].month, tuple(range(1, 9))), [])
    client, forecast = make_business_fixture(allocation)
    client.post("/api/session/login", json={"access_code": "admin-code"})
    body = _body([7], {7: {"business_production": _business_rows()}})
    response = client.post("/api/admin/forecasts", json=body, headers={"X-CSRF-Token": client.cookies.get("pnl_csrf")})
    assert response.status_code == 200
    assert len(allocation.calls) == 1
    session, model_id, inputs = allocation.calls[0]
    assert session and model_id == BASE
    assert tuple(item.month for item in inputs) == (7,) * 6
    assert tuple(item.product_code for item in forecast.last_request.months[0].production) == CANONICAL_PRODUCTION_CODES
    assert tuple(item.quantity for item in forecast.last_request.months[0].production) == tuple(float(value) for value in range(1, 9))


def test_http_preserves_legacy_omission_and_forwards_explicit_actual_mode():
    allocation = AllocationDouble(
        lambda values: _canonical(values[0].month, tuple(range(1, 9))), []
    )
    client, forecast = make_business_fixture(allocation)
    client.post("/api/session/login", json={"access_code": "admin-code"})
    headers = {"X-CSRF-Token": client.cookies.get("pnl_csrf")}

    legacy = _body([7], {7: {"business_production": _business_rows()}})
    assert client.post("/api/admin/forecasts", json=legacy, headers=headers).status_code == 200
    legacy_month = forecast.last_request.months[0]
    assert legacy_month.new_business_goods_cogs_mode is None
    assert legacy_month.new_business_goods_cogs is None

    explicit = _body([7], {7: {
        "business_production": _business_rows(),
        "new_business_goods_cogs_mode": "ACTUAL_YTD_DEFAULT",
    }})
    explicit["idempotency_key"] = "business-http-explicit-mode"
    assert client.post("/api/admin/forecasts", json=explicit, headers=headers).status_code == 200
    explicit_month = forecast.last_request.months[0]
    assert explicit_month.new_business_goods_cogs_mode == "ACTUAL_YTD_DEFAULT"
    assert explicit_month.new_business_goods_cogs is None


def test_business_fixture_reaches_existing_forecast_contract_with_expected_canonical_values():
    allocation = AllocationDouble(
        lambda values: allocate_production(
            values,
            {7: {"SW400": 600, "SW440": 400, "BW400": 300, "BW440": 700}},
            base_model_id=BASE,
            base_workbook_sha256="b" * 64,
        ),
        [],
    )
    client, forecast = make_business_fixture(allocation)
    client.post("/api/session/login", json={"access_code": "admin-code"})
    rows = _business_rows()
    for row, quantity in zip(rows, (100, 200, 300, 1000, 2000, 300)):
        row["quantity"] = quantity
    body = _body([7], {7: {"business_production": rows}})

    response = client.post(
        "/api/admin/forecasts", json=body,
        headers={"X-CSRF-Token": client.cookies.get("pnl_csrf")},
    )

    assert response.status_code == 200
    assert tuple(item.quantity for item in forecast.last_request.months[0].production) == (
        600.0, 400.0, 600.0, 1400.0, 300.0, 100.0, 200.0, 300.0,
    )


def test_business_multi_months_share_one_allocation_call_and_keep_months():
    def factory(values):
        return ProductionAllocationBatch(tuple(
            _canonical(month, tuple(month + index for index in range(8)))
            for month in sorted({item.month for item in values})
        ))

    allocation = AllocationDouble(factory, [])
    client, forecast = make_business_fixture(allocation)
    client.post("/api/session/login", json={"access_code": "admin-code"})
    body = _body([7, 8], {7: {"business_production": _business_rows(7)}, 8: {"business_production": _business_rows(8)}})
    response = client.post("/api/admin/forecasts", json=body, headers={"X-CSRF-Token": client.cookies.get("pnl_csrf")})
    assert response.status_code == 200
    assert len(allocation.calls) == 1
    assert tuple(item.month for item in allocation.calls[0][2]) == (7,) * 6 + (8,) * 6
    assert [month.month for month in forecast.last_request.months] == [7, 8]
    assert forecast.last_request.months[1].production[0].quantity == 8.0


def test_duplicate_business_months_fail_validation_before_allocation():
    allocation = AllocationDouble(lambda values: pytest.fail("duplicate months must not allocate"), [])
    client, _forecast = make_business_fixture(allocation)
    client.post("/api/session/login", json={"access_code": "admin-code"})
    body = _body([7, 7], {7: {"business_production": _business_rows()}})
    response = client.post(
        "/api/admin/forecasts", json=body,
        headers={"X-CSRF-Token": client.cookies.get("pnl_csrf")},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == ApiErrorCode.VALIDATION_ERROR.value
    assert allocation.calls == []


@pytest.mark.parametrize(
    "month_input",
    [
        {"sales": [], "mcm": []},
        {"sales": [], "mcm": [], "production": [], "business_production": _business_rows()},
    ],
)
def test_business_mode_requires_exactly_one_input(month_input):
    allocation = AllocationDouble(lambda values: pytest.fail("invalid mode must not allocate"), [])
    client, _forecast = make_business_fixture(allocation)
    client.post("/api/session/login", json={"access_code": "admin-code"})
    body = _body([7], {7: month_input})
    response = client.post("/api/admin/forecasts", json=body, headers={"X-CSRF-Token": client.cookies.get("pnl_csrf")})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == ApiErrorCode.VALIDATION_ERROR.value


def test_allocation_bff_error_is_propagated_and_viewer_csrf_boundaries_remain():
    class InvalidAllocation:
        def allocate(self, *_args):
            raise BffError(ApiErrorCode.VALIDATION_ERROR, "Production input is invalid")

    client, _forecast = make_business_fixture(InvalidAllocation())
    assert client.post("/api/admin/forecasts", json=_body([7], {7: {"business_production": _business_rows()}})).status_code == 401
    client.post("/api/session/login", json={"access_code": "viewer-code"})
    body = _body([7], {7: {"business_production": _business_rows()}})
    assert client.post("/api/admin/forecasts", json=body, headers={"X-CSRF-Token": client.cookies.get("pnl_csrf")}).status_code == 403

    admin, _forecast = make_business_fixture(InvalidAllocation())
    admin.post("/api/session/login", json={"access_code": "admin-code"})
    body = _body([7], {7: {"business_production": _business_rows()}})
    missing_csrf = admin.post("/api/admin/forecasts", json=body)
    assert missing_csrf.status_code == 403
    propagated = admin.post("/api/admin/forecasts", json=body, headers={"X-CSRF-Token": admin.cookies.get("pnl_csrf")})
    assert propagated.status_code == 422
    assert propagated.json()["error"]["code"] == ApiErrorCode.VALIDATION_ERROR.value


def test_business_input_idempotency_replay_preserves_key_and_returns_replay_flag():
    class ReplayForecast(FakeForecast):
        def __init__(self):
            super().__init__()
            self.requests = []

        def generate(self, session_id, request):
            self.requests.append(request)
            response = dict(super().generate(session_id, request))
            response["idempotency_replayed"] = len(self.requests) > 1
            return response

    allocation = AllocationDouble(lambda values: _canonical(values[0].month, tuple(range(1, 9))), [])
    forecast = ReplayForecast()
    client, _ = make_business_fixture(allocation, forecast=forecast)
    client.post("/api/session/login", json={"access_code": "admin-code"})
    body = _body([7], {7: {"business_production": _business_rows()}})
    headers = {"X-CSRF-Token": client.cookies.get("pnl_csrf")}
    first = client.post("/api/admin/forecasts", json=body, headers=headers)
    second = client.post("/api/admin/forecasts", json=body, headers=headers)
    assert first.status_code == second.status_code == 200
    assert second.json()["idempotency_replayed"] is True
    assert [item.idempotency_key for item in forecast.requests] == [body["idempotency_key"]] * 2


def test_malformed_allocator_result_fails_closed_as_integrity_error():
    allocation = AllocationDouble(lambda _values: object(), [])
    client, _ = make_business_fixture(allocation)
    client.post("/api/session/login", json={"access_code": "admin-code"})
    body = _body([7], {7: {"business_production": _business_rows()}})
    response = client.post(
        "/api/admin/forecasts", json=body,
        headers={"X-CSRF-Token": client.cookies.get("pnl_csrf")},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == ApiErrorCode.INPUT_INTEGRITY_MISMATCH.value
