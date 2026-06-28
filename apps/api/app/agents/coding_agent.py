from __future__ import annotations

from app.agents.base import BaseAgent
from app.models.profile import StudentProfile
from app.models.resource import QualityScore, Resource, ResourceType


class CodingAgent(BaseAgent):
    name = "代码实操Agent"

    def _language_for_topic(self, profile: StudentProfile, topic: str, knowledge_context: list[dict] | None) -> str:
        text = " ".join(
            [
                topic,
                profile.learning_goal,
                profile.knowledge_foundation,
                " ".join(profile.knowledge_graph_focus),
                " ".join(profile.resource_preference),
                " ".join(str(item.get("content") or "") for item in (knowledge_context or [])[:3]),
            ]
        ).lower()
        if any(keyword in text for keyword in [
            "c语言",
            "c 语言",
            "#include <stdio.h>",
            "printf(",
            "scanf(",
            "字符数组",
            "一维数组",
            "二维数组",
            "指针",
            "结构体",
        ]):
            return "c"
        return "python"

    async def generate(
        self,
        profile: StudentProfile,
        topic: str,
        knowledge_context: list[dict] | None = None,
        graph_constraints: dict | None = None,
    ) -> Resource:
        language = self._language_for_topic(profile, topic, knowledge_context)
        if language == "c":
            resource_goal = "生成一个能让学生动手验证该知识点的 C 语言代码实操任务。"
            output_requirements = (
                "使用 Markdown；包含可运行 ```c 代码块、运行步骤、观察问题、改造任务和自检标准；"
                "代码应围绕本地知识库中的概念或例子重新设计，不要只做概念卡片占位；"
                "代码块需要包含 #include <stdio.h>、main 函数和 printf/scanf 等适合该知识点的最小可运行结构。"
            )
            language_tag = "c"
        else:
            resource_goal = "生成一个能让学生动手验证该知识点的 Python 代码实操任务。"
            output_requirements = (
                "使用 Markdown；包含可运行 ```python 代码块、运行步骤、观察问题、改造任务和自检标准；"
                "代码应围绕本地知识库中的概念或例子重新设计，不要只做概念卡片占位。"
            )
            language_tag = "python"
        content = await self.complete_resource_text(
            profile=profile,
            topic=topic,
            knowledge_context=knowledge_context,
            graph_constraints=graph_constraints,
            resource_goal=resource_goal,
            output_requirements=output_requirements,
        )
        return Resource(
            type=ResourceType.CODE_LAB,
            title=f"{topic}代码实操任务",
            topic=topic,
            content=content,
            recommendation_reason=f"结合课程知识库生成可操作代码练习。引用依据：{self.source_text(knowledge_context)}",
            tags=[topic, language_tag, "code-lab"],
            quality_score=QualityScore(),
        )
