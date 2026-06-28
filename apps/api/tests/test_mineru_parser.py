from __future__ import annotations

import io
import sys
import types
import zipfile
from pathlib import Path

import pytest

from app.services import material_parser


class FakeResponse:
    def __init__(self, status_code=200, payload=None, content=b""):
        self.status_code = status_code
        self._payload = payload
        self.content = content
        self.text = str(payload) if payload is not None else content.decode("utf-8", errors="ignore")

    def json(self):
        return self._payload


class RecordingHttpClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def post(self, url, *, headers=None, json=None):
        self.requests.append({"method": "POST", "url": url, "headers": headers, "json": json})
        return self.responses.pop(0)

    def put(self, url, *, content=None):
        self.requests.append({"method": "PUT", "url": url, "content": content})
        return self.responses.pop(0)

    def get(self, url, *, headers=None):
        self.requests.append({"method": "GET", "url": url, "headers": headers})
        return self.responses.pop(0)


def make_zip_file(files: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def test_mineru_client_uploads_polls_and_downloads_structured_result(tmp_path):
    from app.services.mineru_client import MinerUClient

    material_path = tmp_path / "lesson.pdf"
    material_path.write_bytes(b"fake pdf bytes")
    zip_payload = make_zip_file(
        {
            "lesson/full.md": "# Python 基础\n变量与表达式",
            "lesson/lesson_content_list.json": (
                '[{"type":"text","text":"Python 基础","text_level":1,"page_idx":0},'
                '{"type":"text","text":"变量与表达式","page_idx":0}]'
            ),
        }
    )
    http_client = RecordingHttpClient(
        [
            FakeResponse(
                payload={
                    "code": 0,
                    "data": {
                        "batch_id": "batch-1",
                        "file_urls": ["https://oss.example/upload"],
                    },
                    "msg": "ok",
                }
            ),
            FakeResponse(status_code=200),
            FakeResponse(
                payload={
                    "code": 0,
                    "data": {
                        "batch_id": "batch-1",
                        "extract_result": [{"file_name": "lesson.pdf", "state": "running", "err_msg": ""}],
                    },
                    "msg": "ok",
                }
            ),
            FakeResponse(
                payload={
                    "code": 0,
                    "data": {
                        "batch_id": "batch-1",
                        "extract_result": [
                            {
                                "file_name": "lesson.pdf",
                                "state": "done",
                                "err_msg": "",
                                "full_zip_url": "https://cdn.example/result.zip",
                                "data_id": "material-42",
                            }
                        ],
                    },
                    "msg": "ok",
                }
            ),
            FakeResponse(status_code=200, content=zip_payload),
        ]
    )

    result = MinerUClient(
        api_token="token-1",
        http_client=http_client,
        poll_interval_seconds=0,
        poll_timeout_seconds=5,
    ).parse_file(material_path, file_name="lesson.pdf", data_id="material-42")

    assert result.markdown == "# Python 基础\n变量与表达式"
    assert result.content_list == [
        {"type": "text", "text": "Python 基础", "text_level": 1, "page_idx": 0},
        {"type": "text", "text": "变量与表达式", "page_idx": 0},
    ]
    create_request = http_client.requests[0]
    assert create_request["url"] == "https://mineru.net/api/v4/file-urls/batch"
    assert create_request["headers"]["Authorization"] == "Bearer token-1"
    assert create_request["json"]["model_version"] == "vlm"
    assert create_request["json"]["language"] == "ch"
    assert create_request["json"]["enable_table"] is True
    assert create_request["json"]["enable_formula"] is True
    assert create_request["json"]["files"] == [
        {"name": "lesson.pdf", "data_id": "material-42", "is_ocr": True}
    ]
    assert http_client.requests[1] == {
        "method": "PUT",
        "url": "https://oss.example/upload",
        "content": b"fake pdf bytes",
    }


def test_mineru_client_reports_failed_task(tmp_path):
    from app.services.mineru_client import MinerUApiError, MinerUClient

    material_path = tmp_path / "lesson.pdf"
    material_path.write_bytes(b"fake pdf bytes")
    http_client = RecordingHttpClient(
        [
            FakeResponse(payload={"code": 0, "data": {"batch_id": "batch-1", "file_urls": ["https://oss"]}}),
            FakeResponse(status_code=200),
            FakeResponse(
                payload={
                    "code": 0,
                    "data": {
                        "batch_id": "batch-1",
                        "extract_result": [
                            {
                                "file_name": "lesson.pdf",
                                "state": "failed",
                                "err_msg": "文件页数超过限制",
                            }
                        ],
                    },
                }
            ),
        ]
    )

    with pytest.raises(MinerUApiError, match="文件页数超过限制"):
        MinerUClient(
            api_token="token-1",
            http_client=http_client,
            poll_interval_seconds=0,
            poll_timeout_seconds=5,
        ).parse_file(material_path, file_name="lesson.pdf", data_id="material-42")


def test_mineru_client_splits_large_pdf_into_page_range_tasks(monkeypatch, tmp_path):
    from app.services.mineru_client import MinerUClient

    class FakePdfReader:
        def __init__(self, path):  # noqa: ARG002
            self.pages = [object() for _ in range(217)]

    monkeypatch.setitem(sys.modules, "pypdf", types.SimpleNamespace(PdfReader=FakePdfReader))
    material_path = tmp_path / "large.pdf"
    material_path.write_bytes(b"fake large pdf bytes")
    first_zip = make_zip_file(
        {
            "large/full.md": "# part one",
            "large/large_content_list.json": '[{"type":"text","text":"page one","page_idx":0}]',
        }
    )
    second_zip = make_zip_file(
        {
            "large/full.md": "# part two",
            "large/large_content_list.json": '[{"type":"text","text":"page 201","page_idx":0}]',
        }
    )
    http_client = RecordingHttpClient(
        [
            FakeResponse(payload={"code": 0, "data": {"batch_id": "batch-1", "file_urls": ["https://oss.example/upload-1"]}}),
            FakeResponse(status_code=200),
            FakeResponse(
                payload={
                    "code": 0,
                    "data": {
                        "extract_result": [
                            {"file_name": "large.pdf", "state": "done", "full_zip_url": "https://cdn.example/result-1.zip"}
                        ]
                    },
                }
            ),
            FakeResponse(status_code=200, content=first_zip),
            FakeResponse(payload={"code": 0, "data": {"batch_id": "batch-2", "file_urls": ["https://oss.example/upload-2"]}}),
            FakeResponse(status_code=200),
            FakeResponse(
                payload={
                    "code": 0,
                    "data": {
                        "extract_result": [
                            {"file_name": "large.pdf", "state": "done", "full_zip_url": "https://cdn.example/result-2.zip"}
                        ]
                    },
                }
            ),
            FakeResponse(status_code=200, content=second_zip),
        ]
    )

    result = MinerUClient(
        api_token="token-1",
        http_client=http_client,
        poll_interval_seconds=0,
        poll_timeout_seconds=5,
        max_pages_per_task=200,
    ).parse_file(material_path, file_name="large.pdf", data_id="material-42")

    create_requests = [request for request in http_client.requests if request["method"] == "POST"]
    assert create_requests[0]["json"]["files"][0]["page_ranges"] == "1-200"
    assert create_requests[0]["json"]["files"][0]["data_id"] == "material-42-1-200"
    assert create_requests[1]["json"]["files"][0]["page_ranges"] == "201-217"
    assert create_requests[1]["json"]["files"][0]["data_id"] == "material-42-201-217"
    assert result.markdown == "# part one\n\n# part two"
    assert [item["page_idx"] for item in result.content_list] == [0, 200]


def test_mineru_result_to_pages_groups_content_list_by_page():
    from app.services.mineru_client import MinerUParseResult

    result = MinerUParseResult(
        markdown="# fallback",
        content_list=[
            {"type": "text", "text": "第一章 Python 入门", "text_level": 1, "page_idx": 0},
            {"type": "text", "text": "变量、表达式与输入输出。", "page_idx": 0},
            {"type": "equation", "text": "x = 1 + 2", "page_idx": 1},
            {
                "type": "table",
                "table_caption": ["表 1 内置类型"],
                "table_body": "<table><tr><td>list</td><td>列表</td></tr></table>",
                "page_idx": 1,
            },
        ],
    )

    pages = material_parser.mineru_result_to_pages(result)

    assert [page.source_locator for page in pages] == ["page 1", "page 2"]
    assert pages[0].heading == "第一章 Python 入门"
    assert "变量、表达式" in pages[0].text
    assert pages[1].heading == "x = 1 + 2"
    assert "表 1 内置类型" in pages[1].text
    assert "list 列表" in pages[1].text
    assert all(page.ocr_used for page in pages)


def test_parse_material_uses_mineru_when_enabled(monkeypatch, tmp_path):
    from app.services.mineru_client import MinerUParseResult

    material_path = tmp_path / "slides.pptx"
    material_path.write_bytes(b"fake pptx bytes")
    calls = []

    class FakeMinerUClient:
        def __init__(self, **kwargs):
            calls.append({"kwargs": kwargs})

        def parse_file(self, path, *, file_name=None, data_id=None):
            calls.append({"path": path, "file_name": file_name, "data_id": data_id})
            return MinerUParseResult(
                markdown="# Slide 1\nPython 课程",
                content_list=[{"type": "text", "text": "Python 课程", "text_level": 1, "page_idx": 0}],
            )

    monkeypatch.setattr(material_parser, "settings", types.SimpleNamespace(
        mineru_enabled=True,
        mineru_api_token="token-1",
        mineru_base_url="https://mineru.net",
        mineru_model_version="vlm",
        mineru_language="ch",
        mineru_enable_table=True,
        mineru_enable_formula=True,
        mineru_is_ocr=True,
        mineru_poll_interval_seconds=0,
        mineru_poll_timeout_seconds=5,
        mineru_fallback_to_local=False,
        ocr_text_min_chars=50,
        ocr_max_pages=20,
        ocr_render_scale=1.5,
        ocr_model_size="mobile",
    ))
    monkeypatch.setattr(material_parser, "MinerUClient", FakeMinerUClient, raising=False)

    pages = material_parser.parse_material(material_path, "pptx", "chi_sim+eng")

    assert calls[0]["kwargs"]["api_token"] == "token-1"
    assert calls[1]["path"] == material_path
    assert calls[1]["file_name"] == "slides.pptx"
    assert pages[0].text == "Python 课程"
    assert pages[0].ocr_used is True


def test_parse_material_falls_back_to_local_parser_when_mineru_network_fails(monkeypatch, tmp_path):
    material_path = tmp_path / "lesson.pdf"
    material_path.write_bytes(b"fake pdf bytes")

    class FailingMinerUClient:
        def __init__(self, **kwargs):  # noqa: ARG002
            return None

        def parse_file(self, path, *, file_name=None, data_id=None):  # noqa: ARG002
            raise ConnectionError("network is unavailable")

    def fake_parse_pdf(path, ocr_lang, ocr_max_pages=None):  # noqa: ARG001
        return [
            material_parser.ParsedPage(
                source_locator="page 1",
                heading="Local fallback",
                text="Local parser recovered this PDF.",
                ocr_used=False,
            )
        ]

    monkeypatch.setattr(material_parser, "settings", types.SimpleNamespace(
        mineru_enabled=True,
        mineru_api_token="token-1",
        mineru_base_url="https://mineru.net",
        mineru_model_version="vlm",
        mineru_language="ch",
        mineru_enable_table=True,
        mineru_enable_formula=True,
        mineru_is_ocr=True,
        mineru_poll_interval_seconds=0,
        mineru_poll_timeout_seconds=5,
        mineru_fallback_to_local=True,
        ocr_lang="chi_sim+eng",
        ocr_text_min_chars=50,
        ocr_max_pages=20,
        ocr_render_scale=1.5,
        ocr_model_size="mobile",
    ))
    monkeypatch.setattr(material_parser, "MinerUClient", FailingMinerUClient, raising=False)
    monkeypatch.setattr(material_parser, "parse_pdf", fake_parse_pdf, raising=False)

    pages = material_parser.parse_material(material_path, "pdf", "chi_sim+eng")

    assert pages[0].heading == "Local fallback"


def test_parse_material_enabled_without_token_raises_instead_of_local_fallback(monkeypatch, tmp_path):
    from app.services.mineru_client import MinerUApiError

    material_path = tmp_path / "lesson.pdf"
    material_path.write_bytes(b"fake pdf bytes")

    def forbidden_local_parser(path, ocr_lang, ocr_max_pages=None):  # noqa: ARG001
        raise AssertionError("local parser should not run when MinerU is explicitly enabled")

    monkeypatch.setattr(material_parser, "settings", types.SimpleNamespace(
        mineru_enabled=True,
        mineru_api_token="",
        mineru_base_url="https://mineru.net",
        mineru_model_version="vlm",
        mineru_language="ch",
        mineru_enable_table=True,
        mineru_enable_formula=True,
        mineru_is_ocr=True,
        mineru_poll_interval_seconds=0,
        mineru_poll_timeout_seconds=5,
        mineru_fallback_to_local=True,
        ocr_text_min_chars=50,
        ocr_max_pages=20,
        ocr_render_scale=1.5,
        ocr_model_size="mobile",
    ))
    monkeypatch.setattr(material_parser, "parse_pdf", forbidden_local_parser, raising=False)

    with pytest.raises(MinerUApiError, match="MINERU_API_TOKEN"):
        material_parser.parse_material(material_path, "pdf", "chi_sim+eng")
