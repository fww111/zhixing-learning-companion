"""课程材料分块服务：支持 general / qa / book 三种分块预设。

预设体系借鉴自伯乐（Bole）项目的 RAGFlow-like 分块引擎（见
AI-Interview/src/knowledge/chunking/ragflow_like/），按教育场景裁剪：

- general：定长窗口 + 百分比重叠（适合讲义、普通正文）
- qa：抽取"问题：/答案："对与疑问句标题对，统一为 ``问题：…\\n回答：…`` 格式
  （题库/FAQ 资料专用，下游可反向解析抽题），抽不到任何 QA 对时降级 general
- book：按页标题分节、节内层级合并，超长节走"句子级 → 字符级"三级保护
  （防止 embedding 超长）

所有预设共享三层参数合并（KB 默认 ← 文件覆盖 ← 请求覆盖）与分块引擎版本快照，
便于日后更换分块算法后重建索引。
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from enum import StrEnum

from app.services.material_parser import ParsedPage

CHUNK_ENGINE_VERSION = "v2-presets"


class ChunkPresetId(StrEnum):
    GENERAL = "general"
    QA = "qa"
    BOOK = "book"


CHUNK_PRESET_IDS = {preset.value for preset in ChunkPresetId}


@dataclass(frozen=True)
class TextChunk:
    chunk_index: int
    source_locator: str
    heading: str
    content: str
    token_count: int


PRESET_DEFAULTS: dict[str, dict[str, int]] = {
    ChunkPresetId.GENERAL.value: {"max_chars": 1200, "overlap_percent": 15},
    ChunkPresetId.QA.value: {"max_chars": 1200, "overlap_percent": 0},
    ChunkPresetId.BOOK.value: {"max_chars": 1600, "overlap_percent": 0},
}


@dataclass(frozen=True)
class ChunkingParams:
    preset_id: str = ChunkPresetId.GENERAL.value
    max_chars: int = 1200
    overlap_percent: int = 15
    engine_version: str = CHUNK_ENGINE_VERSION

    def snapshot(self) -> dict:
        return asdict(self)


def get_chunk_preset_options() -> list[dict[str, str]]:
    return [
        {
            "value": ChunkPresetId.GENERAL.value,
            "label": "通用分块",
            "description": "定长窗口 + 重叠，适合讲义和普通正文",
        },
        {
            "value": ChunkPresetId.QA.value,
            "label": "问答分块",
            "description": "抽取 问题/答案 对（题库、FAQ、复习问答），无结构对时自动降级通用",
        },
        {
            "value": ChunkPresetId.BOOK.value,
            "label": "教材分块",
            "description": "按标题分节层级合并，超长小节自动句子级保护",
        },
    ]


def resolve_chunk_params(
    kb_default: dict | None = None,
    file_override: dict | None = None,
    request_override: dict | None = None,
) -> ChunkingParams:
    """三层配置合并：request > file > kb 默认，并附带引擎版本快照。

    每层可包含 ``chunk_preset_id`` 与 ``max_chars`` / ``overlap_percent``。
    """
    merged: dict = {}
    for layer in (kb_default, file_override, request_override):
        if layer:
            merged = _deep_merge(merged, layer)

    preset_id = str(merged.get("chunk_preset_id") or ChunkPresetId.GENERAL.value)
    if preset_id not in CHUNK_PRESET_IDS:
        raise ValueError(f"unknown chunk preset id: {preset_id}")

    defaults = dict(PRESET_DEFAULTS[preset_id])
    max_chars = int(merged.get("max_chars") or defaults["max_chars"])
    overlap_percent = int(merged.get("overlap_percent", defaults["overlap_percent"]))
    max_chars = max(200, min(max_chars, 8000))
    overlap_percent = max(0, min(overlap_percent, 50))
    if preset_id != ChunkPresetId.GENERAL.value:
        overlap_percent = 0

    return ChunkingParams(
        preset_id=preset_id,
        max_chars=max_chars,
        overlap_percent=overlap_percent,
        engine_version=CHUNK_ENGINE_VERSION,
    )


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 2)


def chunk_pages(pages: list[ParsedPage], max_chars: int = 1200) -> list[TextChunk]:
    """旧版定长分块（无重叠），保持既有管线行为不变。"""
    if max_chars <= 0:
        raise ValueError("max_chars must be greater than 0")

    chunks: list[TextChunk] = []
    for page in pages:
        content = _normalize_whitespace(page.text)
        if not content:
            continue

        for start in range(0, len(content), max_chars):
            chunk_content = content[start : start + max_chars].strip()
            if not chunk_content:
                continue
            chunks.append(
                TextChunk(
                    chunk_index=len(chunks),
                    source_locator=page.source_locator,
                    heading=page.heading,
                    content=chunk_content,
                    token_count=estimate_tokens(chunk_content),
                )
            )

    return chunks


def chunk_pages_with_preset(pages: list[ParsedPage], params: ChunkingParams) -> list[TextChunk]:
    """按预设分发分块。QA 预设抽不到任何问答对时整体降级为通用分块。"""
    if params.preset_id == ChunkPresetId.QA.value:
        pairs = _chunk_qa(pages, params)
        if pairs:
            return pairs
        general_params = ChunkingParams(
            preset_id=ChunkPresetId.GENERAL.value,
            max_chars=params.max_chars,
            overlap_percent=PRESET_DEFAULTS[ChunkPresetId.GENERAL.value]["overlap_percent"],
            engine_version=params.engine_version,
        )
        return _chunk_general(pages, general_params)
    if params.preset_id == ChunkPresetId.BOOK.value:
        return _chunk_book(pages, params)
    return _chunk_general(pages, params)


# ---------------------------------------------------------------------------
# general：定长窗口 + 百分比重叠
# ---------------------------------------------------------------------------


def _chunk_general(pages: list[ParsedPage], params: ChunkingParams) -> list[TextChunk]:
    max_chars = params.max_chars
    overlap_chars = max_chars * params.overlap_percent // 100
    step = max(1, max_chars - overlap_chars)

    chunks: list[TextChunk] = []
    for page in pages:
        content = _normalize_whitespace(page.text)
        if not content:
            continue

        start = 0
        while start < len(content):
            piece = content[start : start + max_chars].strip()
            if not piece:
                break
            chunks.append(
                TextChunk(
                    chunk_index=len(chunks),
                    source_locator=page.source_locator,
                    heading=page.heading,
                    content=piece,
                    token_count=estimate_tokens(piece),
                )
            )
            if len(content) - start <= overlap_chars:
                break
            start += step

    return chunks


# ---------------------------------------------------------------------------
# qa：问答对抽取
# ---------------------------------------------------------------------------

_QUESTION_PREFIX = re.compile(r"^(?:问题|问|Q|Question)\s*[:：.、]\s*(.+)$", re.IGNORECASE)
_ANSWER_PREFIX = re.compile(r"^(?:答案|答|A|Answer)\s*[:：.、]\s*(.+)$", re.IGNORECASE)
_QUESTION_SUFFIX = re.compile(r"[?？]\s*$")
_NUMBERING_PREFIX = re.compile(r"^\s*(?:\d{1,3}[.、)）]|[（(]\d{1,2}[)）])\s*")


def _chunk_qa(pages: list[ParsedPage], params: ChunkingParams) -> list[TextChunk]:
    pairs: list[tuple[str, str, str]] = []  # (question, answer, source_locator)
    seen_questions: set[str] = set()

    for page in pages:
        lines = [line.strip() for line in page.text.splitlines()]
        lines = [line for line in lines if line]
        index = 0
        while index < len(lines):
            line = lines[index]
            pair = _match_prefix_pair(lines, index)
            if pair is not None:
                question, answer, next_index = pair
                key = _normalize_question(question)
                if key not in seen_questions:
                    seen_questions.add(key)
                    pairs.append((question, answer, page.source_locator))
                index = next_index
                continue
            if _QUESTION_SUFFIX.search(line) and len(line) <= 80:
                answer_lines: list[str] = []
                cursor = index + 1
                while cursor < len(lines):
                    nxt = lines[cursor]
                    if _QUESTION_PREFIX.match(nxt) or (_QUESTION_SUFFIX.search(nxt) and len(nxt) <= 80):
                        break
                    answer_lines.append(nxt)
                    cursor += 1
                    joined = "".join(answer_lines)
                    # 答案凑满一个完整句子后即停，避免吞掉后续不相关内容
                    if len(joined) >= 20 and joined[-1] in "。！？!?":
                        break
                    if sum(len(item) for item in answer_lines) >= params.max_chars:
                        break
                question = _NUMBERING_PREFIX.sub("", line).strip()
                answer = " ".join(answer_lines).strip()
                key = _normalize_question(question)
                if answer and key not in seen_questions:
                    seen_questions.add(key)
                    pairs.append((question, answer, page.source_locator))
                    index = cursor
                    continue
            index += 1

    chunks: list[TextChunk] = []
    for question, answer, locator in pairs:
        for piece in _ensure_max_chars(f"回答：{answer}", params.max_chars - len(question) - 1):
            answer_part = piece
            if answer_part.startswith("回答："):
                answer_part = answer_part[len("回答：") :]
            content = f"问题：{question}\n回答：{answer_part.strip()}"
            chunks.append(
                TextChunk(
                    chunk_index=len(chunks),
                    source_locator=locator,
                    heading=question[:255],
                    content=content,
                    token_count=estimate_tokens(content),
                )
            )
    return chunks


def _match_prefix_pair(lines: list[str], index: int) -> tuple[str, str, int] | None:
    question_match = _QUESTION_PREFIX.match(lines[index])
    if question_match is None:
        return None
    question = question_match.group(1).strip()

    answer_parts: list[str] = []
    cursor = index + 1
    if cursor < len(lines):
        answer_match = _ANSWER_PREFIX.match(lines[cursor])
        if answer_match is not None:
            answer_parts.append(answer_match.group(1).strip())
            cursor += 1
    if not answer_parts:
        # 答案前缀省略：问题行之后到下一个问题行为止的内容视作答案
        while cursor < len(lines):
            nxt = lines[cursor]
            if _QUESTION_PREFIX.match(nxt) or _ANSWER_PREFIX.match(nxt):
                break
            if _QUESTION_SUFFIX.search(nxt) and len(nxt) <= 80 and not answer_parts:
                break
            answer_parts.append(nxt)
            cursor += 1
            if sum(len(part) for part in answer_parts) >= 1200:
                break

    answer = " ".join(part for part in answer_parts).strip()
    if not answer:
        return None
    return question, answer, cursor


def _normalize_question(question: str) -> str:
    return re.sub(r"\s+", "", question).lower()


# ---------------------------------------------------------------------------
# book：标题分节 + 层级合并 + 超长三级保护
# ---------------------------------------------------------------------------


def _chunk_book(pages: list[ParsedPage], params: ChunkingParams) -> list[TextChunk]:
    sections: list[tuple[str, str, str]] = []  # (heading, joined_text, source_locator)
    for page in pages:
        text = _normalize_whitespace(page.text)
        if not text:
            continue
        heading = (page.heading or "").strip()
        if sections and sections[-1][0] == heading:
            prev_heading, prev_text, locator = sections[-1]
            sections[-1] = (prev_heading, f"{prev_text} {text}".strip(), locator)
        else:
            sections.append((heading, text, page.source_locator))

    chunks: list[TextChunk] = []
    for heading, text, locator in sections:
        pieces = _split_long_text(text, params.max_chars)
        buffer = ""
        for piece in pieces:
            candidate = f"{buffer} {piece}".strip() if buffer else piece
            if len(candidate) <= params.max_chars:
                buffer = candidate
                continue
            if buffer:
                chunks.append(_book_chunk(len(chunks), heading, buffer, locator))
                buffer = piece
            else:
                chunks.append(_book_chunk(len(chunks), heading, candidate, locator))
                buffer = ""
        if buffer:
            chunks.append(_book_chunk(len(chunks), heading, buffer, locator))
    return chunks


def _book_chunk(index: int, heading: str, content: str, locator: str) -> TextChunk:
    return TextChunk(
        chunk_index=index,
        source_locator=locator,
        heading=heading[:255],
        content=content,
        token_count=estimate_tokens(content),
    )


def _split_long_text(text: str, max_chars: int) -> list[str]:
    """三级保护：句子级切分 → 仍超长则字符级硬切。"""
    pieces: list[str] = []
    for sentence in re.split(r"(?<=[。！？；!?;])", text):
        sentence = sentence.strip()
        if not sentence:
            continue
        if len(sentence) <= max_chars:
            pieces.append(sentence)
            continue
        for start in range(0, len(sentence), max_chars):
            piece = sentence[start : start + max_chars].strip()
            if piece:
                pieces.append(piece)
    return pieces


def _ensure_max_chars(text: str, max_chars: int) -> list[str]:
    if max_chars <= 0:
        raise ValueError("max_chars must be greater than 0")
    if len(text) <= max_chars:
        return [text]
    return _split_long_text(text, max_chars)


def _normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _deep_merge(base: dict, override: dict) -> dict:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged
