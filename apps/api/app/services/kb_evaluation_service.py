"""知识库检索能力自动评估服务。

借鉴伯乐（Bole）项目的 evaluation_service：
1. 评测集自动构造——从课程 chunk 中选 anchor，配若干干扰 chunk 作为上下文，
   由 LLM 生成 {query, gold_answer}，gold_chunk_ids 固定为 anchor（可校验）；
2. 评估执行——逐题调用检索器（Milvus 语义检索或 MySQL LIKE 兜底），
   计算 recall@k / f1@k，逐题明细落库；
3. 坏例分析——recall@5 低于阈值的条目标记为 error，供分段/检索调优。

产出直接作为参赛材料中"知识库构建方法与效果验证"的量化证据。
"""

from __future__ import annotations

import asyncio
import logging
import random
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.llm.client import LLMClient
from app.models.course import KnowledgeChunk
from app.models.kb_evaluation import KbBenchmarkItem, KbEvaluationDetail, KbEvaluationRun
from app.services.course_service import CourseService

logger = logging.getLogger(__name__)

DEFAULT_TOP_KS = [1, 3, 5, 10]
ERROR_RECALL_THRESHOLD = 0.5
MIN_CHUNKS_FOR_BENCHMARK = 3
MAX_BENCHMARK_SIZE = 30

_BENCHMARK_SYSTEM_PROMPT = (
    "你是课程知识库检索评测集构造器。根据给定的【目标段落】和【干扰段落】，"
    "生成一条学生可能会问的检索 query，要求：答案必须能在目标段落中找到，"
    "而干扰段落不足以回答。只输出 JSON："
    '{"query": "学生的问题", "gold_answer": "目标段落中支撑答案的原文要点"}'
)


class KbEvaluationError(RuntimeError):
    pass


