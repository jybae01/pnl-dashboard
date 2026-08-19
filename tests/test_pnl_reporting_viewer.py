from __future__ import annotations

import copy
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from forecast.bff.application import TrustedBffApplication
from forecast.bff.auth import AccessCodeSessionService
from forecast.bff.errors import BffError
from forecast.bff.http import HttpBffSettings, create_http_bff
from forecast.bff.pnl_reporting_read import (
    CANONICAL_SCHEMA_VERSION,
    PnlReportingViewerService,
    SupabasePnlReportingReadGateway,
)
from forecast.reporting import DatasetType
from forecast.reporting.models import (
    CanonicalMonthlySeries,
    CanonicalProductGroup,
    CanonicalSheet,
    PnlReportingCanonicalInput,
)
from forecast.reporting.registry import (
    MANUFACTURING_COGS_ROWS,
    MONTHLY_PNL_ROWS,
    PRODUCT_GROUPS,
    PRODUCT_PNL_ROWS,
    SGA_ROWS,
    SHEET_MANUFACTURING_COGS,
    SHEET_MONTHLY_PNL,
    SHEET_PRODUCT_PNL,
    SHEET_SGA,
    TEMPLATE_VERSION,
)


PLAN_ID = "11111111-1111-4111-8111-111111111111"
ACTUAL_ID = "22222222-2222-4222-8222-222222222222"


class SnapshotGateway:
    def __init__(self, source):
        self.source = source
        self.calls = []

    def load_active(self, reporting_year):
        self.calls.append(reporting_year)
        return copy.deepcopy(self.source)


def _sessions():
    return AccessCodeSessionService(
        viewer_code="viewer-code",
        admin_code="admin-code",
        actor_namespace_secret="stable-actor-namespace-secret-32chars",
        ttl_seconds=3600,
    )


def _canonical(
    dataset_type: DatasetType,
    *,
    through: int | None = None,
    zero_revenue_month: int | None = None,
) -> PnlReportingCanonicalInput:
    def series(key: str, base: int, *, revenue: bool = False) -> CanonicalMonthlySeries:
        values = []
        for month in range(1, 13):
            available = dataset_type is DatasetType.PLAN or (
                through is not None and month <= through
            )
            value = 0 if revenue and month == zero_revenue_month else base
            values.append(value if available else None)
        return CanonicalMonthlySeries(key, tuple(values))

    pnl_rows = tuple(
        series(
            definition.key,
            0 if definition.key == "rev_rebate" else (
                10 if definition.key == "rev_product" else 2
            ),
            revenue=definition.key.startswith("rev_"),
        )
        for definition in MONTHLY_PNL_ROWS
        if definition.is_input
    )
    cogs_rows = tuple(
        series(definition.key, 2)
        for definition in MANUFACTURING_COGS_ROWS
        if definition.is_input
    )
    sga_rows = tuple(
        series(definition.key, 1)
        for definition in SGA_ROWS
        if definition.is_input
    )
    product_groups = tuple(
        CanonicalProductGroup(
            group.key,
            tuple(
                series(
                    definition.key,
                    5 if definition.key == "revenue" else (
                        10 if definition.key == "volume" else 2
                    ),
                )
                for definition in PRODUCT_PNL_ROWS
                if definition.product_group_key == group.key and definition.is_input
            ),
        )
        for group in PRODUCT_GROUPS
    )
    return PnlReportingCanonicalInput(
        template_version=TEMPLATE_VERSION,
        dataset_type=dataset_type,
        reporting_year=2026,
        actual_through_month=through,
        sheets=(
            CanonicalSheet(SHEET_MONTHLY_PNL, rows=pnl_rows),
            CanonicalSheet(SHEET_MANUFACTURING_COGS, rows=cogs_rows),
            CanonicalSheet(SHEET_SGA, rows=sga_rows),
            CanonicalSheet(SHEET_PRODUCT_PNL, product_groups=product_groups),
        ),
    )


