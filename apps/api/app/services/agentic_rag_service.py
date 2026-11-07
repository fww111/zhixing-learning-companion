from __future__ import annotations

from typing import Any

from sqlalchemy import select

from app.models.course import KnowledgeChunk
from app.services.course_service import CourseService
from app.services.rag_fusion import compress_chunk_to_relevant_sentences, rrf_fuse_hits
from app.services.rag_lexicon import expand_query_with_terms


class AgenticRAGService:
    """Builds grounded evidence for resource agents with KG-constrained retrieval."""

    def __init__(self, course_service: CourseService) -> None:
        self.course_service = course_service

    def build_context(
        self,
        *,
        user_id: int | None,
        course_id: int | None,
        node_id: str,
        topic: str,
    ) -> dict[str, Any]:
        if user_id is None or course_id is None:
            return {
                "knowledge_context": [],
                "graph_constraints": self._empty_graph_constraints(node_id, topic),
                "retrieval_trace": [],
            }

        graph_constraints = self._graph_constraints(user_id, course_id, node_id, topic)
        queries = [
            expand_query_with_terms(query)
            for query in self._retrieval_queries(topic, graph_constraints)
        ]
        raw_hits = self._vector_hits(user_id, course_id, queries)
        vector_hits = rrf_fuse_hits(raw_hits, max_results=30)
        knowledge_context, retrieval_trace = self._mysql_context_from_hits(course_id, vector_hits)

        if not knowledge_context:
            knowledge_context = self._fallback_chunks(user_id, course_id, queries)
            retrieval_trace = [
                {
                    "query": item.get("retrieval_query") or topic,
                    "vector_chunk_id": None,
                    "mysql_chunk_id": item.get("chunk_id"),
                    "source_locator": item.get("source_locator"),
                    "strategy": "mysql_fallback",
                }
                for item in knowledge_context
            ]

        return {
            "knowledge_context": knowledge_context[:5],
            "graph_constraints": graph_constraints,
            "retrieval_trace": retrieval_trace[:8],
        }

    def _graph_constraints(self, user_id: int, course_id: int, node_id: str, topic: str) -> dict[str, Any]:
        try:
            graph = self.course_service.get_knowledge_graph(user_id, course_id)
        except Exception:
            graph = {"nodes": [], "edges": []}

        nodes = graph.get("nodes") or []
        edges = graph.get("edges") or []
        by_id = {str(node.get("id")): node for node in nodes if node.get("id") is not None}
        current = by_id.get(str(node_id)) if node_id else None
        if current is None:
            current = self._find_node_by_name(nodes, topic)

        if current is None:
            return {
                **self._empty_graph_constraints(node_id, topic),
                "node_found": False,
            }

        current_id = str(current.get("id") or "")
        parent = by_id.get(str(current.get("parent_id") or ""))
        predecessors = []
        successors = []
        related = []
        for edge in edges:
            source_id = str(edge.get("source_node_id") or "")
            target_id = str(edge.get("target_node_id") or "")
            relation = str(edge.get("relation_type") or "related")
            if target_id == current_id and source_id in by_id:
                predecessors.append(self._node_ref(by_id[source_id], edge))
            elif source_id == current_id and target_id in by_id:
                successor = self._node_ref(by_id[target_id], edge)
                if relation in {"prerequisite", "depends_on", "sequence"}:
                    successors.append(successor)
                else:
                    related.append(successor)

        siblings = [
            self._node_ref(node)
            for node in nodes
            if node.get("id") != current.get("id")
            and node.get("parent_id")
            and node.get("parent_id") == current.get("parent_id")
        ][:3]

        return {
            "current_node": self._node_ref(current),
            "parent": self._node_ref(parent) if parent else None,
            "predecessors": predecessors[:3],
            "successors": successors[:3],
            "related": (related + siblings)[:5],
            "source_chunk_ids": [str(item) for item in current.get("source_chunk_ids") or []],
            "node_found": True,
        }

    def _vector_hits(self, user_id: int, course_id: int, queries: list[str]) -> list[dict[str, Any]]:
        """多路向量召回：每路按返回顺序记 rank（交给 RRF 跨路融合）。"""
        hits = []
        for query in queries:
            try:
                results = self.course_service.semantic_search(user_id, course_id, query)
            except Exception:
                results = []
            for rank, result in enumerate(results):
                chunk_id = self._coerce_chunk_id(result.get("chunk_id"))
                if chunk_id is None:
                    continue
                hits.append(
                    {
                        "query": query,
                        "chunk_id": chunk_id,
                        "_rank": rank,
                        "distance": result.get("distance"),
                        "vector_source_locator": result.get("source_locator"),
                    }
                )
        return hits

    def _mysql_context_from_hits(
        self,
        course_id: int,
        hits: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        if not hits:
            return [], []

        chunk_ids = [hit["chunk_id"] for hit in hits]
        chunks = list(
            self.course_service.db.scalars(
                select(KnowledgeChunk).where(KnowledgeChunk.course_id == course_id, KnowledgeChunk.id.in_(chunk_ids))
            )
        )
        by_id = {chunk.id: chunk for chunk in chunks}
        context = []
        trace = []
        for hit in hits:
            chunk = by_id.get(hit["chunk_id"])
            if chunk is None:
                trace.append(
                    {
                        "query": hit["query"],
                        "vector_chunk_id": hit["chunk_id"],
                        "mysql_chunk_id": None,
                        "source_locator": hit.get("vector_source_locator"),
                        "strategy": "vector_hit_missing_mysql_chunk",
                    }
                )
                continue
            context.append(self._chunk_context(chunk, hit.get("first_query") or hit.get("query") or "", hit.get("distance")))
            trace.append(
                {
                    "query": hit.get("first_query") or hit.get("query") or "",
                    "hit_queries": hit.get("hit_queries") or [],
                    "rrf_score": hit.get("rrf_score"),
                    "vector_chunk_id": hit["chunk_id"],
                    "mysql_chunk_id": chunk.id,
                    "source_locator": chunk.source_locator,
                    "distance": hit.get("distance"),
                    "strategy": "vector_to_mysql_rrf",
                }
            )
        return context, trace

    def _fallback_chunks(self, user_id: int, course_id: int, queries: list[str]) -> list[dict[str, Any]]:
        try:
            chunks = self.course_service.list_chunks(user_id, course_id)
        except Exception:
            return []
        ranked = self._rank_chunks(chunks, " ".join(queries))
        return [self._chunk_context(chunk, queries[0] if queries else "") for chunk in ranked[:5]]

    def _rank_chunks(self, chunks: list[KnowledgeChunk], query: str) -> list[KnowledgeChunk]:
        compact_query = (query or "").lower()
        terms = [term for term in compact_query.replace(".", " ").split() if term]

        def score(chunk: KnowledgeChunk) -> tuple[int, int]:
            text = f"{chunk.heading} {chunk.content}".lower()
            lexical = sum(1 for term in terms if term and term in text)
            return (lexical, -chunk.chunk_index)

        return sorted(chunks, key=score, reverse=True)

    def _retrieval_queries(self, topic: str, graph_constraints: dict[str, Any]) -> list[str]:
        values = [topic]
        current = graph_constraints.get("current_node") or {}
        parent = graph_constraints.get("parent") or {}
        values.append(f"{current.get('name', '')} {current.get('summary', '')}".strip())
        values.append(f"{parent.get('name', '')} {topic}".strip())
        for key in ("predecessors", "successors", "related"):
            for node in graph_constraints.get(key) or []:
                values.append(f"{topic} {node.get('name', '')} {node.get('relation_type', '')}".strip())
        return list(dict.fromkeys(value for value in values if value))[:6]

    def _chunk_context(self, chunk: KnowledgeChunk, query: str, distance: Any | None = None) -> dict[str, Any]:
        compressed = compress_chunk_to_relevant_sentences(chunk.content, query)
        return {
            "chunk_id": chunk.id,
            "source_locator": chunk.source_locator or chunk.heading or "本地知识库",
            "heading": chunk.heading,
            # 句级抽取式压缩：按查询相关度保留句子（chunk_id 仍指向 MySQL 原文，可回溯全文）
            "content": compressed,
            "compressed": len(compressed) < len(chunk.content),
            "retrieval_query": query,
            "distance": distance,
            "storage": "mysql",
        }

    def _find_node_by_name(self, nodes: list[dict[str, Any]], topic: str) -> dict[str, Any] | None:
        compact_topic = (topic or "").strip()
        for node in nodes:
            if compact_topic and compact_topic in str(node.get("name") or ""):
                return node
        return None

    def _node_ref(self, node: dict[str, Any], edge: dict[str, Any] | None = None) -> dict[str, Any]:
        result = {
            "id": str(node.get("id") or ""),
            "name": str(node.get("name") or ""),
            "node_type": str(node.get("node_type") or ""),
            "summary": str(node.get("summary") or ""),
            "level": node.get("level"),
            "parent_id": str(node.get("parent_id") or ""),
        }
        if edge:
            result["relation_type"] = str(edge.get("relation_type") or "related")
            result["relation_reason"] = str(edge.get("reason") or "")
        return result

    def _empty_graph_constraints(self, node_id: str, topic: str) -> dict[str, Any]:
        return {
            "current_node": {"id": node_id or "", "name": topic or "", "node_type": "", "summary": ""},
            "parent": None,
            "predecessors": [],
            "successors": [],
            "related": [],
            "source_chunk_ids": [],
            "node_found": False,
        }

    def _coerce_chunk_id(self, value: Any) -> int | None:
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            normalized = value.removeprefix("chunk-")
            if normalized.isdigit():
                return int(normalized)
        return None
