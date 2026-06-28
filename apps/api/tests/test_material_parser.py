import sys
import types

import pytest

from app.core.storage import allowed_file_type, course_upload_dir, safe_upload_name
from app.services.chunking_service import chunk_pages
from app.services import material_parser
from app.services.material_parser import MaterialParseError, ParsedPage


def set_parser_settings(monkeypatch, **overrides):
    current = material_parser.settings
    values = {
        "ocr_text_min_chars": getattr(current, "ocr_text_min_chars", 50),
        "ocr_max_pages": getattr(current, "ocr_max_pages", 20),
        "ocr_render_scale": getattr(current, "ocr_render_scale", 1.5),
        "ocr_model_size": getattr(current, "ocr_model_size", "mobile"),
    }
    values.update(overrides)
    monkeypatch.setattr(material_parser, "settings", types.SimpleNamespace(**values))


def test_safe_upload_name_removes_path_parts():
    assert safe_upload_name("..\\secret\\lesson 1.pdf").endswith(".pdf")
    assert "\\" not in safe_upload_name("..\\secret\\lesson 1.pdf")
    assert "/" not in safe_upload_name("../secret/lesson 1.pdf")


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("CON.pdf", "upload_CON.pdf"),
        ("com1.PPTX", "upload_com1.pptx"),
        ("folder\\LPT9.ppt", "upload_LPT9.ppt"),
    ],
)
def test_safe_upload_name_prefixes_windows_reserved_basenames(filename, expected):
    assert safe_upload_name(filename) == expected


@pytest.mark.parametrize("bad_user_id", ["../1", "..\\1", "1/../2", "abc", "0", "-1"])
def test_course_upload_dir_rejects_invalid_user_id(tmp_path, bad_user_id):
    with pytest.raises(ValueError):
        course_upload_dir(tmp_path, bad_user_id, 1)


@pytest.mark.parametrize("bad_course_id", ["../1", "..\\1", "1/../2", "abc", "0", "-1"])
def test_course_upload_dir_rejects_invalid_course_id(tmp_path, bad_course_id):
    with pytest.raises(ValueError):
        course_upload_dir(tmp_path, 1, bad_course_id)


def test_course_upload_dir_creates_path_under_upload_root(tmp_path):
    path = course_upload_dir(tmp_path, "1", 2)

    assert path == tmp_path / "1" / "2"
    assert path.is_dir()


def test_allowed_file_type_whitelist():
    assert allowed_file_type("course.PDF") == "pdf"
    assert allowed_file_type("slides.pptx") == "pptx"
    assert allowed_file_type("slides.ppt") == "ppt"
    assert allowed_file_type("image.exe") is None


def test_parse_material_rejects_legacy_ppt_with_clear_error(tmp_path):
    with pytest.raises(ValueError, match="Legacy \\.ppt parsing is not supported; convert to \\.pptx"):
        material_parser.parse_material(tmp_path / "slides.ppt", "ppt", "eng")


def test_parse_pdf_ocr_fallback_runs_per_page(monkeypatch, tmp_path):
    class FakePdfPage:
        def __init__(self, text):
            self._text = text

        def extract_text(self):
            return self._text

    class FakePdfReader:
        def __init__(self, path):
            self.pages = [
                FakePdfPage("This page already has enough extracted text."),
                FakePdfPage("short"),
            ]

    fake_pypdf = types.SimpleNamespace(PdfReader=FakePdfReader)
    monkeypatch.setitem(sys.modules, "pypdf", fake_pypdf)

    ocr_calls = []

    def fake_ocr_pdf_page(path, page_number, ocr_lang):
        ocr_calls.append((path, page_number, ocr_lang))
        return ParsedPage(
            source_locator=f"page {page_number}",
            heading="OCR heading",
            text="OCR recovered text from page two.",
            ocr_used=True,
        )

    monkeypatch.setattr(material_parser, "ocr_pdf_page", fake_ocr_pdf_page, raising=False)
    set_parser_settings(monkeypatch, ocr_text_min_chars=20, ocr_max_pages=20)

    pages = material_parser.parse_pdf(tmp_path / "scan.pdf", "chi_sim")

    assert ocr_calls == [(tmp_path / "scan.pdf", 2, "chi_sim")]
    assert [page.text for page in pages] == [
        "This page already has enough extracted text.",
        "OCR recovered text from page two.",
    ]
    assert [page.ocr_used for page in pages] == [False, True]