def _dataset(
    dataset_type: DatasetType,
    *,
    through: int | None = None,
    pointer_type: DatasetType | None = None,
    stored_type: DatasetType | None = None,
    zero_revenue_month: int | None = None,
):
    pointer_type = pointer_type or dataset_type
    stored_type = stored_type or dataset_type
    dataset_id = PLAN_ID if dataset_type is DatasetType.PLAN else ACTUAL_ID
    canonical = _canonical(
        stored_type,
        through=through if stored_type is DatasetType.ACTUAL else None,
        zero_revenue_month=zero_revenue_month,
    )
    return {
        "pointer_reporting_year": 2026,
        "pointer_dataset_type": pointer_type.value,
        "pointer_dataset_id": dataset_id,
        "dataset_id": dataset_id,
        "dataset_type": stored_type.value,
        "reporting_year": 2026,
        "canonical_schema_version": CANONICAL_SCHEMA_VERSION,
        "template_version": TEMPLATE_VERSION,
        "actual_through_month": through if stored_type is DatasetType.ACTUAL else None,
        "canonical_payload": canonical.to_dict(),
        "uploaded_at": (
            "2026-08-19T01:00:00+00:00"
            if dataset_type is DatasetType.ACTUAL
            else "2026-08-19T00:00:00+00:00"
        ),
    }


def _source(*datasets, years=(2026,)):
    return {"available_years": list(years), "datasets": list(datasets)}


def _service(source):
    sessions = _sessions()
    gateway = SnapshotGateway(source)
    return sessions, gateway, PnlReportingViewerService(sessions, gateway)


@pytest.mark.parametrize(
    ("datasets", "expected"),
    [
        ((), "MISSING_BOTH"),
        ((_dataset(DatasetType.PLAN),), "MISSING_ACTUAL"),
        ((_dataset(DatasetType.ACTUAL, through=6),), "MISSING_PLAN"),
        (
            (_dataset(DatasetType.PLAN), _dataset(DatasetType.ACTUAL, through=6)),
            "READY",
        ),
    ],
)
def test_gap_matrix_and_ready_are_explicit_http_200_business_states(datasets, expected):
    years = (2026, 2025, 2024) if datasets else (2025, 2024)
    sessions, gateway, service = _service(_source(*datasets, years=years))
    ticket = sessions.login("viewer-code")
    response = service.viewer_read(ticket.session_id, 2026)

    assert response["dtoVersion"] == "1"
    assert response["reportingState"] == expected
    assert response["state"] == ("DATA_READY" if expected == "READY" else "REPORTING_GAP")
    assert (response["report"] is not None) is (expected == "READY")
    assert response["metadata"]["selectedYear"] == 2026
    assert response["metadata"]["availableYears"] == list(years)
    assert response["metadata"]["plan"]["exists"] is any(
        row["pointer_dataset_type"] == "PLAN" for row in datasets
    )
    assert response["metadata"]["actual"]["exists"] is any(
        row["pointer_dataset_type"] == "ACTUAL" for row in datasets
    )
    assert gateway.calls == [2026]


def test_available_years_are_descending_active_union_and_gap_keeps_selector_metadata():
    sessions, _, service = _service(_source(years=(2025, 2024)))
    response = service.viewer_read(sessions.login("admin-code").session_id, 2026)
    assert response == {
        "dtoVersion": "1",
        "state": "REPORTING_GAP",
        "reportingState": "MISSING_BOTH",
        "metadata": {
            "selectedYear": 2026,
            "availableYears": [2025, 2024],
            "plan": {"exists": False, "datasetId": None, "lastUpdated": None},
            "actual": {
                "exists": False,
                "datasetId": None,
                "actualThroughMonth": None,
                "lastUpdated": None,
            },
            "lastUpdated": None,
        },
        "report": None,
    }


