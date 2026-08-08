from forecast.e2e_harness import SignedUploadE2EHarness


class FakeTransport:
    def __init__(self):
        self.calls = []

    def json(self, method, url, *, headers=None, body=None):
        self.calls.append((method, url, body))
        if url.endswith("/uploads/init"):
            return {
                "modelId": "model-1",
                "jobId": "job-1",
                "signedUrl": "https://storage.example/signed",
            }
        if url.endswith("/uploaded"):
            return {"status": "pending", "queueMessageId": 42}
        if url.endswith("/jobs/job-1"):
            return {"id": "job-1", "status": "completed"}
        raise AssertionError(url)

    def bytes(self, method, url, *, headers=None, body):
        self.calls.append((method, url, body))


def test_signed_upload_queue_worker_completed_sequence():
    transport = FakeTransport()
    harness = SignedUploadE2EHarness(
        "https://project.example/functions/v1/pnl-gateway",
        "admin-jwt",
        transport=transport,
        sleep=lambda _seconds: None,
    )

    outcome = harness.run(
        b"xlsx-bytes",
        {
            "name": "Actual",
            "modelType": "실적",
            "modelYear": 2026,
            "fileName": "actual.xlsx",
            "baselineModelId": "00000000-0000-4000-8000-000000000001",
            "months": [1],
            "publish": True,
        },
    )

    assert outcome.status == "completed"
    assert [call[0] for call in transport.calls] == ["POST", "PUT", "POST", "GET"]
    assert transport.calls[1][1] == "https://storage.example/signed"
