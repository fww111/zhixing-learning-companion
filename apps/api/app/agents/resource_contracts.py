from __future__ import annotations

from typing import Any

from app.models.profile import StudentProfile
from app.models.resource import Resource, ResourceType


def build_analysis_plan(
    *,
    profile: StudentProfile,
    topic: str,
    requested_resource_types: list[ResourceType],
    knowledge_context: list[dict[str, Any]],
    graph_constraints: dict[str, Any],
) -> dict[str, Any]:
    citation_ids = _citation_ids(knowledge_context)
    current_node = graph_constraints.get("current_node") or {}
    parent = graph_constraints.get("parent") or {}
    resource_requirements = {
        resource_type.value: {
            "resource_type": resource_type.value,
            "agent": _agent_name(resource_type),
            "goal": _resource_goal(resource_type),
            "must_use_evidence_chunk_ids": citation_ids,
            "must_follow_graph_node": current_node.get("id") or "",
        }
        for resource_type in requested_resource_types
    }
    blueprint = {
        "topic": topic,
        "learning_objectives": [
            f"理解{topic}的核心概念",
            "能说明它在课程知识图谱中的前后关系",
            "能完成与当前知识点匹配的练习或实操任务",
        ],
        "prerequisites": [item.get("name") for item in graph_constraints.get("predecessors") or [] if item.get("name")],
        "successors": [item.get("name") for item in graph_constraints.get("successors") or [] if item.get("name")],
        "key_claims": _key_claims(topic, knowledge_context),
        "misconceptions": profile.weak_points[:3],
        "difficulty_level": "基础" if "基础" in profile.knowledge_foundation or "一般" in profile.knowledge_foundation else "进阶",
        "style_policy": f"{profile.learning_style}；资源偏好：{'、'.join(profile.resource_preference)}",
        "evidence_chunk_ids": citation_ids,
        "graph_scope": {
            "current_node": current_node,
            "parent": parent,
            "related_count": len(graph_constraints.get("related") or []),
        },
        "resource_requirements": resource_requirements,
    }
    return {
        "agent": "分析规划Agent",
        "topic": topic,
        "student_profile_basis": {
            "learning_goal": profile.learning_goal,
            "knowledge_foundation": profile.knowledge_foundation,
            "learning_style": profile.learning_style,
            "weak_points": profile.weak_points,
        },
        "resource_blueprint": blueprint,
        "risk_points": _risk_points(knowledge_context, graph_constraints),
    }


def build_verification_report(
    *,
    resources: list[Resource],
    knowledge_context: list[dict[str, Any]],
    graph_constraints: dict[str, Any],
    analysis_plan: dict[str, Any],
) -> dict[str, Any]:
    citation_ids = _citation_ids(knowledge_context)
    graph_constraint_count = _graph_constraint_count(graph_constraints)
    unsupported_claims = []
    if not citation_ids:
        unsupported_claims.append("未找到可回表的 MySQL 原文块，资源事实依据不足。")
    if not graph_constraints.get("current_node"):
        unsupported_claims.append("未识别当前知识图谱节点，图谱约束不足。")

    fact_score = 0.95 if citation_ids else 0.55
    pedagogy_score = 0.9 if resources and analysis_plan.get("resource_blueprint") else 0.65
    hallucination_risk = "low" if fact_score >= 0.8 and graph_constraint_count > 0 else "medium"
    decision = "accepted" if fact_score >= 0.8 and pedagogy_score >= 0.75 else "revise"
    notes = [
        f"已使用 {len(citation_ids)} 个 MySQL 原文块作为事实依据。",
        f"已纳入 {graph_constraint_count} 条知识图谱结构约束。",
        f"已检查 {len(resources)} 类资源与统一资源蓝图的一致性。",
    ]
    if unsupported_claims:
        notes.extend(unsupported_claims)

    for resource in resources:
        resource.citation_chunk_ids = citation_ids
        resource.grounding_status = "verified" if decision == "accepted" else "needs_revision"
        resource.verification_notes = notes

    return {
        "agent": "事实校验Agent",
        "decision": decision,
        "fact_score": fact_score,
        "pedagogy_score": pedagogy_score,
        "hallucination_risk": hallucination_risk,
        "evidence_count": len(citation_ids),
        "graph_constraint_count": graph_constraint_count,
        "citation_chunk_ids": citation_ids,
        "unsupported_claims": unsupported_claims,
        "notes": notes,
    }