def test_ready_response_is_lossless_structural_dto_with_full_twelve_month_cogs():
    sessions, _, service = _service(_source(
        _dataset(DatasetType.PLAN),
        _dataset(DatasetType.ACTUAL, through=6),
        years=(2026, 2025, 2024),
    ))
    response = service.viewer_read(sessions.login("viewer-code").session_id, 2026)
    report = response["report"]

    assert response["metadata"]["lastUpdated"] == "2026-08-19T01:00:00Z"
    assert report["identity"]["availableYears"] == [2026, 2025, 2024]
    assert report["identity"]["actualThroughMonth"] == 6
    assert len(report["identity"]["periods"]) == 12
    assert [item["key"] for item in report["kpis"]] == [
        "revenue", "operating_profit", "adjusted_operating_profit"
    ]
    assert len(report["monthlyTrends"]) == 12
    assert len(report["monthlyDataRows"]) == 8
    assert len(report["pnlRows"]) == 25
    assert len(report["cogsRows"]) == 5
    assert all(len(row["months"]) == 12 for row in report["cogsRows"])
    assert all(len(row["cells"]) == 26 for row in report["cogsRows"])
    assert len(report["sgaRows"]) == 23
    assert {segment["key"]: len(segment["rows"]) for segment in report["productSegments"]} == {
        "SW": 10, "BW": 10, "LC": 10, "FS": 10, "NEW_BUSINESS": 8
    }
    lc = next(item for item in report["productSegments"] if item["key"] == "LC")
    fs = next(item for item in report["productSegments"] if item["key"] == "FS")
    new_business = next(
        item for item in report["productSegments"] if item["key"] == "NEW_BUSINESS"
    )
    assert (lc["dimensionLabel"], lc["businessUnit"]) == ("4-inch", "PCS")
    assert (fs["dimensionLabel"], fs["businessUnit"]) == ("LENGTH", "m")
    assert new_business["dimensionLabel"] is None
    assert new_business["businessUnit"] is None
    assert {row["key"] for row in new_business["rows"]}.isdisjoint({"volume", "asp"})
    mixed = next(row for row in report["pnlRows"] if row["key"] == "sales_volume")
    assert all(value is None for value in mixed["actualValues"])
    assert "comparisonByPeriod" in report["pnlRows"][0]
    assert "ytd" in report["pnlRows"][0]
    assert "customRangeComparisons" in report["pnlRows"][0]
    assert abs(report["monthlyTrends"][0]["actualOperatingMargin"]) > 1


@pytest.mark.parametrize("through", [1, 6, 12])
def test_actual_through_preserves_dynamic_actual_only_future_null_and_zero(through):
    zero_month = 1 if through == 1 else None
    sessions, _, service = _service(_source(
        _dataset(DatasetType.PLAN),
        _dataset(DatasetType.ACTUAL, through=through, zero_revenue_month=zero_month),
    ))
    report = service.viewer_read(sessions.login("viewer-code").session_id, 2026)["report"]
    identity = report["identity"]
    assert identity["actualThroughMonth"] == through
    assert len(identity["actualPeriodKeys"]) == through
    assert [month["actualAvailable"] for month in report["monthlyTrends"]] == [
        month <= through for month in range(1, 13)
    ]
    assert all(
        month["actualRevenue"] is None
        and month["actualOperatingProfit"] is None
        and month["actualOperatingMargin"] is None
        for month in report["monthlyTrends"][through:]
    )
    assert all(len(row["actualOnly"]) == through + 1 for row in report["pnlRows"])
    assert all(
        month["amount"] is None
        for row in report["cogsRows"]
        for month in row["months"][through:]
    )
    if through == 1:
        assert report["kpis"][0]["amount"] == 0
        assert report["kpis"][0]["amountText"] == "0"
        assert report["monthlyTrends"][0]["actualRevenue"] == 0


