import asyncio

from app.services import openmaic_client
from app.services.openmaic_client import OpenMAICClient


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def test_openmaic_client_submits_supported_payload_and_returns_job_metadata(monkeypatch):
    calls = []

    class FakeAsyncClient:
        def __init__(self, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, url, json):
            calls.append({"url": url, "json": json, "timeout": self.timeout})
            return FakeResponse(
                {
                    "success": True,
                    "jobId": "job-1",
                    "status": "queued",
                    "step": "queued",
                    "pollUrl": "http://127.0.0.1:3000/api/generate-classroom/job-1",
                    "pollIntervalMs": 5000,
                }
            )

    monkeypatch.setattr(openmaic_client.httpx, "AsyncClient", FakeAsyncClient)

    result = asyncio.run(
        OpenMAICClient(base_url="http://127.0.0.1:3000/", timeout_seconds=7).generate_classroom(
            requirement="Build a Python class",
            pdf_text="authoritative context",
            language="zh-CN",
            agent_mode="generate",
        )
    )

    assert calls == [
        {
            "url": "http://127.0.0.1:3000/api/generate-classroom",
            "json": {
                "requirement": "Build a Python class",
                "language": "zh-CN",
                "agentMode": "generate",
                "pdfContent": {"text": "authoritative context", "images": []},
            },
            "timeout": 7,
        }
    ]
    assert result["job_id"] == "job-1"
    assert result["status"] == "queued"
    assert result["poll_interval_ms"] == 5000
    assert result["error"] == ""


def test_openmaic_client_can_enable_tts_for_voxcpm_backed_classrooms(monkeypatch):
    calls = []

    class FakeAsyncClient:
        def __init__(self, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, url, json):
            calls.append({"url": url, "json": json})
            return FakeResponse(
                {
                    "success": True,
                    "jobId": "job-tts",
                    "status": "queued",
                    "step": "queued",
                }
            )

    monkeypatch.setattr(openmaic_client.httpx, "AsyncClient", FakeAsyncClient)

    result = asyncio.run(
        OpenMAICClient(base_url="http://127.0.0.1:3000").generate_classroom(
            requirement="Build a voiced Python classroom",
            pdf_text="",
            enable_tts=True,
        )
    )

    assert calls[0]["json"] == {
        "requirement": "Build a voiced Python classroom",
        "language": "zh-CN",
        "agentMode": "generate",
        "enableTTS": True,
    }
    assert result["job_id"] == "job-tts"


def test_openmaic_client_does_not_treat_queued_message_as_error(monkeypatch):
    class FakeAsyncClient:
        def __init__(self, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, url, json):  # noqa: ARG002
            return FakeResponse(
                {
                    "success": True,
                    "jobId": "job-queued",
                    "status": "queued",
                    "step": "queued",
                    "message": "Classroom generation job queued",
                    "pollUrl": "http://127.0.0.1:3000/api/generate-classroom/job-queued",
                    "pollIntervalMs": 5000,
                }
            )

    monkeypatch.setattr(openmaic_client.httpx, "AsyncClient", FakeAsyncClient)

    result = asyncio.run(
        OpenMAICClient(base_url="http://127.0.0.1:3000/", timeout_seconds=7).generate_classroom(
            requirement="Build a Python class",
            pdf_text="authoritative context",
        )
    )

    assert result["status"] == "queued"
    assert result["poll_url"] == "http://127.0.0.1:3000/api/generate-classroom/job-queued"
    assert result["error"] == ""


def test_openmaic_client_polls_job_and_normalizes_relative_classroom_url(monkeypatch):
    calls = []

    class FakeAsyncClient:
        def __init__(self, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def get(self, url):
            calls.append({"url": url, "timeout": self.timeout})
            return FakeResponse(
                {
                    "success": True,
                    "jobId": "job-1",
                    "status": "succeeded",
                    "step": "done",
                    "result": {
                        "classroomId": "classroom-1",
                        "url": "/classroom/classroom-1",
                    },
                }
            )

    monkeypatch.setattr(openmaic_client.httpx, "AsyncClient", FakeAsyncClient)

    result = asyncio.run(
        OpenMAICClient(base_url="http://127.0.0.1:3000/", timeout_seconds=9).poll_classroom("job-1")
    )

    assert calls == [{"url": "http://127.0.0.1:3000/api/generate-classroom/job-1", "timeout": 9}]
    assert result["job_id"] == "job-1"
    assert result["status"] == "succeeded"
    assert result["step"] == "done"
    assert result["classroom_id"] == "classroom-1"
    assert result["url"] == "http://127.0.0.1:3000/classroom/classroom-1"


def test_openmaic_client_rejects_poll_url_outside_configured_service():
    client = OpenMAICClient(base_url="http://127.0.0.1:3000")

    try:
        client._poll_url(job_id="", poll_url="http://169.254.169.254/latest/meta-data")
    except ValueError as exc:
        assert "outside configured OpenMAIC service" in str(exc)
    else:
        raise AssertionError("Expected OpenMAICClient to reject external poll_url")
