from __future__ import annotations

from functools import lru_cache
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from app.core.config import settings
from app.services.mineru_client import MinerUApiError, MinerUClient, MinerUParseResult, plain_text_from_html


class MaterialParseError(RuntimeError):
    """Raised when a material parser dependency or runtime operation fails."""


@dataclass(frozen=True)
class ParsedPage:
    source_locator: str
    heading: str
    text: str
    ocr_used: bool = False


def parse_material(path: str | Path, file_type: str, ocr_lang: str, ocr_max_pages: int | None = None) -> list[ParsedPage]:
    normalized_type = file_type.lower().lstrip(".")
    if normalized_type == "ppt":
        raise ValueError("Legacy .ppt parsing is not supported; convert to .pptx")
    if _should_use_mineru():
        try:
            return parse_material_with_mineru(path)
        except Exception as exc:
            if _is_mineru_configuration_error(exc) or not settings.mineru_fallback_to_local:
                raise
    if normalized_type == "pdf":
        return parse_pdf(path, ocr_lang, ocr_max_pages=ocr_max_pages)
    if normalized_type == "pptx":
        return parse_pptx(path)
    raise ValueError(f"Unsupported material type: {file_type}")


def parse_material_with_mineru(path: str | Path) -> list[ParsedPage]:
    file_path = Path(path)
    client = MinerUClient(
        api_token=settings.mineru_api_token,
        base_url=settings.mineru_base_url,
        model_version=settings.mineru_model_version,
        language=settings.mineru_language,
        enable_table=settings.mineru_enable_table,
        enable_formula=settings.mineru_enable_formula,
        is_ocr=settings.mineru_is_ocr,
        poll_interval_seconds=settings.mineru_poll_interval_seconds,
        poll_timeout_seconds=settings.mineru_poll_timeout_seconds,
    )
    result = client.parse_file(file_path, file_name=file_path.name)
    pages = mineru_result_to_pages(result)
    if not pages:
        raise MinerUApiError("MinerU parsing produced no extractable text")
    return pages


def mineru_result_to_pages(result: MinerUParseResult) -> list[ParsedPage]:
    if result.content_list:
        return _mineru_content_list_to_pages(result.content_list)
    if result.markdown.strip():
        return [
            ParsedPage(
                source_locator="document",
                heading=_first_text_line(_strip_markdown_heading_marks(result.markdown)),
                text=result.markdown.strip(),
                ocr_used=True,
            )
        ]
    return []


def _should_use_mineru() -> bool:
    return bool(getattr(settings, "mineru_enabled", False))


def _is_mineru_configuration_error(exc: Exception) -> bool:
    return isinstance(exc, MinerUApiError) and "MINERU_API_TOKEN" in str(exc)


def _mineru_content_list_to_pages(content_list: list[dict[str, Any]]) -> list[ParsedPage]:
    page_parts: dict[int, list[str]] = {}
    page_headings: dict[int, str] = {}

    for item in content_list:
        text = _mineru_item_text(item)
        if not text:
            continue
        page_number = _mineru_page_number(item)
        page_parts.setdefault(page_number, []).append(text)
        if page_number not in page_headings and _is_mineru_heading(item, text):
            page_headings[page_number] = text.splitlines()[0].strip()

    pages: list[ParsedPage] = []
    for page_number in sorted(page_parts):
        text = "\n".join(page_parts[page_number]).strip()
        if not text:
            continue
        pages.append(
            ParsedPage(
                source_locator=f"page {page_number}",
                heading=page_headings.get(page_number) or _first_text_line(text),
                text=text,
                ocr_used=True,
            )
        )
    return pages


def _mineru_page_number(item: dict[str, Any]) -> int:
    value = item.get("page_idx", item.get("page", item.get("page_number", 0)))
    try:
        return max(1, int(value) + 1 if "page_idx" in item else int(value))
    except (TypeError, ValueError):
        return 1


def _is_mineru_heading(item: dict[str, Any], text: str) -> bool:
    if item.get("text_level") is not None:
        return True
    return (item.get("type") or "").lower() in {"title", "heading"} and bool(text)