class KbEvaluationService:
    def __init__(self, db: Session, course_service: CourseService | None = None, llm: LLMClient | None = None):
        self.db = db
        self.course_service = course_service or CourseService(db)
        self.llm = llm

    # ------------------------------------------------------------------
    # 评测集构造
    # ------------------------------------------------------------------

    def generate_benchmark(self, user_id: int, course_id: int, size: int = 8) -> dict[str, Any]:
        self.course_service.get_course(user_id, course_id)
        chunks = list(
            self.db.scalars(
                select(KnowledgeChunk)
                .where(KnowledgeChunk.course_id == course_id)
                .order_by(KnowledgeChunk.chunk_index.asc(), KnowledgeChunk.id.asc())
            )
        )
        if len(chunks) < MIN_CHUNKS_FOR_BENCHMARK:
            raise KbEvaluationError(
                f"course needs at least {MIN_CHUNKS_FOR_BENCHMARK} knowledge chunks to build a benchmark"
            )
        size = max(1, min(int(size or 8), MAX_BENCHMARK_SIZE))

        rng = random.Random()
        anchors = rng.sample(chunks, min(size, len(chunks)))
        items: list[KbBenchmarkItem] = []
        for anchor in anchors:
            others = [chunk for chunk in chunks if chunk.id != anchor.id]
            distractors = rng.sample(others, min(3, len(others))) if others else []
            payload = self._generate_one(anchor, distractors)
            items.append(
                KbBenchmarkItem(
                    user_id=user_id,
                    course_id=course_id,
                    query=payload["query"],
                    gold_answer=payload["gold_answer"],
                    gold_chunk_ids=[anchor.id],
                    distractor_chunk_ids=[chunk.id for chunk in distractors],
                    source=payload["source"],
                )
            )
        self.db.add_all(items)
        self.db.commit()
        return {
            "generated": len(items),
            "items": [self._item_payload(item) for item in items],
        }

    def _generate_one(self, anchor: KnowledgeChunk, distractors: list[KnowledgeChunk]) -> dict[str, Any]:
        fallback_query = f"请讲解{anchor.heading}的要点" if anchor.heading else f"讲解以下课程内容：{anchor.content[:24]}"
        fallback_answer = anchor.content[:160]
        if self.llm is None:
            return {"query": fallback_query, "gold_answer": fallback_answer, "source": "fallback"}

        context_lines = ["【目标段落】", f"[chunk-{anchor.id}] {anchor.content[:800]}"]
        if distractors:
            context_lines.append("【干扰段落】")
            context_lines.extend(f"[chunk-{chunk.id}] {chunk.content[:400]}" for chunk in distractors)
        try:
            data = self._complete_json(_BENCHMARK_SYSTEM_PROMPT, "\n".join(context_lines))
            query = str(data.get("query", "")).strip()
            gold_answer = str(data.get("gold_answer", "")).strip()
            if not query or not gold_answer:
                raise ValueError("empty query or gold_answer from llm")
            return {"query": query, "gold_answer": gold_answer, "source": "llm_generated"}
        except Exception as exc:
            logger.warning("benchmark llm generation failed, using fallback", extra={"error": str(exc)})
            return {"query": fallback_query, "gold_answer": fallback_answer, "source": "fallback"}

    def _complete_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        """兼容同步/异步 LLM 客户端（LLMClient.complete_json 为 async）。"""
        result = self.llm.complete_json(system_prompt, user_prompt)
        if asyncio.iscoroutine(result):
            result = asyncio.run(result)
        return result

    def list_benchmark(self, user_id: int, course_id: int, limit: int = 200) -> list[dict[str, Any]]:
        self.course_service.get_course(user_id, course_id)
        rows = self.db.scalars(
            select(KbBenchmarkItem)
            .where(KbBenchmarkItem.user_id == user_id, KbBenchmarkItem.course_id == course_id)
            .order_by(KbBenchmarkItem.id.desc())
            .limit(max(1, min(limit, 500)))
        ).all()
        return [self._item_payload(row) for row in rows]

    # ------------------------------------------------------------------
    # 评估执行
    # ------------------------------------------------------------------

    def create_run(self, user_id: int, course_id: int, retriever: str = "semantic") -> dict[str, Any]:
        if retriever not in {"semantic", "mysql_like"}:
            raise KbEvaluationError("retriever must be 'semantic' or 'mysql_like'")
        self.course_service.get_course(user_id, course_id)
        run = KbEvaluationRun(
            user_id=user_id,
            course_id=course_id,
            status="pending",
            retriever=retriever,
            top_ks=DEFAULT_TOP_KS,
        )
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)
        return self._run_payload(run)

    def run_evaluation(self, user_id: int, run_id: int) -> dict[str, Any]:
        run = self.db.scalar(
            select(KbEvaluationRun).where(
                KbEvaluationRun.id == run_id, KbEvaluationRun.user_id == user_id
            )
        )
        if run is None:
            raise KbEvaluationError("evaluation run not found")
        self.course_service.get_course(user_id, run.course_id)

        items = list(
            self.db.scalars(
                select(KbBenchmarkItem).where(
                    KbBenchmarkItem.course_id == run.course_id,
                    KbBenchmarkItem.user_id == user_id,
                )
            )
        )
        if not items:
            raise KbEvaluationError("benchmark is empty; generate benchmark items first")

        run.status = "running"
        run.error_message = ""
        self.db.commit()

        top_ks = list(run.top_ks or DEFAULT_TOP_KS)
        max_k = max(top_ks)
        details: list[KbEvaluationDetail] = []
        try:
            for item in items:
                retrieved_ids = self._retrieve(run, user_id, item.query, max_k)
                metrics = _retrieval_metrics(item.gold_chunk_ids, retrieved_ids, top_ks)
                is_error = metrics.get("recall@5", metrics[f"recall@{max_k}"]) < ERROR_RECALL_THRESHOLD
                details.append(
                    KbEvaluationDetail(
                        run_id=run.id,
                        item_id=item.id,
                        query=item.query,
                        retrieved_chunk_ids=retrieved_ids,
                        metrics=metrics,
                        is_error=is_error,
                    )
                )
                self.db.add(details[-1])
        except KbEvaluationError:
            run.status = "failed"
            run.error_message = "retriever unavailable"
            self.db.commit()
            raise
        except Exception as exc:  # noqa: BLE001 — 评估失败要落库为 failed 状态
            run.status = "failed"
            run.error_message = str(exc)[:500]
            self.db.commit()
            logger.exception("kb evaluation run failed", extra={"run_id": run.id})
            raise KbEvaluationError(f"evaluation failed: {exc}") from exc

        overall: dict[str, Any] = {}
        for key in details[0].metrics:
            overall[key] = round(sum(detail.metrics[key] for detail in details) / len(details), 4)
        overall["overall_score"] = overall.get("recall@5", overall[f"recall@{max_k}"])

        run.item_count = len(details)
        run.error_count = sum(1 for detail in details if detail.is_error)
        run.overall_metrics = overall
        run.status = "completed"
        self.db.commit()
        self.db.refresh(run)
        return {**self._run_payload(run), "details": [self._detail_payload(detail) for detail in details]}

    def _retrieve(self, run: KbEvaluationRun, user_id: int, query: str, limit: int) -> list[int]:
        if run.retriever == "mysql_like":
            chunks = self._mysql_like_search(run.course_id, query, limit)
            return [chunk.id for chunk in chunks]
        try:
            results = self.course_service.semantic_search(user_id, run.course_id, query)
            ids: list[int] = []
            for result in results[:limit]:
                chunk_id = result.get("chunk_id")
                if isinstance(chunk_id, int):
                    ids.append(chunk_id)
            return ids
        except Exception as exc:  # noqa: BLE001
            logger.warning("semantic retriever failed", extra={"error": str(exc)})
            raise KbEvaluationError("semantic retriever unavailable") from exc

    def _mysql_like_search(self, course_id: int, query: str, limit: int) -> list[KnowledgeChunk]:
        chunks = list(
            self.db.scalars(
                select(KnowledgeChunk).where(KnowledgeChunk.course_id == course_id)
            )
        )
        terms = [term for term in query.replace("，", " ").replace(",", " ").split() if term]
        if not terms and query.strip():
            terms = [query.strip()]

        def score(chunk: KnowledgeChunk) -> int:
            haystack = f"{chunk.heading}\n{chunk.content}"
            return sum(1 for term in terms if term in haystack)

        ranked = sorted(chunks, key=lambda chunk: (score(chunk), chunk.chunk_index), reverse=True)
        matched = [chunk for chunk in ranked if score(chunk) > 0]
        return (matched or ranked)[:limit]

    def list_runs(self, user_id: int, course_id: int, limit: int = 20) -> list[dict[str, Any]]:
        self.course_service.get_course(user_id, course_id)
        rows = self.db.scalars(
            select(KbEvaluationRun)
            .where(KbEvaluationRun.user_id == user_id, KbEvaluationRun.course_id == course_id)
            .order_by(KbEvaluationRun.id.desc())
            .limit(max(1, min(limit, 100)))
        ).all()
        return [self._run_payload(row) for row in rows]

    def get_run(self, user_id: int, run_id: int, error_only: bool = False) -> dict[str, Any]:
        run = self.db.scalar(
            select(KbEvaluationRun).where(KbEvaluationRun.id == run_id, KbEvaluationRun.user_id == user_id)
        )
        if run is None:
            raise KbEvaluationError("evaluation run not found")
        query = select(KbEvaluationDetail).where(KbEvaluationDetail.run_id == run_id)
        if error_only:
            query = query.where(KbEvaluationDetail.is_error.is_(True))
        details = list(self.db.scalars(query.order_by(KbEvaluationDetail.id.asc())))
        return {**self._run_payload(run), "details": [self._detail_payload(detail) for detail in details]}

    # ------------------------------------------------------------------

    @staticmethod
    def _item_payload(item: KbBenchmarkItem) -> dict[str, Any]:
        return {
            "id": item.id,
            "query": item.query,
            "gold_answer": item.gold_answer,
            "gold_chunk_ids": item.gold_chunk_ids,
            "distractor_chunk_ids": item.distractor_chunk_ids,
            "source": item.source,
            "created_at": item.created_at.isoformat() if item.created_at else None,
        }

    @staticmethod
    def _run_payload(run: KbEvaluationRun) -> dict[str, Any]:
        return {
            "id": run.id,
            "course_id": run.course_id,
            "status": run.status,
            "retriever": run.retriever,
            "top_ks": run.top_ks,
            "overall_metrics": run.overall_metrics,
            "item_count": run.item_count,
            "error_count": run.error_count,
            "error_message": run.error_message,
            "created_at": run.created_at.isoformat() if run.created_at else None,
        }

    @staticmethod
    def _detail_payload(detail: KbEvaluationDetail) -> dict[str, Any]:
        return {
            "id": detail.id,
            "item_id": detail.item_id,
            "query": detail.query,
            "retrieved_chunk_ids": detail.retrieved_chunk_ids,
            "metrics": detail.metrics,
            "is_error": detail.is_error,
        }


def _retrieval_metrics(gold_ids: list[int], retrieved_ids: list[int], top_ks: list[int]) -> dict[str, float]:
    gold = set(gold_ids)
    metrics: dict[str, float] = {}
    for k in top_ks:
        topk = retrieved_ids[:k]
        hits = len(gold & set(topk))
        recall = hits / len(gold) if gold else 0.0
        precision = hits / k if k else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        metrics[f"recall@{k}"] = round(recall, 4)
        metrics[f"f1@{k}"] = round(f1, 4)
    return metrics


__all__ = ["KbEvaluationError", "KbEvaluationService", "DEFAULT_TOP_KS", "ERROR_RECALL_THRESHOLD"]