def test_parse_pdf_limits_number_of_ocr_pages(monkeypatch, tmp_path):
    class FakePdfPage:
        def extract_text(self):
            return ""

    class FakePdfReader:
        def __init__(self, path):
            self.pages = [FakePdfPage(), FakePdfPage(), FakePdfPage()]

    fake_pypdf = types.SimpleNamespace(PdfReader=FakePdfReader)
    monkeypatch.setitem(sys.modules, "pypdf", fake_pypdf)
    set_parser_settings(monkeypatch, ocr_text_min_chars=20, ocr_max_pages=1)

    ocr_calls = []

    def fake_ocr_pdf_page(path, page_number, ocr_lang):  # noqa: ARG001
        ocr_calls.append(page_number)
        return ParsedPage(
            source_locator=f"page {page_number}",
            heading="OCR heading",
            text=f"OCR recovered text from page {page_number}.",
            ocr_used=True,
        )

    monkeypatch.setattr(material_parser, "ocr_pdf_page", fake_ocr_pdf_page, raising=False)

    pages = material_parser.parse_pdf(tmp_path / "scan.pdf", "chi_sim")

    assert ocr_calls == [1]
    assert [page.source_locator for page in pages] == ["page 1"]


def test_parse_pdf_can_disable_ocr_page_limit_for_background_jobs(monkeypatch, tmp_path):
    class FakePdfPage:
        def extract_text(self):
            return ""

    class FakePdfReader:
        def __init__(self, path):
            self.pages = [FakePdfPage(), FakePdfPage(), FakePdfPage()]

    fake_pypdf = types.SimpleNamespace(PdfReader=FakePdfReader)
    monkeypatch.setitem(sys.modules, "pypdf", fake_pypdf)
    set_parser_settings(monkeypatch, ocr_text_min_chars=20, ocr_max_pages=1)

    ocr_calls = []

    def fake_ocr_pdf_page(path, page_number, ocr_lang):  # noqa: ARG001
        ocr_calls.append(page_number)
        return ParsedPage(
            source_locator=f"page {page_number}",
            heading="OCR heading",
            text=f"OCR recovered text from page {page_number}.",
            ocr_used=True,
        )

    monkeypatch.setattr(material_parser, "ocr_pdf_page", fake_ocr_pdf_page, raising=False)

    pages = material_parser.parse_pdf(tmp_path / "scan.pdf", "chi_sim", ocr_max_pages=-1)

    assert ocr_calls == [1, 2, 3]
    assert [page.source_locator for page in pages] == ["page 1", "page 2", "page 3"]


def test_parse_pdf_preserves_text_when_ocr_dependency_is_missing(monkeypatch, tmp_path):
    class FakePdfPage:
        def __init__(self, text):
            self._text = text

        def extract_text(self):
            return self._text

    class FakePdfReader:
        def __init__(self, path):
            self.pages = [
                FakePdfPage("This page already has enough extracted text."),
                FakePdfPage("short extracted text"),
            ]

    fake_pypdf = types.SimpleNamespace(PdfReader=FakePdfReader)
    monkeypatch.setitem(sys.modules, "pypdf", fake_pypdf)

    def raising_ocr_pdf_page(path, page_number, ocr_lang):  # noqa: ARG001
        raise MaterialParseError("OCR failed. Install and configure PaddleOCR, PaddlePaddle, PyMuPDF.")

    monkeypatch.setattr(material_parser, "ocr_pdf_page", raising_ocr_pdf_page, raising=False)

    set_parser_settings(monkeypatch, ocr_text_min_chars=20, ocr_max_pages=20)

    pages = material_parser.parse_pdf(tmp_path / "lesson.pdf", "chi_sim")

    assert [page.text for page in pages] == [
        "This page already has enough extracted text.",
        "short extracted text",
    ]
    assert [page.ocr_used for page in pages] == [False, False]


def test_parse_pdf_falls_back_to_full_ocr_when_text_extraction_returns_nothing(monkeypatch, tmp_path):
    class FakePdfPage:
        def extract_text(self):
            return ""

    class FakePdfReader:
        def __init__(self, path):
            self.pages = [FakePdfPage(), FakePdfPage()]

    fake_pypdf = types.SimpleNamespace(PdfReader=FakePdfReader)
    monkeypatch.setitem(sys.modules, "pypdf", fake_pypdf)

    ocr_calls = []

    def fake_parse_pdf_with_ocr(path, ocr_lang):
        ocr_calls.append((path, ocr_lang))
        return [
            ParsedPage(
                source_locator="page 1",
                heading="OCR heading",
                text="OCR recovered text from the scanned pdf.",
                ocr_used=True,
            )
        ]

    monkeypatch.setattr(material_parser, "parse_pdf_with_ocr", fake_parse_pdf_with_ocr, raising=False)

    pages = material_parser.parse_pdf(tmp_path / "scan.pdf", "chi_sim")

    assert ocr_calls == [(tmp_path / "scan.pdf", "chi_sim")]
    assert [page.text for page in pages] == ["OCR recovered text from the scanned pdf."]
    assert [page.ocr_used for page in pages] == [True]


