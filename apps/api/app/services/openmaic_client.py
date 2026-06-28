from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import httpx

from app.core.config import settings


class OpenMAICClient:
    def __init__(self, base_url: str | None = None, timeout_seconds: float | None = None) -> None:
        self.base_url = (base_url or settings.openmaic_base_url).rstrip("/")
        self.timeout_seconds = timeout_seconds or settings.openmaic_timeout_seconds

    async def generate_classroom(
        self,
        *,
        requirement: str,
        pdf_text: str,
        language: str = "zh-CN",
        agent_mode: str = "generate",
        enable_tts: bool | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "requirement": requirement,
            "language": language,
            "agentMode": agent_mode,
        }
        if enable_tts is not None:
            payload["enableTTS"] = enable_tts
        if pdf_text.strip():
            payload["pdfContent"] = {"text": pdf_text, "images": []}

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(f"{self.base_url}/api/generate-classroom", json=payload)
            response.raise_for_status()
            data = response.json()

        return self._normalize_classroom(data)

    async def poll_classroom(self, job_id: str = "", *, poll_url: str = "") -> dict[str, Any]:
        target_url = self._poll_url(job_id=job_id, poll_url=poll_url)
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.get(target_url)
            response.raise_for_status()
            data = response.json()

        normalized = self._normalize_classroom(data)
        if poll_url and not normalized.get("poll_url"):
            normalized["poll_url"] = poll_url
        if job_id and not normalized.get("job_id"):
            normalized["job_id"] = job_id
        return normalized

    def _poll_url(self, *, job_id: str = "", poll_url: str = "") -> str:
        if poll_url:
            parsed = urlparse(poll_url)
            if parsed.scheme and parsed.netloc:
                configured = urlparse(self.base_url)
                if (parsed.scheme, parsed.netloc) != (configured.scheme, configured.netloc):
                    raise ValueError("OpenMAIC poll_url is outside configured OpenMAIC service")
                return poll_url
            return f"{self.base_url}/{poll_url.lstrip('/')}"
        if not job_id:
            raise ValueError("OpenMAIC job_id or poll_url is required")
        return f"{self.base_url}/api/generate-classroom/{job_id}"

    def _normalize_classroom(self, data: dict[str, Any]) -> dict[str, Any]:
        body = data.get("data") if isinstance(data, dict) and isinstance(data.get("data"), dict) else data
        result = body.get("result") if isinstance(body, dict) and isinstance(body.get("result"), dict) else {}
        classroom_url = self._absolute_url(result.get("url") or body.get("url") or "")
        classroom_id = result.get("classroomId") or result.get("id") or body.get("classroomId") or ""
        poll_url = self._absolute_url(body.get("pollUrl") or body.get("poll_url") or "")
        status = body.get("status") or ""
        explicit_error = body.get("error") or ""
        message_error = body.get("message") if str(status).lower() in {"failed", "error"} else ""
        return {
            "job_id": body.get("jobId") or body.get("job_id") or "",
            "status": status,
            "step": body.get("step") or "",
            "poll_url": poll_url,
            "poll_interval_ms": int(body.get("pollIntervalMs") or body.get("poll_interval_ms") or 0),
            "url": classroom_url,
            "classroom_id": classroom_id,
            "error": explicit_error or message_error or "",
        }

    def _absolute_url(self, value: str) -> str:
        if not value:
            return ""
        parsed = urlparse(value)
        if parsed.scheme and parsed.netloc:
            return value
        return f"{self.base_url}/{value.lstrip('/')}"