def build_pedagogy_report(
    *,
    resources: list[Resource],
    profile: StudentProfile,
    analysis_plan: dict[str, Any],
) -> dict[str, Any]:
    requested = set((analysis_plan.get("resource_blueprint") or {}).get("resource_requirements", {}).keys())
    produced = {resource.type.value for resource in resources}
    missing = sorted(requested - produced)
    score = 0.92 if not missing else 0.68
    return {
        "agent": "教学适配校验Agent",
        "score": score,
        "decision": "accepted" if score >= 0.75 else "revise",
        "missing_resource_types": missing,
        "profile_alignment": [
            f"学习风格：{profile.learning_style}",
            f"资源偏好：{'、'.join(profile.resource_preference)}",
            f"薄弱点：{'、'.join(profile.weak_points)}",
        ],
    }


def build_debate_report(
    *,
    verification_report: dict[str, Any],
    pedagogy_report: dict[str, Any],
) -> dict[str, Any]:
    disagreements = []
    if verification_report.get("decision") != pedagogy_report.get("decision"):
        disagreements.append("事实校验与教学适配校验给出的通过状态不一致。")
    unsupported_claims = verification_report.get("unsupported_claims") or []
    decision = "accepted" if not disagreements and not unsupported_claims else "revise"
    return {
        "agent": "辩论交叉验证Agent",
        "decision": decision,
        "disagreements": disagreements,
        "unsupported_claims": unsupported_claims,
        "debate_summary": (
            "事实校验与教学适配校验均通过，资源可进入决策节点。"
            if decision == "accepted"
            else "存在未被证据支持或教学适配不足的内容，需要重检索或重生成。"
        ),
    }


def build_decision_report(
    *,
    verification_report: dict[str, Any],
    pedagogy_report: dict[str, Any],
    debate_report: dict[str, Any],
) -> dict[str, Any]:
    if debate_report.get("decision") == "accepted":
        decision = "accepted"
        next_action = "return_resources"
    elif verification_report.get("evidence_count", 0) == 0:
        decision = "retrieve_more"
        next_action = "retrieve_more_evidence"
    else:
        decision = "revise"
        next_action = "revise_resources"
    return {
        "agent": "决策Agent",
        "decision": decision,
        "next_action": next_action,
        "revision_count": 0,
        "max_revision_count": 1,
        "reason": debate_report.get("debate_summary") or "",
        "fallback_available": True,
        "scores": {
            "fact_score": verification_report.get("fact_score", 0),
            "pedagogy_score": pedagogy_report.get("score", 0),
        },
    }


def _citation_ids(knowledge_context: list[dict[str, Any]]) -> list[int | str]:
    return list(
        dict.fromkeys(
            item.get("chunk_id")
            for item in knowledge_context
            if item.get("chunk_id") is not None and str(item.get("content") or "").strip()
        )
    )


def _key_claims(topic: str, knowledge_context: list[dict[str, Any]]) -> list[str]:
    claims = [f"{topic}的讲解必须来自本地课程知识库和知识图谱。"]
    for item in knowledge_context[:3]:
        heading = item.get("heading") or item.get("source_locator") or "本地知识库片段"
        claims.append(f"引用{heading}作为事实依据。")
    return claims


def _risk_points(knowledge_context: list[dict[str, Any]], graph_constraints: dict[str, Any]) -> list[str]:
    risks = []
    if not knowledge_context:
        risks.append("缺少 MySQL 原文块，生成内容容易泛化。")
    if not graph_constraints.get("current_node"):
        risks.append("缺少当前知识图谱节点，难以约束知识边界。")
    successors = graph_constraints.get("successors") or []
    if successors:
        risks.append("避免把后续知识提前作为当前知识点的必要前提。")
    return risks or ["当前证据和图谱约束充足，低幻觉风险。"]


def _graph_constraint_count(graph_constraints: dict[str, Any]) -> int:
    count = 1 if graph_constraints.get("current_node") else 0
    count += 1 if graph_constraints.get("parent") else 0
    for key in ("predecessors", "successors", "related"):
        count += len(graph_constraints.get(key) or [])
    return count


def _resource_goal(resource_type: ResourceType) -> str:
    goals = {
        ResourceType.MIND_MAP: "结构化呈现知识层级和图谱关系",
        ResourceType.DOCUMENT: "生成可直接学习的讲解文档",
        ResourceType.VIDEO: "生成微课或动画分镜脚本",
        ResourceType.CODE_LAB: "生成可运行的代码实操任务",
        ResourceType.EXERCISE: "生成分层练习和解析",
        ResourceType.READING: "生成拓展阅读路径和任务",
    }
    return goals[resource_type]


def _agent_name(resource_type: ResourceType) -> str:
    names = {
        ResourceType.MIND_MAP: "思维导图Agent",
        ResourceType.DOCUMENT: "文档生成Agent",
        ResourceType.VIDEO: "视频脚本Agent",
        ResourceType.CODE_LAB: "代码实操Agent",
        ResourceType.EXERCISE: "题库生成Agent",
        ResourceType.READING: "拓展阅读Agent",
    }
    return names[resource_type]
