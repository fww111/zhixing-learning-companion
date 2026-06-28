from __future__ import annotations

from app.agents.base import BaseAgent
from app.models.profile import StudentProfile
from app.models.resource import QualityScore, Resource, ResourceType


class MindMapAgent(BaseAgent):
    name = "思维导图Agent"

    async def generate(
        self,
        profile: StudentProfile,
        topic: str,
        knowledge_context: list[dict] | None = None,
        graph_constraints: dict | None = None,
    ) -> Resource:
        system_prompt, user_prompt = self.mind_map_prompt(
            profile=profile,
            topic=topic,
            knowledge_context=knowledge_context,
            graph_constraints=graph_constraints,
        )
        if self.llm is None:
            raise RuntimeError(f"{self.name} requires an LLM client")
        content = (await self.llm.complete_text(system_prompt, user_prompt)).strip()
        return Resource(
            type=ResourceType.MIND_MAP,
            title=f"{topic}思维导图",
            topic=topic,
            content=content,
            recommendation_reason=f"先建立知识结构，再进入讲解和练习。引用依据：{self.source_text(knowledge_context)}",
            tags=[topic, "markmap"],
            quality_score=QualityScore(),
        )


class ReadingAgent(BaseAgent):
    name = "拓展阅读Agent"

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
            resource_goal="生成一份拓展阅读指引，帮助学生把该知识点放回课程上下文。",
            output_requirements=(
                "使用 Markdown；包含阅读顺序、阅读重点、对照问题、笔记模板和阅读产出要求；"
                "需要基于知识库片段提炼，不要直接展示原文片段。"
            ),
        )
        return Resource(
            type=ResourceType.READING,
            title=f"{topic}拓展阅读",
            topic=topic,
            content=content,
            recommendation_reason=f"用于补齐背景知识和课程上下文。引用依据：{self.source_text(knowledge_context)}",
            tags=[topic, "reading"],
            quality_score=QualityScore(),
        )


class VideoScriptAgent(BaseAgent):
    name = "视频脚本Agent"

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
            resource_goal="生成一个可用于录制微课或动画讲解的视频脚本。",
            output_requirements=(
                "使用 Markdown；包含开场、分镜、旁白、画面建议、互动提问和结尾自检；"
                "脚本应把知识库内容转化成讲授语言，不要直接贴原始片段。"
            ),
        )
        return Resource(
            type=ResourceType.VIDEO,
            title=f"{topic}教学视频脚本",
            topic=topic,
            content=content,
            recommendation_reason=f"用视听化表达降低理解门槛。引用依据：{self.source_text(knowledge_context)}",
            tags=[topic, "video-script"],
            quality_score=QualityScore(),
        )


class MultimodalAgent(BaseAgent):
    name = "多模态资源Agent"

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.mind_map_agent = MindMapAgent(self.llm)
        self.reading_agent = ReadingAgent(self.llm)
        self.video_agent = VideoScriptAgent(self.llm)

    async def generate(
        self,
        profile: StudentProfile,
        topic: str,
        knowledge_context: list[dict] | None = None,
        graph_constraints: dict | None = None,
    ) -> list[Resource]:
        return [
            await self.generate_mind_map(profile, topic, knowledge_context, graph_constraints),
            await self.generate_reading(profile, topic, knowledge_context, graph_constraints),
            await self.generate_video(profile, topic, knowledge_context, graph_constraints),
        ]

    async def generate_mind_map(
        self,
        profile: StudentProfile,
        topic: str,
        knowledge_context: list[dict] | None = None,
        graph_constraints: dict | None = None,
    ) -> Resource:
        return await self.mind_map_agent.generate(profile, topic, knowledge_context, graph_constraints)

    async def generate_reading(
        self,
        profile: StudentProfile,
        topic: str,
        knowledge_context: list[dict] | None = None,
        graph_constraints: dict | None = None,
    ) -> Resource:
        return await self.reading_agent.generate(profile, topic, knowledge_context, graph_constraints)

    async def generate_video(
        self,
        profile: StudentProfile,
        topic: str,
        knowledge_context: list[dict] | None = None,
        graph_constraints: dict | None = None,
    ) -> Resource:
        return await self.video_agent.generate(profile, topic, knowledge_context, graph_constraints)
