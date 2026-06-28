from __future__ import annotations

from app.llm.client import LLMClient
from app.models.profile import StudentProfile


class BaseAgent:
    name = "base_agent"

    def __init__(self, llm: LLMClient | None = None) -> None:
        self.llm = llm

    def event(self, event: str, summary: str) -> dict[str, str]:
        return {"event": event, "agent": self.name, "summary": summary}

    def knowledge_context_text(self, knowledge_context: list[dict] | None, limit: int = 5) -> str:
        if not knowledge_context:
            return "暂无可引用的本地知识库片段。"
        lines = []
        for index, item in enumerate(knowledge_context[:limit], 1):
            source = item.get("source_locator") or item.get("chunk_id") or "本地知识库"
            content = str(item.get("content") or "").strip()
            lines.append(f"[{index}] 来源：{source}\n{content}")
        return "\n\n".join(lines)

    def source_text(self, knowledge_context: list[dict] | None, limit: int = 5) -> str:
        if not knowledge_context:
            return "暂无可引用片段"
        return "、".join(
            str(item.get("source_locator") or item.get("chunk_id") or "本地知识库")
            for item in knowledge_context[:limit]
        )

    def graph_constraints_text(self, graph_constraints: dict | None) -> str:
        if not graph_constraints:
            return "暂无知识图谱约束。"

        current = graph_constraints.get("current_node") or {}
        parent = graph_constraints.get("parent") or {}
        lines = [
            f"当前知识点：{current.get('name') or '未识别'}（{current.get('id') or '无ID'}）",
        ]
        if parent:
            lines.append(f"所属章节：{parent.get('name')}")
        relation_specs = [
            ("前置知识", graph_constraints.get("predecessors") or []),
            ("后续知识", graph_constraints.get("successors") or []),
            ("相关知识", graph_constraints.get("related") or []),
        ]
        for label, nodes in relation_specs:
            if nodes:
                values = []
                for node in nodes[:4]:
                    reason = node.get("relation_reason") or node.get("summary") or ""
                    values.append(f"{node.get('name')}（{node.get('relation_type') or 'related'}：{reason}）")
                lines.append(f"{label}：" + "；".join(values))
        source_chunk_ids = graph_constraints.get("source_chunk_ids") or []
        if source_chunk_ids:
            lines.append(f"图谱节点绑定原文块：{', '.join(str(item) for item in source_chunk_ids)}")
        return "\n".join(lines)

    def profile_text(self, profile: StudentProfile) -> str:
        return (
            f"专业/年级：{profile.major} / {profile.grade}\n"
            f"学习目标：{profile.learning_goal}\n"
            f"基础情况：{profile.knowledge_foundation}\n"
            f"学习偏好：{profile.learning_style}；资源偏好：{', '.join(profile.resource_preference)}\n"
            f"认知方式：{profile.cognitive_style}\n"
            f"薄弱点：{', '.join(profile.weak_points)}\n"
            f"时间偏好：{profile.time_preference}\n"
            f"约束：{', '.join(profile.constraints) if profile.constraints else '无'}"
        )

    def resource_prompt(
        self,
        *,
        profile: StudentProfile,
        topic: str,
        knowledge_context: list[dict] | None,
        graph_constraints: dict | None = None,
        resource_goal: str,
        output_requirements: str,
    ) -> tuple[str, str]:
        system_prompt = (
            f"你是{self.name}。请基于本地课程知识库片段和学生画像生成教学资源。"
            "知识库片段是依据，不要原样堆砌；需要综合、改写、举例和组织成适合学生学习的内容。"
            "必须遵守知识图谱给出的章节、前置、后续和相关关系，不能把后续知识提前当作当前知识的前提。"
            "如果片段不足，可以补充通用教学解释，但不要编造与课程材料冲突的事实。"
            "输出中的关键事实应能追溯到提供的 MySQL 原文块或知识图谱关系。"
            "请优先输出结构化、可直接用于页面展示的内容，不要输出对模型能力的解释。"
        )
        user_prompt = f"""知识点：{topic}

学生画像：
{self.profile_text(profile)}

知识图谱约束：
{self.graph_constraints_text(graph_constraints)}

本地知识库片段：
{self.knowledge_context_text(knowledge_context)}

资源目标：
{resource_goal}

输出要求：
{output_requirements}
"""
        return system_prompt, user_prompt

    def mind_map_prompt(
        self,
        *,
        profile: StudentProfile,
        topic: str,
        knowledge_context: list[dict] | None,
        graph_constraints: dict | None = None,
    ) -> tuple[str, str]:
        system_prompt = (
            f"你是{self.name}，请生成严格结构化的思维导图文本。"
            "输出必须体现层级关系，适合被前端渲染为图，而不是普通说明文。"
            "必须依据知识图谱约束组织中心节点、前置关系、后续关系和相关知识。"
        )
        user_prompt = f"""知识点：{topic}

学生画像：
{self.profile_text(profile)}

知识图谱约束：
{self.graph_constraints_text(graph_constraints)}

本地知识库片段：
{self.knowledge_context_text(knowledge_context)}

输出格式要求：
1. 使用 Markdown 标题层级或缩进列表表达中心主题、一级分支、二级分支。
2. 中心节点必须是当前知识点。
3. 每个一级分支都要能映射到课程材料中的一个关键子主题。
4. 至少包含：定义、结构、步骤/流程、示例、常见误区、与前后知识点关系。
5. 不要写成普通文档，不要加入长篇解释段落。
"""
        return system_prompt, user_prompt

    async def complete_resource_text(
        self,
        *,
        profile: StudentProfile,
        topic: str,
        knowledge_context: list[dict] | None,
        graph_constraints: dict | None = None,
        resource_goal: str,
        output_requirements: str,
    ) -> str:
        if self.llm is None:
            raise RuntimeError(f"{self.name} requires an LLM client")
        system_prompt, user_prompt = self.resource_prompt(
            profile=profile,
            topic=topic,
            knowledge_context=knowledge_context,
            graph_constraints=graph_constraints,
            resource_goal=resource_goal,
            output_requirements=output_requirements,
        )
        content = await self.llm.complete_text(system_prompt, user_prompt)
        return content.strip()
