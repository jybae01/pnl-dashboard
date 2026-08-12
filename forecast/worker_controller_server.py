from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI, HTTPException
from supabase import create_client

from .logging_config import configure_structured_logging
from .worker_lifecycle import (
    GoogleWorkerPoolScaler,
    SupabaseWorkerLifecycleGateway,
    WorkerBusyError,
    WorkerControlUnavailable,
    WorkerLifecycleController,
)


def create_worker_controller(
    controller: WorkerLifecycleController,
) -> FastAPI:
    app = FastAPI(title="PNL Worker Lifecycle Controller", docs_url=None, redoc_url=None)

    @app.get("/health/live")
    def live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready")
    def ready() -> dict[str, Any]:
        return _invoke(controller.status)

    @app.get("/v1/worker/status")
    def status() -> dict[str, Any]:
        return _invoke(controller.status)

    @app.post("/v1/worker/reconcile")
    def reconcile() -> dict[str, Any]:
        return _invoke(controller.reconcile)

    @app.post("/v1/worker/emergency-wake")
    def emergency_wake() -> dict[str, Any]:
        return _invoke(controller.emergency_wake)

    @app.post("/v1/worker/safe-stop")
    def safe_stop() -> dict[str, Any]:
        try:
            return _invoke(controller.safe_stop)
        except WorkerBusyError as exc:
            raise HTTPException(status_code=409, detail="WORKER_BUSY") from exc

    @app.exception_handler(WorkerControlUnavailable)
    async def control_unavailable(_request, _exc):
        from fastapi.responses import JSONResponse

        return JSONResponse(
            status_code=503,
            content={"error": {"code": "WORKER_CONTROL_UNAVAILABLE"}},
        )

    return app


def _invoke(operation) -> dict[str, Any]:
    try:
        return operation().public_dict()
    except (WorkerBusyError, WorkerControlUnavailable):
        raise
    except Exception as exc:
        raise WorkerControlUnavailable("worker control dependency is unavailable") from exc


def create_worker_controller_from_environment() -> FastAPI:
    configure_structured_logging(os.getenv("CONTROLLER_LOG_LEVEL", "INFO"))
    url = _required("SUPABASE_URL")
    secret = _required("SUPABASE_SECRET_KEY")
    client = create_client(url, secret)
    gateway = SupabaseWorkerLifecycleGateway(client)
    scaler = GoogleWorkerPoolScaler(
        project_id=_required("GOOGLE_CLOUD_PROJECT"),
        region=_required("GOOGLE_CLOUD_REGION"),
        worker_pool=os.getenv("PNL_WORKER_POOL_NAME", "pnl-worker").strip(),
    )
    return create_worker_controller(WorkerLifecycleController(gateway, scaler))


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required")
    return value
