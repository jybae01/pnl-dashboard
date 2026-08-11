from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from pathlib import Path
from typing import Any

import httpx
from supabase import create_client


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


def _secret(name: str) -> str:
    path = Path(_required(f"{name}_FILE"))
    value = path.read_text(encoding="utf-8").strip()
    if not value:
        raise RuntimeError(f"{name}_FILE is empty")
    return value


def _expect(response: httpx.Response, status: int) -> dict[str, Any]:
    if response.status_code != status:
        raise RuntimeError(
            f"unexpected response: {response.request.method} {response.request.url.path} "
            f"returned {response.status_code}"
        )
    if response.headers.get("content-type", "").startswith("application/json"):
        return response.json()
    return {}


def _cookie_header(client: httpx.Client) -> str:
    values = []
    for name in ("pnl_session", "pnl_csrf"):
        value = client.cookies.get(name)
        if value:
            values.append(f"{name}={value}")
    return "; ".join(values)


def _clear_lockout(supabase_client: Any, client_ip: str) -> None:
    client_key = hashlib.sha256(("login-client-v1:" + client_ip).encode("utf-8")).hexdigest()
    supabase_client.rpc("clear_bff_login_failures", {"p_client_key": client_key}).execute()


def _wait_for_file(path: str, *, timeout_seconds: float = 30.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if Path(path).is_file():
            return
        time.sleep(0.25)
    raise RuntimeError("local edge CA was not generated in time")


def _wait_for_status(
    client: httpx.Client, path: str, status: int, *, timeout_seconds: float = 90.0
) -> httpx.Response:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            response = client.get(path)
            if response.status_code == status:
                return response
        except httpx.HTTPError:
            pass
        time.sleep(0.5)
    raise RuntimeError(f"{path} did not become ready in time")


def main() -> int:
    edge_url = _required("PHASE_B_EDGE_URL")
    origin = edge_url
    ca_file = _required("PHASE_B_CA_FILE")
    bff_a_url = _required("PHASE_B_BFF_A_URL")
    bff_b_url = _required("PHASE_B_BFF_B_URL")
    probe_ip = _required("PHASE_B_PROBE_IP")
    admin_code = _secret("ADMIN_CODE")
    viewer_code = _secret("VIEWER_CODE")
    supabase_key = _secret("SUPABASE_SECRET_KEY")
    supabase_client = create_client(_required("SUPABASE_URL"), supabase_key)
    correlation_ids: set[str] = set()

    _wait_for_file(ca_file)
    with httpx.Client(base_url=edge_url, verify=ca_file, timeout=30.0) as edge:
        ready = _wait_for_status(edge, "/health/ready", 200)
        if ready.headers.get("x-correlation-id"):
            correlation_ids.add(ready.headers["x-correlation-id"])
        for path in ("/health/live", "/"):
            response = edge.get(path)
            _expect(response, 200)
            if response.headers.get("x-correlation-id"):
                correlation_ids.add(response.headers["x-correlation-id"])

        login = edge.post("/api/session/login", json={"access_code": admin_code})
        _expect(login, 200)
        correlation_ids.add(login.headers["x-correlation-id"])
        csrf = edge.cookies.get("pnl_csrf")
        if not csrf:
            raise RuntimeError("admin login did not issue a CSRF cookie")
        mutation_headers = {"Origin": origin, "X-CSRF-Token": csrf}

        session = edge.get("/api/session")
        _expect(session, 200)
        models_response = edge.get("/api/models")
        models = _expect(models_response, 200).get("models", [])
        published = [item for item in models if item.get("is_published")]
        if len(published) < 2:
            raise RuntimeError("at least two published staging models are required")

        forecast_body = {
            "base_model_id": published[0]["model_id"],
            "name": "Phase B disabled Forecast probe",
            "model_year": published[0]["model_year"],
            "version": "phase-b-disabled",
            "start_month": 7,
            "end_month": 7,
            "months": [{"month": 7, "sales": [], "production": []}],
            "idempotency_key": f"phase-b-forecast-disabled-{uuid.uuid4()}",
        }
        forecast = edge.post("/api/admin/forecasts", json=forecast_body, headers=mutation_headers)
        forecast_payload = _expect(forecast, 403)
        if forecast_payload.get("error", {}).get("code") != "FORECAST_SCOPE_NOT_APPROVED":
            raise RuntimeError("disabled Forecast did not fail with the scoped policy error")

        analysis_body = {
            "baseline_model_id": published[0]["model_id"],
            "comparison_model_id": published[1]["model_id"],
            "start_month": 1,
            "end_month": 12,
            "baseline_sales_fx": 1480,
            "comparison_sales_fx": 1480,
            "idempotency_key": f"phase-b-analysis-{uuid.uuid4()}",
        }
        submitted = _expect(
            edge.post("/api/analyses", json=analysis_body, headers=mutation_headers), 200
        )
        job_id = submitted["job_id"]
        result_id = None
        for _ in range(120):
            job = _expect(edge.get(f"/api/jobs/{job_id}"), 200)
            if str(job.get("status", "")).lower() == "completed":
                result_id = job.get("result_id")
                break
            if str(job.get("status", "")).lower() == "failed":
                raise RuntimeError("deployed Worker reported a failed Analysis job")
            time.sleep(1)
        if not result_id:
            raise RuntimeError("deployed Worker did not complete the Analysis job in time")

        _expect(edge.get(f"/api/admin/results/{result_id}"), 200)
        _expect(edge.get(f"/api/admin/results/{result_id}/presentation"), 200)
        evidence = edge.get(f"/api/admin/results/{result_id}/evidence")
        _expect(evidence, 200)
        if not evidence.content.startswith(b"PK"):
            raise RuntimeError("Evidence response is not an XLSX package")
        history = _expect(edge.get("/api/admin/calculation-history?limit=10"), 200)
        if not any(item.get("job_id") == job_id for item in history.get("items", [])):
            raise RuntimeError("completed Analysis is missing from History")

        with httpx.Client(base_url=edge_url, verify=ca_file, timeout=30.0) as viewer:
            _expect(viewer.post("/api/session/login", json={"access_code": viewer_code}), 200)
            pnl = _expect(viewer.get("/api/viewer/pnl-dashboard"), 200)
            uuid.UUID(str(pnl.get("result_id")))

    with httpx.Client(base_url=bff_a_url, timeout=15.0) as first:
        _expect(first.post("/api/session/login", json={"access_code": admin_code}), 200)
        cookie = _cookie_header(first)
        csrf = first.cookies.get("pnl_csrf")
        if not cookie or not csrf:
            raise RuntimeError("BFF-A did not issue shared session cookies")
        with httpx.Client(base_url=bff_b_url, timeout=15.0) as second:
            _expect(second.get("/api/session", headers={"Cookie": cookie}), 200)
            _expect(
                second.post(
                    "/api/session/logout",
                    headers={"Cookie": cookie, "Origin": origin, "X-CSRF-Token": csrf},
                ),
                200,
            )
        _expect(first.get("/api/session", headers={"Cookie": cookie}), 401)

    _clear_lockout(supabase_client, probe_ip)
    try:
        statuses = []
        for index, target in enumerate((bff_a_url, bff_b_url, bff_a_url, bff_b_url)):
            with httpx.Client(base_url=target, timeout=15.0) as client:
                response = client.post(
                    "/api/session/login",
                    json={"access_code": "invalid-phase-b-code"},
                    headers={"X-Forwarded-For": f"198.51.100.{index + 1}"},
                )
                statuses.append(response.status_code)
        with httpx.Client(base_url=edge_url, verify=ca_file, timeout=15.0) as edge:
            response = edge.post(
                "/api/session/login",
                json={"access_code": "invalid-phase-b-code"},
                headers={"X-Forwarded-For": "203.0.113.200"},
            )
            statuses.append(response.status_code)
        if statuses[-1] != 429 or any(status != 401 for status in statuses[:-1]):
            raise RuntimeError(
                "distributed lockout or edge forwarded-header replacement did not hold"
            )
    finally:
        _clear_lockout(supabase_client, probe_ip)

    result = {
        "https_edge": "PASS",
        "health_readiness": "PASS",
        "forecast_disabled": "PASS",
        "shared_session": "PASS",
        "distributed_lockout": "PASS",
        "analysis_worker_result": "PASS",
        "presentation_history_evidence": "PASS",
        "published_default_pnl_available": "PASS",
        "correlation_ids_observed": len(correlation_ids),
    }
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
