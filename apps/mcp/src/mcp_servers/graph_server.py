"""graph-server: course knowledge graph constraints and ground-truth evidence retrieval.

See docs/agentarts/03-MCP服务接口契约.md §2.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import or_, select

from mcp_servers._bootstrap import ensure_api_importable

ensure_api_importable()

from mcp.server.fastmcp import FastMCP  # noqa: E402

from mcp_servers.runtime import (  # noqa: E402
    CourseLookupError,
    clamp_limit,
    ensure_course,
    fail,
    get_session,
    ok,
    run_server,
)

from app.models.course import KnowledgeChunk  # noqa: E402
from app.services.course_service import CourseNotFoundError, CourseService  # noqa: E402

mcp = FastMCP("graph-server", stateless_http=True)

_PARENT_RELATIONS = {"contains", "includes", "has_subnode"}


def _load_graph(db: Any, user_id: int, course_id: int) -> dict[str, Any] | dict[str, Any]:
    try:
        graph = CourseService(db).get_knowledge_graph(user_id, course_id)
    except CourseNotFoundError as exc:
        return fail("course_not_found", str(exc))
    nodes = graph.get("nodes") or []
    edges = graph.get("edges") or []
    if not nodes:
        return fail(
            "graph_missing",
            f"knowledge graph for course {course_id} is empty; build the graph first",
        )
    return {"nodes": nodes, "edges": edges}


def _find_node(graph: dict[str, Any], node_id: str) -> dict[str, Any] | None:
    for node in graph.get("nodes", []):
        if str(node.get("id", "")) == node_id:
            return node
    return None


def _chunk_id_list(raw: Any) -> list[int]:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            raw = [raw]
    if not isinstance(raw, list):
        return []
    ids: list[int] = []
    for item in raw:
        try:
            ids.append(int(item))
        except (TypeError, ValueError):
            continue
    return ids


def _escape_like(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return escaped


def _chunk_payload(chunk: KnowledgeChunk) -> dict[str, Any]:
    return {
        "chunk_id": chunk.id,
        "material_id": chunk.material_id,
        "chunk_index": chunk.chunk_index,
        "heading": chunk.heading,
        "source_locator": chunk.source_locator,
        "content": chunk.content,
        "token_count": chunk.token_count,
    }


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


def get_course_graph_impl(user_id: int, course_id: int) -> dict[str, Any]:
    """返回当前课程的完整知识图谱（节点含掌握度状态，边含关系类型与理由）。

    Args:
        user_id: 学生用户 ID。
        course_id: 课程 ID。

    Returns:
        nodes: [{id, name, node_type, difficulty, summary, level, parent_id,
        order, source_chunk_ids, mastery_status, mastery_score}]；
        edges: [{id, source_node_id, target_node_id, relation_type, reason, confidence}]。
    """
    with get_session() as db:
        try:
            ensure_course(db, user_id, course_id)
        except CourseLookupError as exc:
            return fail("course_not_found", str(exc))
        graph = _load_graph(db, user_id, course_id)
        if "ok" in graph and graph["ok"] is False:
            return graph
        return ok(nodes=graph["nodes"], edges=graph["edges"])


def get_node_constraints_impl(user_id: int, course_id: int, node_id: str) -> dict[str, Any]:
    """返回当前知识点的图谱约束：父章节、子节点、前置知识、后续知识、相关节点与掌握度。

    资源生成与智能辅导必须使用该约束决定"讲什么、讲多深、先讲什么"。

    Args:
        user_id: 学生用户 ID。
        course_id: 课程 ID。
        node_id: 知识图谱节点 ID。

    Returns:
        node（节点详情）、parent（父章节）、children、prerequisites（前置节点列表）、
        successors（后续节点列表）、related（related/易错/案例等其余关系节点列表）、
        mastery（{mastery_status, mastery_score}）。
    """
    if not node_id:
        return fail("validation_error", "node_id must not be empty")
    with get_session() as db:
        try:
            ensure_course(db, user_id, course_id)
        except CourseLookupError as exc:
            return fail("course_not_found", str(exc))
        graph = _load_graph(db, user_id, course_id)
        if "ok" in graph and graph["ok"] is False:
            return graph

        node = _find_node(graph, node_id)
        if node is None:
            return fail("validation_error", f"node {node_id} not found in course graph")

        nodes = graph["nodes"]
        edges = graph["edges"]
        by_id = {str(item.get("id", "")): item for item in nodes}

        parent = by_id.get(str(node.get("parent_id", ""))) if node.get("parent_id") else None
        children = [item for item in nodes if str(item.get("parent_id", "")) == node_id]

        prerequisites: list[dict[str, Any]] = []
        successors: list[dict[str, Any]] = []
        related: list[dict[str, Any]] = []
        for edge in edges:
            relation = str(edge.get("relation_type", ""))
            source = str(edge.get("source_node_id", ""))
            target = str(edge.get("target_node_id", ""))
            if relation == "prerequisite":
                if target == node_id and source in by_id:
                    prerequisites.append(by_id[source])
                elif source == node_id and target in by_id:
                    successors.append(by_id[target])
            elif node_id in {source, target} and relation not in _PARENT_RELATIONS:
                other_id = target if source == node_id else source
                if other_id in by_id and all(item.get("id") != by_id[other_id].get("id") for item in related):
                    related.append(by_id[other_id])

        return ok(
            node=node,
            parent=parent,
            children=children,
            prerequisites=prerequisites,
            successors=successors,
            related=related,
            mastery={
                "mastery_status": node.get("mastery_status", "not_started"),
                "mastery_score": node.get("mastery_score"),
            },
        )


def get_knowledge_evidence_impl(
    user_id: int,
    course_id: int,
    node_id: str,
    limit: int = 6,
) -> dict[str, Any]:
    """返回当前知识点绑定的课程原文证据（MySQL knowledge_chunks 回表）。

    生成给学生的内容必须以这些原文 chunk 为最终依据（Milvus/平台知识库只做召回）。
    优先按节点 source_chunk_ids 精确回表；无绑定时按节点名做 LIKE 兜底检索。

    Args:
        user_id: 学生用户 ID。
        course_id: 课程 ID。
        node_id: 知识图谱节点 ID。
        limit: 最多返回的 chunk 数，默认 6，最大 50。

    Returns:
        evidence: [{chunk_id, material_id, chunk_index, heading, source_locator,
        content, token_count}]，content 为教材原文。
    """
    if not node_id:
        return fail("validation_error", "node_id must not be empty")
    with get_session() as db:
        try:
            ensure_course(db, user_id, course_id)
        except CourseLookupError as exc:
            return fail("course_not_found", str(exc))
        graph = _load_graph(db, user_id, course_id)
        if "ok" in graph and graph["ok"] is False:
            return graph
        node = _find_node(graph, node_id)
        if node is None:
            return fail("validation_error", f"node {node_id} not found in course graph")

        limited = clamp_limit(limit, default=6, maximum=50)
        chunks: list[KnowledgeChunk] = []
        chunk_ids = _chunk_id_list(node.get("source_chunk_ids"))
        if chunk_ids:
            chunks = list(
                db.scalars(
                    select(KnowledgeChunk)
                    .where(KnowledgeChunk.course_id == course_id, KnowledgeChunk.id.in_(chunk_ids))
                    .order_by(KnowledgeChunk.chunk_index)
                    .limit(limited)
                ).all()
            )
        if not chunks:
            node_name = str(node.get("name", "")).strip()
            if node_name:
                pattern = f"%{_escape_like(node_name)}%"
                chunks = list(
                    db.scalars(
                        select(KnowledgeChunk)
                        .where(
                            KnowledgeChunk.course_id == course_id,
                            or_(
                                KnowledgeChunk.heading.ilike(pattern, escape="\\"),
                                KnowledgeChunk.content.ilike(pattern, escape="\\"),
                            ),
                        )
                        .order_by(KnowledgeChunk.chunk_index)
                        .limit(limited)
                    ).all()
                )
        return ok(
            node_id=node_id,
            node_name=node.get("name", ""),
            evidence=[_chunk_payload(chunk) for chunk in chunks],
        )


def search_course_chunks_impl(
    user_id: int,
    course_id: int,
    query: str,
    limit: int = 8,
) -> dict[str, Any]:
    """按关键词检索当前课程的原文 chunk（LIKE 检索兜底，不依赖向量服务）。

    Args:
        user_id: 学生用户 ID。
        course_id: 课程 ID。
        query: 关键词（如"列表切片"、"for 循环"）。
        limit: 最多返回条数，默认 8，最大 50。

    Returns:
        chunks: [{chunk_id, material_id, chunk_index, heading, source_locator,
        content, token_count}]。
    """
    if not (query or "").strip():
        return fail("validation_error", "query must not be empty")
    with get_session() as db:
        try:
            ensure_course(db, user_id, course_id)
        except CourseLookupError as exc:
            return fail("course_not_found", str(exc))
        pattern = f"%{_escape_like(query.strip())}%"
        chunks = db.scalars(
            select(KnowledgeChunk)
            .where(
                KnowledgeChunk.course_id == course_id,
                or_(
                    KnowledgeChunk.heading.ilike(pattern, escape="\\"),
                    KnowledgeChunk.content.ilike(pattern, escape="\\"),
                ),
            )
            .order_by(KnowledgeChunk.chunk_index)
            .limit(clamp_limit(limit, default=8, maximum=50))
        ).all()
        return ok(query=query, chunks=[_chunk_payload(chunk) for chunk in chunks])


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

# Single registry shared with the unified single-port entrypoint.
TOOL_IMPLS = {
    "get_course_graph": get_course_graph_impl,
    "get_node_constraints": get_node_constraints_impl,
    "get_knowledge_evidence": get_knowledge_evidence_impl,
    "search_course_chunks": search_course_chunks_impl,
}

for _name, _impl in TOOL_IMPLS.items():
    mcp.tool(name=_name)(_impl)


if __name__ == "__main__":
    run_server(mcp, default_port=8101)
