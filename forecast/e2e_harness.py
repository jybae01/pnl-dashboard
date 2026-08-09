from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Callable, Protocol
from urllib.error import HTTPError
from urllib.request import Request, urlopen


class JsonHttpTransport(Protocol):
    def json(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...

    def bytes(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        body: bytes,
    ) -> None: ...


class UrllibTransport:
    def json(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        encoded = None if body is None else json.dumps(body).encode("utf-8")
        request = Request(url, data=encoded, method=method, headers={
            "content-type": "application/json",
            **(headers or {}),
        })
        try:
            with urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"gateway returned HTTP {exc.code}: {detail}") from exc

    def bytes(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        body: bytes,
    ) -> None:
        request = Request(url, data=body, method=method, headers=headers or {})
        try:
            with urlopen(request, timeout=120) as response:
                response.read()
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"signed upload returned HTTP {exc.code}: {detail}") from exc


@dataclass(frozen=True)
class PipelineOutcome:
    model_id: str
    job_id: str
    status: str
    status_payload: dict[str, Any]


class SignedUploadE2EHarness:
    """Exercise deployed signed upload -> pgmq -> worker -> completed JSONB."""

    CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    def __init__(
        self,
        gateway_url: str,
        admin_jwt: str,
        *,
        transport: JsonHttpTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.gateway_url = gateway_url.rstrip("/")
        self.headers = {"authorization": f"Bearer {admin_jwt}"}
        self.transport = transport or UrllibTransport()
        self.sleep = sleep

    def run(
        self,
        workbook: bytes,
        metadata: dict[str, Any],
        *,
        timeout_seconds: float = 180,
        poll_seconds: float = 2,
    ) -> PipelineOutcome:
        initialized = self.transport.json(
            "POST",
            f"{self.gateway_url}/uploads/init",
            headers=self.headers,
            body=metadata,
        )
        model_id = str(initialized["modelId"])
        job_id = str(initialized["jobId"])
        signed_url = str(initialized["signedUrl"])
        self.transport.bytes(
            "PUT",
            signed_url,
            headers={"content-type": self.CONTENT_TYPE, "x-upsert": "false"},
            body=workbook,
        )
        uploaded = self.transport.json(
            "POST",
            f"{self.gateway_url}/jobs/{job_id}/uploaded",
            headers=self.headers,
            body={},
        )
        if not uploaded.get("queueMessageId"):
            raise RuntimeError("upload callback did not return a pgmq message receipt")

        deadline = time.monotonic() + timeout_seconds
        status: dict[str, Any] = {}
        while time.monotonic() < deadline:
            status = self.transport.json(
                "GET",
                f"{self.gateway_url}/jobs/{job_id}",
                headers=self.headers,
            )
            if status.get("status") in {"completed", "failed"}:
                return PipelineOutcome(model_id, job_id, str(status["status"]), status)
            self.sleep(poll_seconds)
        raise TimeoutError(f"calculation job {job_id} did not reach a terminal state")
