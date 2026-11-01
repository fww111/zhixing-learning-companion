from __future__ import annotations

import pytest

from app.services.chunking_service import (
    CHUNK_ENGINE_VERSION,
    ChunkingParams,
    ChunkPresetId,
    TextChunk,
    chunk_pages,
    chunk_pages_with_preset,
    get_chunk_preset_options,
    resolve_chunk_params,
)
from app.services.material_parser import ParsedPage


def page(text: str, heading: str = "", locator: str = "p1") -> ParsedPage:
    return ParsedPage(source_locator=locator, heading=heading, text=text)


def test_resolve_chunk_params_defaults_by_preset():
    general = resolve_chunk_params({"chunk_preset_id": "general"})
    assert general.preset_id == "general"
    assert general.overlap_percent == 15
    assert general.engine_version == CHUNK_ENGINE_VERSION

    qa = resolve_chunk_params({"chunk_preset_id": "qa"})
    assert qa.preset_id == "qa"
    assert qa.overlap_percent == 0

    book = resolve_chunk_params({"chunk_preset_id": "book"})
    assert book.preset_id == "book"


def test_resolve_chunk_params_three_layer_precedence():
    merged = resolve_chunk_params(
        {"chunk_preset_id": "general", "max_chars": 1200},
        {"max_chars": 2000},
        {"chunk_preset_id": "book", "max_chars": 800},
    )
    assert merged.preset_id == "book"          # request 层最高
    assert merged.max_chars == 800
    assert merged.snapshot()["engine_version"] == CHUNK_ENGINE_VERSION


def test_resolve_chunk_params_rejects_unknown_preset():
    with pytest.raises(ValueError):
        resolve_chunk_params({"chunk_preset_id": "laws"})


def test_general_preset_overlap_and_no_duplicate_tail():
    text = "字" * 3000
    params = resolve_chunk_params({"chunk_preset_id": "general", "max_chars": 1000, "overlap_percent": 20})
    chunks = chunk_pages_with_preset([page(text)], params)

    assert len(chunks) >= 3
    # 相邻 chunk 有重叠：第二个 chunk 的开头出现在第一个 chunk 的结尾区间
    assert chunks[0].content[800:1000] == chunks[1].content[:200]
    # 尾部不产生完全重复的 chunk
    assert all(chunk.content for chunk in chunks)


def test_chunk_pages_legacy_behavior_unchanged():
    chunks = chunk_pages([page("x" * 2500)], max_chars=1000)
    assert [len(chunk.content) for chunk in chunks] == [1000, 1000, 500]


def test_qa_preset_prefix_pairs():
    doc = "\n".join(
        [
            "问题：什么是时间复杂度？",
            "答案：描述算法运行时间随输入规模增长的趋势。",
            "问题：什么是空间复杂度？",
            "答案：描述算法额外占用内存随输入规模的增长趋势。",
            "问题：什么是时间复杂度？",  # 重复问题应被去重
            "答案：重复答案。",
        ]
    )
    params = resolve_chunk_params({"chunk_preset_id": "qa"})
    chunks = chunk_pages_with_preset([page(doc)], params)

    assert len(chunks) == 2
    assert chunks[0].content.startswith("问题：什么是时间复杂度？\n回答：")
    assert chunks[0].heading == "什么是时间复杂度？"
    assert all("重复答案" not in chunk.content for chunk in chunks)


def test_qa_preset_question_heading_pair():
    doc = "\n".join(
        [
            "1. 二分查找的适用条件是什么？",
            "二分查找要求数组有序，且条件具有单调性。",
            "每次循环把搜索范围缩小一半。",
            "下一章是动态规划，介绍状态转移方程的设计。",
        ]
    )
    params = resolve_chunk_params({"chunk_preset_id": "qa"})
    chunks = chunk_pages_with_preset([page(doc)], params)

    assert len(chunks) == 1
    assert "二分查找的适用条件" in chunks[0].content
    assert chunks[0].content.startswith("问题：")
    assert "状态转移方程" not in chunks[0].content


def test_qa_preset_falls_back_to_general_when_no_pairs():
    doc = "这是一段没有任何问答结构的普通讲义内容。" * 50
    params = resolve_chunk_params({"chunk_preset_id": "qa"})
    chunks = chunk_pages_with_preset([page(doc)], params)

    assert chunks
    assert all(not chunk.content.startswith("问题：") for chunk in chunks)


def test_book_preset_groups_by_heading_and_splits_long_sections():
    long_body = "算法很重要。".join([""] * 400)  # 无句号结尾的长文本由硬切兜底
    pages = [
        page("第一节内容短。", heading="第一章 概述", locator="p1"),
        page("第二节续内容，仍然较短。", heading="第一章 概述", locator="p2"),
        page("长" * 500 + "。分节内容超长需要切分保护。" * 60, heading="第二章 复杂度", locator="p3"),
        page(long_body, heading="第三章 硬切", locator="p4"),
    ]
    params = resolve_chunk_params({"chunk_preset_id": "book", "max_chars": 600})
    chunks = chunk_pages_with_preset(pages, params)

    assert chunks
    assert all(len(chunk.content) <= 600 for chunk in chunks)
    headings = {chunk.heading for chunk in chunks}
    assert "第一章 概述" in headings
    # 相同标题的相邻页应合并到同一节
    first_section_chunks = [chunk for chunk in chunks if chunk.heading == "第一章 概述"]
    assert all("第一节内容短" in chunk.content or "第二节续内容" in chunk.content for chunk in first_section_chunks)


def test_preset_options_for_frontend():
    options = get_chunk_preset_options()
    assert {option["value"] for option in options} == {"general", "qa", "book"}
    assert all(option["label"] and option["description"] for option in options)