def _mineru_item_text(item: dict[str, Any]) -> str:
    item_type = (item.get("type") or "").lower()
    text = str(item.get("text") or "").strip()
    if text:
        return _strip_markdown_heading_marks(text)
    if item_type == "table":
        caption = " ".join(str(value).strip() for value in item.get("table_caption", []) if str(value).strip())
        body = plain_text_from_html(str(item.get("table_body") or item.get("html") or ""))
        return "\n".join(part for part in [caption, body] if part).strip()
    if item_type in {"equation", "formula"}:
        return str(item.get("latex") or item.get("html") or "").strip()
    return ""


def _strip_markdown_heading_marks(text: str) -> str:
    return "\n".join(line.lstrip("#").strip() for line in text.splitlines()).strip()


def parse_pdf(path: str | Path, ocr_lang: str, ocr_max_pages: int | None = None) -> list[ParsedPage]:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    pages: list[ParsedPage] = []
    ocr_page_count = 0

    for index, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        max_ocr_pages = settings.ocr_max_pages if ocr_max_pages is None else ocr_max_pages
        if len(text) < settings.ocr_text_min_chars:
            try:
                if max_ocr_pages < 0 or ocr_page_count < max_ocr_pages:
                    ocr_page_count += 1
                    ocr_page = ocr_pdf_page(path, index, ocr_lang)
                else:
                    ocr_page = None
            except MaterialParseError:
                ocr_page = None
            if ocr_page:
                pages.append(ocr_page)
            elif text:
                pages.append(
                    ParsedPage(
                        source_locator=f"page {index}",
                        heading=_first_text_line(text),
                        text=text,
                        ocr_used=False,
                    )
                )
        else:
            if text:
                pages.append(
                    ParsedPage(
                        source_locator=f"page {index}",
                        heading=_first_text_line(text),
                        text=text,
                        ocr_used=False,
                    )
                )

    if pages:
        return pages

    ocr_pages = parse_pdf_with_ocr(path, ocr_lang)
    if ocr_pages:
        return ocr_pages

    raise MaterialParseError(
        "PDF parsing produced no extractable text. Install and configure PaddleOCR, PaddlePaddle, PyMuPDF, and the requested OCR language data."
    )


def parse_pdf_with_ocr(path: str | Path, ocr_lang: str) -> list[ParsedPage]:
    try:
        import fitz
        from paddleocr import PaddleOCR
    except Exception as exc:
        raise _ocr_error() from exc

    pages: list[ParsedPage] = []
    try:
        ocr_engine = _get_paddle_ocr(ocr_lang)
        document = fitz.open(str(path))
        try:
            for index in range(len(document)):
                page = document.load_page(index)
                image = _render_pdf_page(page, fitz)
                text = _extract_paddle_ocr_text(ocr_engine.predict(image))
                if text:
                    pages.append(
                        ParsedPage(
                            source_locator=f"page {index + 1}",
                            heading=_first_text_line(text),
                            text=text,
                            ocr_used=True,
                        )
                    )
        finally:
            close = getattr(document, "close", None)
            if close is not None:
                close()
    except Exception as exc:
        raise _ocr_error() from exc
    return pages


def ocr_pdf_page(path: str | Path, page_number: int, ocr_lang: str) -> ParsedPage | None:
    try:
        import fitz
        from paddleocr import PaddleOCR
    except Exception as exc:
        raise _ocr_error() from exc

    try:
        ocr_engine = _get_paddle_ocr(ocr_lang)
        document = fitz.open(str(path))
        try:
            if page_number < 1 or page_number > len(document):
                return None
            page = document.load_page(page_number - 1)
            image = _render_pdf_page(page, fitz)
            text = _extract_paddle_ocr_text(ocr_engine.predict(image))
        finally:
            close = getattr(document, "close", None)
            if close is not None:
                close()
    except Exception as exc:
        raise _ocr_error() from exc

    if not text:
        return None
    return ParsedPage(
        source_locator=f"page {page_number}",
        heading=_first_text_line(text),
        text=text,
        ocr_used=True,
    )


def parse_pptx(path: str | Path) -> list[ParsedPage]:
    from pptx import Presentation

    presentation = Presentation(str(path))
    pages: list[ParsedPage] = []

    for index, slide in enumerate(presentation.slides, start=1):
        text_parts: list[str] = []
        for shape in slide.shapes:
            text = getattr(shape, "text", "").strip()
            if text:
                text_parts.append(text)

        text = "\n".join(text_parts).strip()
        if text:
            pages.append(
                ParsedPage(
                    source_locator=f"slide {index}",
                    heading=_first_text_line(text),
                    text=text,
                    ocr_used=False,
                )
            )

    return pages


def _first_text_line(text: str) -> str:
    for line in text.splitlines():
        heading = line.strip()
        if heading:
            return heading
    return ""


@lru_cache(maxsize=8)
def _get_paddle_ocr(ocr_lang: str) -> Any:
    from paddleocr import PaddleOCR

    detection_model_name, recognition_model_name, side_len = _ocr_model_config(settings.ocr_model_size)
    kwargs = {
        "engine": "paddle_dynamic",
        "text_detection_model_name": detection_model_name,
        "text_recognition_model_name": recognition_model_name,
        "use_doc_orientation_classify": False,
        "use_doc_unwarping": False,
        "use_textline_orientation": False,
        "text_det_limit_side_len": side_len,
        "text_det_limit_type": "max",
    }
    if detection_model_name is None and recognition_model_name is None:
        kwargs["lang"] = _normalize_paddleocr_lang(ocr_lang)
    return PaddleOCR(**kwargs)


def _ocr_model_config(model_size: str) -> tuple[str, str, int]:
    normalized = (model_size or "").lower().strip()
    if normalized == "server":
        return "PP-OCRv5_server_det", "PP-OCRv5_server_rec", 960
    return "PP-OCRv5_mobile_det", "PP-OCRv5_mobile_rec", 736


def _normalize_paddleocr_lang(ocr_lang: str) -> str:
    normalized = (ocr_lang or "").lower().strip()
    if any(token in normalized for token in ("chi", "zh", "ch")):
        return "ch"
    if normalized.startswith("en") or "eng" in normalized:
        return "en"
    return "ch"


def _render_pdf_page(page: Any, fitz_module: Any) -> np.ndarray:
    scale = max(1.0, float(settings.ocr_render_scale))
    pixmap = page.get_pixmap(matrix=fitz_module.Matrix(scale, scale), alpha=False)
    image = np.frombuffer(pixmap.samples, dtype=np.uint8)
    return image.reshape(pixmap.height, pixmap.width, pixmap.n)


def _extract_paddle_ocr_text(result: Any) -> str:
    if not result:
        return ""

    lines: list[str] = []
    blocks = result if isinstance(result, list) else [result]

    for block in blocks:
        payload = None
        if isinstance(block, dict):
            payload = block
        else:
            payload = getattr(block, "json", None)
            if callable(payload):
                payload = payload()
            if not isinstance(payload, dict):
                payload = getattr(block, "res", None)

        if isinstance(payload, dict):
            res = payload.get("res", payload)
            if isinstance(res, dict):
                rec_texts = res.get("rec_texts")
                if isinstance(rec_texts, list):
                    lines.extend(str(text).strip() for text in rec_texts if str(text).strip())
                    continue
                rec_text = res.get("rec_text")
                if rec_text:
                    lines.append(str(rec_text).strip())
                    continue
            elif isinstance(res, list):
                for item in res:
                    if isinstance(item, dict):
                        text = item.get("rec_text") or item.get("text")
                        if text:
                            lines.append(str(text).strip())
            continue

        if isinstance(block, (list, tuple)):
            if len(block) >= 2:
                candidate = block[1]
                if isinstance(candidate, (list, tuple)):
                    if candidate:
                        text = candidate[0]
                    else:
                        continue
                else:
                    text = candidate
                if text:
                    lines.append(str(text).strip())

    return "\n".join(line for line in lines if line).strip()


def _ocr_error() -> MaterialParseError:
    return MaterialParseError(
        "OCR failed. Install and configure PaddleOCR, PaddlePaddle, PyMuPDF, and the requested OCR language data."
    )