@pytest.mark.parametrize(
    "mutate",
    [
        lambda row: row.update(dataset_type="ACTUAL"),
        lambda row: row.update(reporting_year=2025),
        lambda row: row.update(canonical_schema_version="OTHER"),
        lambda row: row.update(dataset_id=ACTUAL_ID),
        lambda row: row["canonical_payload"]["sheets"][SHEET_MONTHLY_PNL].pop("rev_product"),
    ],
)
def test_pointer_or_canonical_integrity_failure_is_not_a_reporting_gap(mutate):
    row = _dataset(DatasetType.PLAN)
    mutate(row)
    sessions, _, service = _service(_source(row))
    with pytest.raises(BffError) as caught:
        service.viewer_read(sessions.login("viewer-code").session_id, 2026)
    assert caught.value.code.value == "INPUT_INTEGRITY_MISMATCH"


@pytest.mark.parametrize(
    "case",
    [
        "plan_applicable_null",
        "actual_applicable_null",
        "unknown_sheet",
        "unknown_row",
        "unknown_product_group",
        "unknown_product_metric",
    ],
)
def test_persisted_canonical_schema_or_applicable_null_is_integrity_error(case):
    plan = _dataset(DatasetType.PLAN)
    actual = _dataset(DatasetType.ACTUAL, through=6)
    plan_sheets = plan["canonical_payload"]["sheets"]
    actual_sheets = actual["canonical_payload"]["sheets"]
    if case == "plan_applicable_null":
        plan_sheets[SHEET_MONTHLY_PNL]["rev_product"]["01"] = None
        datasets = (plan, actual)
    elif case == "actual_applicable_null":
        actual_sheets[SHEET_MONTHLY_PNL]["rev_product"]["01"] = None
        datasets = (plan, actual)
    elif case == "unknown_sheet":
        plan_sheets["99_UNKNOWN"] = {}
        datasets = (plan,)
    elif case == "unknown_row":
        plan_sheets[SHEET_MONTHLY_PNL]["unknown"] = copy.deepcopy(
            plan_sheets[SHEET_MONTHLY_PNL]["rev_product"]
        )
        datasets = (plan,)
    elif case == "unknown_product_group":
        plan_sheets[SHEET_PRODUCT_PNL]["UNKNOWN"] = copy.deepcopy(
            plan_sheets[SHEET_PRODUCT_PNL]["SW"]
        )
        datasets = (plan,)
    else:
        plan_sheets[SHEET_PRODUCT_PNL]["SW"]["unknown"] = copy.deepcopy(
            plan_sheets[SHEET_PRODUCT_PNL]["SW"]["revenue"]
        )
        datasets = (plan,)

    sessions, _, service = _service(_source(*datasets))
    with pytest.raises(BffError) as caught:
        service.viewer_read(sessions.login("viewer-code").session_id, 2026)
    assert caught.value.code.value == "INPUT_INTEGRITY_MISMATCH"


def test_active_pointer_to_superseded_dataset_is_integrity_error():
    plan = _dataset(DatasetType.PLAN)
    plan["superseded_at"] = "2026-08-19T02:00:00+00:00"
    plan["superseded_by_dataset_id"] = ACTUAL_ID
    sessions, _, service = _service(_source(plan))
    with pytest.raises(BffError) as caught:
        service.viewer_read(sessions.login("viewer-code").session_id, 2026)
    assert caught.value.code.value == "INPUT_INTEGRITY_MISMATCH"


def _http_client(source):
    sessions = _sessions()
    service = PnlReportingViewerService(sessions, SnapshotGateway(source))
    application = TrustedBffApplication(
        sessions=sessions,
        submissions=object(),
        jobs=object(),
        results=object(),
        pnl_reporting_read=service,
    )
    return TestClient(create_http_bff(
        application,
        settings=HttpBffSettings(
            environment="test",
            csrf_secret="csrf-secret-at-least-32-characters",
        ),
    ))


