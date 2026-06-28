from __future__ import annotations

from app.agents.base import BaseAgent
from app.models.profile import StudentProfile
from app.models.resource import QualityScore, Resource, ResourceType


class DocumentAgent(BaseAgent):
    name = "文档生成Agent"

    async def generate(
        self,
        profile: StudentProfile,
        topic: str,
        knowledge_context: list[dict] | None = None,
        graph_constraints: dict | None = None,
    ) -> Resource:
        content = await self.complete_resource_text(
            profile=profile,
            topic=topic,
            knowledge_context=knowledge_context,
            graph_constraints=graph_constraints,
            resource_goal="生成一份可直接学习的知识点讲解文档，帮助学生理解概念、步骤、例子和易错点。",
            output_requirements=(
                "使用 Markdown；包含学习目标、概念解释、教材依据改写后的例子、常见误区、"
                "学习建议和自检问题；不要把本地知识库片段整段原样复制到正文。"
            ),
        )
        return Resource(
            type=ResourceType.DOCUMENT,
            title=f"{topic}个性化讲解文档",
            topic=topic,
            content=content,
            recommendation_reason=f"基于学生画像和本地知识库生成讲解文档。引用依据：{self.source_text(knowledge_context)}",
            tags=[topic, "markdown"],
            quality_score=QualityScore(),
        )
