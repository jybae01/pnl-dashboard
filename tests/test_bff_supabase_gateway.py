from __future__ import annotations

import json
from pathlib import Path

import pytest

from forecast.bff import create_supabase_bff_application
from forecast.bff.gateway import (
    GatewayIdempotencyConflictError,
    SupabaseBffApplicationGateway,
)
from forecast.provenance import ResultProvenance


class Response:
    def __init__(self, data):
        self.data = data


class RpcCall:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error

    def execute(self):
        if self.error:
            raise self.error
        return Response(self.response)


class FakeClient:
    def __init__(self):
        self.calls = []
        self.responses = {}
        self.errors = {}

    def rpc(self, name, params):
        self.calls.append((name, params))
        return RpcCall(self.responses.get(name), self.errors.get(name))


def test_submit_uses_narrow_idempotent_rpc_and_no_created_by_fabrication():
    client = FakeClient()
    client.responses["create_durable_calculation_job_idempotent"] = [{
        "job_id": "job-1", "status": "pending", "idempotency_replayed": False,
    }]
    gateway = SupabaseBffApplicationGateway(client)
    provenance = ResultProvenance("engine", "mapping", "a" * 64, "1")

    result = gateway.submit_analysis(
        baseline_model_id="base",
        comparison_model_id="comparison",
        start_month=1,
        end_month=6,
        baseline_sales_fx=1480,
        comparison_sales_fx=1500,
        idempotency_actor="actor",
        idempotency_key="key",
        provenance=provenance,
        max_attempts=3,
    )

    name, params = client.calls[0]
    assert name == "create_durable_calculation_job_idempotent"
    assert result.job_id == "job-1" and not result.idempotency_replayed
    assert "p_created_by" not in params
    assert params["p_mapping_hash"] == "a" * 64


def test_factory_composes_explicit_server_only_boundary_without_environment_switch():
    app = create_supabase_bff_application(
        supabase_client=FakeClient(),
        viewer_code="viewer-secret",
        admin_code="admin-secret",
        actor_namespace_secret="stable-server-only-actor-namespace",
        provenance=ResultProvenance("engine", "mapping", "a" * 64, "1"),
    )

    ticket = app.login("admin-secret")
    assert app.validate_session(ticket.session_id).role == "admin"
    app.logout(ticket.session_id)


def test_factory_defaults_to_disabled_and_keeps_non_forecast_capabilities():
    mapping = json.loads(Path("config/model_mapping.json").read_text(encoding="utf-8"))
    app = create_supabase_bff_application(
        supabase_client=FakeClient(),
        viewer_code="viewer-secret",
        admin_code="admin-secret",
        actor_namespace_secret="stable-server-only-actor-namespace",
        provenance=ResultProvenance("engine", "mapping", "a" * 64, "1"),
        model_repository=object(),
        model_mapping=mapping,
        mapping_path="config/model_mapping.json",
    )
    assert app.model_management is not None
    assert app.model_ingestion is not None
    assert app.model_publication is not None
    assert app.result_publication is not None
    assert app.forecast_generation is None


def test_idempotency_conflict_is_mapped_without_raw_database_error():
    client = FakeClient()
    client.errors["create_durable_calculation_job_idempotent"] = RuntimeError(
        "IDEMPOTENCY_CONFLICT: internal postgres detail"
    )
    gateway = SupabaseBffApplicationGateway(client)
    provenance = ResultProvenance("engine", "mapping", "a" * 64, "1")

    with pytest.raises(GatewayIdempotencyConflictError, match="idempotency conflict"):
        gateway.submit_analysis(
            baseline_model_id="base", comparison_model_id="comparison",
            start_month=1, end_month=6, baseline_sales_fx=1480,
            comparison_sales_fx=1500, idempotency_actor="actor",
            idempotency_key="key", provenance=provenance, max_attempts=3,
        )


def test_by_id_reads_use_distinct_admin_and_viewer_rpcs():
    client = FakeClient()
    client.responses["get_calculation_job_status_by_id"] = []
    client.responses["get_calculation_result_admin_preview_by_id"] = []
    client.responses["get_available_calculation_result_by_id"] = []
    client.responses["get_bounded_evidence_admin"] = []
    client.responses["get_bounded_evidence_viewer"] = []
    client.responses["list_calculation_history_admin"] = []
    gateway = SupabaseBffApplicationGateway(client)

    assert gateway.get_job_status("job") is None
    assert gateway.get_admin_result_preview("result") is None
    assert gateway.get_viewer_result(
        "result", supported_result_schema_versions=("1",)
    ) is None
    assert gateway.get_admin_evidence_payload(
        "result", supported_result_schema_versions=("1",)
    ) is None
    assert gateway.get_viewer_evidence_payload(
        "result", supported_result_schema_versions=("1",)
    ) is None
    assert gateway.list_calculation_history(
        limit=25, before_created_at=None, before_job_id=None
    ) == []
    assert [name for name, _params in client.calls] == [
        "get_calculation_job_status_by_id",
        "get_calculation_result_admin_preview_by_id",
        "get_available_calculation_result_by_id",
        "get_bounded_evidence_admin",
        "get_bounded_evidence_viewer",
        "list_calculation_history_admin",
    ]


@pytest.mark.parametrize("response,expected", [
    (False, False),
    ([False], False),
    ([{"validate_calculation_result_availability": False}], False),
    ([{"validate_calculation_result_availability": True}], True),
])
def test_availability_scalar_response_is_normalized(response, expected):
    client = FakeClient()
    client.responses["validate_calculation_result_availability"] = response
    gateway = SupabaseBffApplicationGateway(client)

    assert gateway.validate_result_availability(
        "result", supported_result_schema_versions=("1",)
    ) is expected
