from __future__ import annotations

import io
import json
import re
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class MinerUApiError(RuntimeError):
    """Raised when MinerU API upload, polling, or result download fails."""


@dataclass(frozen=True)
class MinerUParseResult:
    markdown: str
    content_list: list[dict[str, Any]]


class MinerUClient:
    def __init__(
        self,
        api_token: str,
        *,
        base_url: str = "https://mineru.net",
        model_version: str = "vlm",
        language: str = "ch",
        enable_table: bool = True,
        enable_formula: bool = True,
        is_ocr: bool = True,
        poll_interval_seconds: int = 3,
        poll_timeout_seconds: int = 900,
        max_pages_per_task: int = 200,
        http_client: Any | None = None,
    ) -> None:
        if not api_token:
            raise MinerUApiError("MINERU_API_TOKEN is required when MinerU parsing is enabled")
        self.api_token = api_token
        self.base_url = base_url.rstrip("/")
        self.model_version = model_version
        self.language = language
        self.enable_table = enable_table
        self.enable_formula = enable_formula
        self.is_ocr = is_ocr
        self.poll_interval_seconds = max(0, poll_interval_seconds)
        self.poll_timeout_seconds = max(1, poll_timeout_seconds)
        self.max_pages_per_task = max(1, max_pages_per_task)
        self.http_client = http_client if http_client is not None else self._create_http_client()

    def parse_file(self, path: str | Path, *, file_name: str | None = None, data_id: str | None = None) -> MinerUParseResult:
        file_path = Path(path)
        upload_name = file_name or file_path.name
        page_ranges = self._page_ranges(file_path)
        if not page_ranges:
            return self._parse_file_range(file_path, upload_name, data_id=data_id, page_range=None, page_offset=0)

        results = [
            self._parse_file_range(
                file_path,
                upload_name,
                data_id=self._range_data_id(data_id, page_range),
                page_range=page_range,
                page_offset=int(page_range.split("-", 1)[0]) - 1,
            )
            for page_range in page_ranges
        ]
        return self._merge_results(results)

    def _parse_file_range(
        self,
        file_path: Path,
        upload_name: str,
        *,
        data_id: str | None,
        page_range: str | None,
        page_offset: int,
    ) -> MinerUParseResult:
        batch_id, upload_url = self._create_upload_url(upload_name, data_id=data_id, page_range=page_range)
        self._upload_file(upload_url, file_path)
        extract_result = self._poll_extract_result(batch_id, upload_name)
        full_zip_url = self._extract_string(extract_result, "full_zip_url")
        if not full_zip_url:
            raise MinerUApiError("MinerU task finished without full_zip_url")
        return self._offset_result_pages(self._download_parse_result(full_zip_url), page_offset)

    def _create_http_client(self) -> Any:
        import httpx

        return httpx.Client(timeout=60)

    def _headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_token}",
        }

    def _create_upload_url(self, file_name: str, *, data_id: str | None, page_range: str | None = None) -> tuple[str, str]:
        payload = {
            "enable_formula": self.enable_formula,
            "enable_table": self.enable_table,
            "language": self.language,
            "model_version": self.model_version,
            "files": [
                {
                    "name": file_name,
                    "is_ocr": self.is_ocr,
                }
            ],
        }
        if data_id:
            payload["files"][0]["data_id"] = data_id
        if page_range:
            payload["files"][0]["page_ranges"] = page_range

        response = self.http_client.post(
            f"{self.base_url}/api/v4/file-urls/batch",
            headers=self._headers(),
            json=payload,
        )
        data = self._checked_json(response, "create MinerU upload URL")
        batch_id = self._extract_string(data, "batch_id")
        file_urls = self._extract_list(data, "file_urls")
        if not batch_id or not file_urls:
            raise MinerUApiError("MinerU upload URL response is missing batch_id or file_urls")
        return batch_id, str(file_urls[0])

    def _upload_file(self, upload_url: str, path: Path) -> None:
        response = self.http_client.put(upload_url, content=path.read_bytes())
        status_code = getattr(response, "status_code", 0)
        if status_code < 200 or status_code >= 300:
            raise MinerUApiError(f"MinerU upload failed with HTTP {status_code}: {getattr(response, 'text', '')}")

    def _poll_extract_result(self, batch_id: str, file_name: str) -> dict[str, Any]:
        deadline = time.monotonic() + self.poll_timeout_seconds
        last_state = ""
        while time.monotonic() <= deadline:
            response = self.http_client.get(
                f"{self.base_url}/api/v4/extract-results/batch/{batch_id}",
                headers=self._headers(),
            )
            data = self._checked_json(response, "poll MinerU extract result")
            result = self._select_extract_result(data, file_name)
            state = self._extract_string(result, "state").lower()
            last_state = state or last_state
            if state in {"done", "success", "succeeded", "completed"}:
                return result
            if state in {"failed", "error"}:
                message = self._extract_string(result, "err_msg") or self._extract_string(result, "error_msg")
                raise MinerUApiError(message or f"MinerU task failed for {file_name}")
            if self.poll_interval_seconds > 0:
                time.sleep(self.poll_interval_seconds)

        raise MinerUApiError(f"MinerU task timed out after {self.poll_timeout_seconds}s; last state={last_state or 'unknown'}")

    def _download_parse_result(self, full_zip_url: str) -> MinerUParseResult:
        response = self.http_client.get(full_zip_url, headers=None)
        status_code = getattr(response, "status_code", 0)
        if status_code < 200 or status_code >= 300:
            raise MinerUApiError(f"MinerU result download failed with HTTP {status_code}: {getattr(response, 'text', '')}")
        return self._parse_result_zip(response.content)

    def _checked_json(self, response: Any, action: str) -> dict[str, Any]:
        status_code = getattr(response, "status_code", 0)
        if status_code < 200 or status_code >= 300:
            raise MinerUApiError(f"MinerU {action} failed with HTTP {status_code}: {getattr(response, 'text', '')}")
        payload = response.json()
        if not isinstance(payload, dict):
            raise MinerUApiError(f"MinerU {action} returned a non-object response")
        code = payload.get("code")
        if code not in (None, 0, "0"):
            message = payload.get("msg") or payload.get("message") or payload.get("error")
            raise MinerUApiError(str(message or f"MinerU {action} failed with code {code}"))
        data = payload.get("data", payload)
        if not isinstance(data, dict):
            raise MinerUApiError(f"MinerU {action} response data is not an object")
        return data

    def _select_extract_result(self, data: dict[str, Any], file_name: str) -> dict[str, Any]:
        raw_results = data.get("extract_result") or data.get("extract_results") or data.get("results")
        if isinstance(raw_results, list):
            for item in raw_results:
                if not isinstance(item, dict):
                    continue
                candidate_name = self._extract_string(item, "file_name") or self._extract_string(item, "name")
                if candidate_name in {"", file_name}:
                    return item
            for item in raw_results:
                if isinstance(item, dict):
                    return item
        if isinstance(raw_results, dict):
            return raw_results
        if "state" in data:
            return data
        raise MinerUApiError("MinerU polling response is missing extract_result")

    def _parse_result_zip(self, payload: bytes) -> MinerUParseResult:
        markdown = ""
        content_list: list[dict[str, Any]] = []
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            names = archive.namelist()
            markdown_name = self._find_archive_member(names, "full.md") or self._find_suffix(names, ".md")
            content_list_name = self._find_archive_member(names, "_content_list.json") or self._find_archive_member(names, "content_list.json")
            if markdown_name:
                markdown = archive.read(markdown_name).decode("utf-8", errors="ignore").strip()
            if content_list_name:
                raw_content = archive.read(content_list_name).decode("utf-8", errors="ignore")
                parsed = json.loads(raw_content)
                if isinstance(parsed, list):
                    content_list = [item for item in parsed if isinstance(item, dict)]
        if not markdown and not content_list:
            raise MinerUApiError("MinerU result zip does not contain full.md or content_list.json")
        return MinerUParseResult(markdown=markdown, content_list=content_list)

    def _page_ranges(self, path: Path) -> list[str]:
        if path.suffix.lower() != ".pdf":
            return []
        try:
            from pypdf import PdfReader

            page_count = len(PdfReader(str(path)).pages)
        except Exception:
            return []
        if page_count <= self.max_pages_per_task:
            return []
        ranges = []
        for start in range(1, page_count + 1, self.max_pages_per_task):
            end = min(start + self.max_pages_per_task - 1, page_count)
            ranges.append(f"{start}-{end}")
        return ranges

    def _range_data_id(self, data_id: str | None, page_range: str) -> str | None:
        if not data_id:
            return None
        return f"{data_id}-{page_range}"

    def _offset_result_pages(self, result: MinerUParseResult, page_offset: int) -> MinerUParseResult:
        if page_offset <= 0 or not result.content_list:
            return result
        shifted_items = []
        for item in result.content_list:
            shifted = dict(item)
            if "page_idx" in shifted:
                shifted["page_idx"] = self._offset_int(shifted["page_idx"], page_offset)
            elif "page" in shifted:
                shifted["page"] = self._offset_int(shifted["page"], page_offset)
            elif "page_number" in shifted:
                shifted["page_number"] = self._offset_int(shifted["page_number"], page_offset)
            shifted_items.append(shifted)
        return MinerUParseResult(markdown=result.markdown, content_list=shifted_items)

    def _merge_results(self, results: list[MinerUParseResult]) -> MinerUParseResult:
        markdown = "\n\n".join(result.markdown for result in results if result.markdown.strip()).strip()
        content_list = [item for result in results for item in result.content_list]
        return MinerUParseResult(markdown=markdown, content_list=content_list)

    def _offset_int(self, value: Any, offset: int) -> Any:
        try:
            return int(value) + offset
        except (TypeError, ValueError):
            return value

    def _find_archive_member(self, names: list[str], suffix: str) -> str | None:
        normalized_suffix = suffix.lower()
        for name in names:
            if name.lower().endswith(normalized_suffix):
                return name
        return None

    def _find_suffix(self, names: list[str], suffix: str) -> str | None:
        for name in names:
            if name.lower().endswith(suffix.lower()):
                return name
        return None

    def _extract_string(self, data: dict[str, Any], key: str) -> str:
        value = data.get(key)
        return str(value).strip() if value is not None else ""

    def _extract_list(self, data: dict[str, Any], key: str) -> list[Any]:
        value = data.get(key)
        return value if isinstance(value, list) else []


def plain_text_from_html(value: str) -> str:
    without_tags = re.sub(r"<[^>]+>", " ", value or "")
    return re.sub(r"\s+", " ", without_tags).strip()
