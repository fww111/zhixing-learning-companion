from __future__ import annotations

from app.agents.base import BaseAgent
from app.models.profile import StudentProfile
from app.models.resource import QualityScore, Resource, ResourceType


class ExerciseAgent(BaseAgent):
    name = "题库生成Agent"

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
            resource_goal="生成一组围绕该知识点的专业评估练习，用于学习后检测学生是否真正掌握本节课内容。",
            output_requirements=(
                "使用 Markdown，严格按以下结构输出，便于前端评估页解析：\n"
                "1. 题干\nA. 选项\nB. 选项\nC. 选项\n答案：A/B/C\n维度：概念理解\n权重：35%\n"
                "2. 题干\nA. 选项\nB. 选项\nC. 选项\n答案：A/B/C\n维度：迁移应用\n权重：30%\n"
                "3. 题干\nA. 选项\nB. 选项\nC. 选项\n答案：A/B/C\n维度：调试反思\n权重：35%\n"
                "编程题：给出一个与当前知识点直接相关的最小可运行任务要求；不要给完整答案代码。\n"
                "期望输出：给出用于自动判分的唯一输出文本。\n"
                "```python 或 ```c 代码块只放起始代码/占位注释，不要包含期望输出或最终答案。\n"
                "题目必须从本地知识库内容改写或延展，考察本知识点的专业概念、应用场景、错误诊断或代码行为。\n"
                "不能生成询问是否记住标题、是否记住要点、是否看过视频、是否复制示例等学习行为题。\n"
                "选项必须是专业判断、代码行为、场景选择或错误原因，不能把“只记住标题/看过视频”作为干扰项。\n"
                "编程题必须随知识点变化，不能统一要求输出“某某达标”；题目只给任务要求、起始代码和期望输出，不给完整答案代码。"
            ),
        )
        return Resource(
            type=ResourceType.EXERCISE,
            title=f"{topic}分层练习题",
            topic=topic,
            content=content,
            recommendation_reason=f"根据知识点薄弱情况生成练习和解析。引用依据：{self.source_text(knowledge_context)}",
            tags=[topic, "exercise"],
            quality_score=QualityScore(),
        )