def test_parse_pdf_with_paddleocr_uses_rendered_image_arrays(monkeypatch, tmp_path):
    class FakePixmap:
        width = 2
        height = 1
        n = 3
        samples = b"\xff\x00\x00\x00\xff\x00"

    class FakePage:
        def get_pixmap(self, matrix, alpha):  # noqa: ARG002
            return FakePixmap()

    class FakeDocument:
        def __len__(self):
            return 1

        def load_page(self, index):  # noqa: ARG002
            return FakePage()

        def close(self):
            return None

    class FakePaddleOCR:
        def __init__(self, **kwargs):
            assert kwargs["engine"] == "paddle_dynamic"
            assert "show_log" not in kwargs
            assert kwargs["use_doc_orientation_classify"] is False
            assert kwargs["use_doc_unwarping"] is False
            assert kwargs["use_textline_orientation"] is False
            assert kwargs["text_detection_model_name"] == "PP-OCRv5_mobile_det"
            assert kwargs["text_recognition_model_name"] == "PP-OCRv5_mobile_rec"
            assert kwargs["text_det_limit_side_len"] == 736
            assert kwargs["text_det_limit_type"] == "max"
            assert "lang" not in kwargs
            self.kwargs = kwargs

        def predict(self, image):  # noqa: ARG002
            assert getattr(image, "shape", None) == (1, 2, 3)
            return [
                types.SimpleNamespace(
                    json={
                        "res": {
                            "rec_texts": ["Python 基础", "变量与表达式"],
                        }
                    }
                )
            ]

    fake_fitz = types.SimpleNamespace(
        Matrix=lambda x, y: (x, y),
        open=lambda path: FakeDocument(),  # noqa: ARG005
    )
    fake_paddleocr = types.SimpleNamespace(PaddleOCR=FakePaddleOCR)
    monkeypatch.setitem(sys.modules, "fitz", fake_fitz)
    monkeypatch.setitem(sys.modules, "paddleocr", fake_paddleocr)
    set_parser_settings(monkeypatch, ocr_model_size="mobile", ocr_render_scale=1.0)
    material_parser._get_paddle_ocr.cache_clear()

    pages = material_parser.parse_pdf_with_ocr(tmp_path / "scan.pdf", "chi_sim+eng")

    assert len(pages) == 1
    assert pages[0].ocr_used is True
    assert pages[0].heading == "Python 基础"
    assert pages[0].text == "Python 基础\n变量与表达式"


def test_server_ocr_model_size_uses_server_models(monkeypatch):
    captured_kwargs = []

    class FakePaddleOCR:
        def __init__(self, **kwargs):
            captured_kwargs.append(kwargs)

    fake_paddleocr = types.SimpleNamespace(PaddleOCR=FakePaddleOCR)
    monkeypatch.setitem(sys.modules, "paddleocr", fake_paddleocr)
    set_parser_settings(monkeypatch, ocr_model_size="server")
    material_parser._get_paddle_ocr.cache_clear()

    material_parser._get_paddle_ocr("chi_sim+eng")

    assert captured_kwargs[0]["text_detection_model_name"] == "PP-OCRv5_server_det"
    assert captured_kwargs[0]["text_recognition_model_name"] == "PP-OCRv5_server_rec"


def test_ocr_dependency_failure_raises_actionable_error(monkeypatch, tmp_path):
    material_parser._get_paddle_ocr.cache_clear()
    monkeypatch.setitem(sys.modules, "fitz", None)

    with pytest.raises(MaterialParseError) as exc_info:
        material_parser.parse_pdf_with_ocr(tmp_path / "scan.pdf", "chi_sim")

    message = str(exc_info.value)
    assert "OCR failed" in message
    assert "install" in message.lower()
    assert "PaddleOCR" in message
    assert "PaddlePaddle" in message


def test_chunk_pages_preserves_source_locator():
    pages = [
        ParsedPage(source_locator="page 1", heading="绪论", text="机器学习是从数据中学习规律。" * 20, ocr_used=False),
        ParsedPage(source_locator="page 2", heading="监督学习", text="监督学习使用有标签样本。" * 20, ocr_used=False),
    ]
    chunks = chunk_pages(pages, max_chars=120)
    assert chunks
    assert chunks[0].source_locator == "page 1"
    assert chunks[0].heading == "绪论"
    assert "机器学习" in chunks[0].content
