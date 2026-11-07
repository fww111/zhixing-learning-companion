"""RAG 检索质量算法：RRF 多路融合 + 句级上下文压缩（纯函数）。

- RRF（Reciprocal Rank Fusion）：多路查询的命中排名跨路融合——
  在多路查询中反复出现的 chunk 得分更高，单路霸榜被抑制（k=60 业界标准）。
- 句级抽取式压缩：chunk 原文按句子拆分，按查询术语命中率排序取 top 句，
  保持原文顺序重组——进 prompt 的证据更短更相关（token ↓，信噪比 ↑）。
"""

from __future__ import annotations

import re
from typing import Any

from app.services.rag_lexicon import extract_query_terms

RRF_K = 60

_SENTENCE_SPLIT = re.compile(r"(?<=[。！？!?；;\n.])\s*")


def rrf_fuse_hits(
    hits: list[dict[str, Any]],
    *,
    max_results: int,
) -> list[dict[str, Any]]:
    """把多路查询的向量命中按 RRF 融合排序。

    输入 hit：{query, chunk_id, distance, vector_source_locator}，顺序即该路排名。
    输出：按融合分降序的去重 chunk 列表，附 rrf_score 与 hit_queries（命中过的查询路）。
    """
    scores: dict[int, float] = {}
    meta: dict[int, dict[str, Any]] = {}
    for hit in hits:
        chunk_id = hit.get("chunk_id")
        if chunk_id is None:
            continue
        chunk_key = int(chunk_id)
        rank = hit.get("_rank", 0)
        contribution = 1.0 / (RRF_K + rank + 1)
        scores[chunk_key] = scores.get(chunk_key, 0.0) + contribution
        entry = meta.setdefault(
            chunk_key,
            {
                "chunk_id": chunk_key,
                "distance": hit.get("distance"),
                "vector_source_locator": hit.get("vector_source_locator"),
                "hit_queries": [],
                "first_query": hit.get("query"),
            },
        )
        query = str(hit.get("query") or "")
        if query and query not in entry["hit_queries"]:
            entry["hit_queries"].append(query)

    ranked = sorted(scores.items(), key=lambda pair: pair[1], reverse=True)[:max_results]
    results: list[dict[str, Any]] = []
    for chunk_id, score in ranked:
        results.append({**meta[chunk_id], "rrf_score": round(score, 6)})
    return results


def compress_chunk_to_relevant_sentences(
    content: str,
    query: str,
    *,
    max_sentences: int = 6,
    min_keep: int = 2,
) -> str:
    """抽取式压缩：保留与查询最相关的句子（保持原文顺序）。

    规则：句子里每命中一个查询术语 +1；命中 chunk 标题词 +2 由调用方传入标题加权。
    句子不足 min_keep 时全保（短 chunk 不压缩）。
    """
    text = (content or "").strip()
    if not text:
        return ""
    sentences = [s.strip() for s in _SENTENCE_SPLIT.split(text) if s.strip()]
    if len(sentences) <= max_sentences:
        return text

    terms = extract_query_terms(query)
    if not terms:
        return "。".join(sentences[:max_sentences])

    def sentence_score(sentence: str) -> int:
        lowered = sentence.lower()
        return sum(1 for term in terms if term in lowered)

    scored = sorted(range(len(sentences)), key=lambda i: sentence_score(sentences[i]), reverse=True)
    keep_indices = sorted(scored[:max_sentences])
    kept = [sentences[i].rstrip("。！？；!?.;， ") for i in keep_indices if sentences[i].strip()]
    if len(kept) < min_keep:
        kept = [s.rstrip("。！？；!?.;， ") for s in sentences[:min_keep]]
    return "。".join(kept) + "。"