def test_viewer_endpoint_auth_required_year_no_csrf_and_private_no_store():
    source = _source(_dataset(DatasetType.PLAN), _dataset(DatasetType.ACTUAL, through=6))
    client = _http_client(source)
    assert client.get("/api/viewer/pnl-reporting?year=2026").status_code == 401

    assert client.post("/api/session/login", json={"access_code": "viewer-code"}).status_code == 200
    viewer = client.get("/api/viewer/pnl-reporting?year=2026")
    assert viewer.status_code == 200
    assert viewer.headers["cache-control"] == "private, no-store"
    assert viewer.json()["reportingState"] == "READY"

    assert client.post("/api/session/login", json={"access_code": "admin-code"}).status_code == 200
    admin = client.get("/api/viewer/pnl-reporting?year=2026")
    assert admin.status_code == 200
    assert admin.json()["reportingState"] == "READY"

    assert client.get("/api/viewer/pnl-reporting").status_code == 422
    assert client.get("/api/viewer/pnl-reporting?year=not-a-year").status_code == 422
    assert client.get("/api/viewer/pnl-reporting?year=1999").status_code == 422


@pytest.mark.parametrize(
    ("datasets", "reporting_state"),
    [
        ((), "MISSING_BOTH"),
        ((_dataset(DatasetType.PLAN),), "MISSING_ACTUAL"),
        ((_dataset(DatasetType.ACTUAL, through=6),), "MISSING_PLAN"),
        (
            (_dataset(DatasetType.PLAN), _dataset(DatasetType.ACTUAL, through=6)),
            "READY",
        ),
    ],
)
def test_all_reporting_states_are_http_200(datasets, reporting_state):
    years = (2026,) if datasets else ()
    client = _http_client(_source(*datasets, years=years))
    client.post("/api/session/login", json={"access_code": "viewer-code"})
    response = client.get("/api/viewer/pnl-reporting?year=2026")
    assert response.status_code == 200
    assert response.json()["reportingState"] == reporting_state
    assert (response.json()["report"] is not None) is (reporting_state == "READY")


def test_http_integrity_failure_is_safe_409_not_gap():
    broken = _dataset(DatasetType.PLAN)
    broken["dataset_type"] = "ACTUAL"
    client = _http_client(_source(broken))
    client.post("/api/session/login", json={"access_code": "viewer-code"})
    response = client.get("/api/viewer/pnl-reporting?year=2026")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INPUT_INTEGRITY_MISMATCH"
    assert "traceback" not in response.text.casefold()
    assert "REPORTING_GAP" not in response.text


def test_malformed_gateway_payload_is_a_safe_integrity_error():
    sessions, _, service = _service([])
    with pytest.raises(BffError) as caught:
        service.viewer_read(sessions.login("viewer-code").session_id, 2026)
    assert caught.value.code.value == "INPUT_INTEGRITY_MISMATCH"


def test_supabase_read_gateway_calls_only_the_narrow_rpc_and_never_storage():
    class Client:
        def __init__(self):
            self.calls = []

        @property
        def storage(self):
            raise AssertionError("viewer read must never access Storage")

        def rpc(self, name, params):
            self.calls.append((name, params))
            return SimpleNamespace(execute=lambda: SimpleNamespace(data={
                "available_years": [2026],
                "datasets": [],
            }))

    client = Client()
    gateway = SupabasePnlReportingReadGateway(client)
    assert gateway.load_active(2026) == {"available_years": [2026], "datasets": []}
    assert client.calls == [(
        "get_pnl_reporting_viewer_source",
        {"p_reporting_year": 2026},
    )]


def test_viewer_read_source_has_no_engine_analysis_legacy_storage_or_formula_leakage():
    source = Path("forecast/bff/pnl_reporting_read.py").read_text(encoding="utf-8").casefold()
    for forbidden in (
        "from ..reporting import",
        "forecast.engine",
        "from .analysis",
        "pnl_dashboard",
        "calculation_results",
        "is_default",
        "is_published",
        "parse_pnl_reporting_workbook",
        "load_workbook",
        ".storage",
        ".download(",
        "revenue_total",
        "ratio_percent",
        "variance_rate",
    ):
        assert forbidden not in source
