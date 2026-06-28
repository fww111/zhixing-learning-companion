from __future__ import annotations

from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, Field


class ResourceType(StrEnum):
    DOCUMENT = "document"
    MIND_MAP = "mind_map"
    EXERCISE = "exercise"
    READING = "reading"
    VIDEO = "video"
    CODE_LAB = "code_lab"


class QualityScore(BaseModel):
    accuracy: float = 0.9
    personalization: float = 0.88
    completeness: float = 0.86
    operability: float = 0.9


class Resource(BaseModel):
    id: str = Field(default_factory=lambda: f"resource-{uuid4().hex[:8]}")
    type: ResourceType
    title: str
    topic: str
    content: str
    recommendation_reason: str
    tags: list[str] = Field(default_factory=list)
    quality_score: QualityScore | None = None
    citation_chunk_ids: list[int | str] = Field(default_factory=list)
    grounding_status: str = "unverified"
    verification_notes: list[str] = Field(default_factory=list)

    @classmethod
    def sample(cls, resource_type: ResourceType, topic: str) -> "Resource":
        titles = {
            ResourceType.DOCUMENT: f"{topic}个性化讲解文档",
            ResourceType.MIND_MAP: f"{topic}知识导图",
            ResourceType.EXERCISE: f"{topic}分层练习",
            ResourceType.READING: f"{topic}拓展阅读",
            ResourceType.VIDEO: f"{topic}教学动画脚本",
            ResourceType.CODE_LAB: f"{topic}代码实操案例",
        }
        return cls(
            type=resource_type,
            title=titles[resource_type],
            topic=topic,
            content=f"# {titles[resource_type]}\n\n围绕{topic}生成的学习资源。",
            recommendation_reason=f"根据画像中的薄弱点和资源偏好推荐{topic}资源。",
            tags=[topic, resource_type.value],
            quality_score=QualityScore(),
            grounding_status="sample",
        )


class OpenMAICClassroom(BaseModel):
    job_id: str = ""
    status: str = ""
    step: str = ""
    poll_url: str = ""
    poll_interval_ms: int = 0
    url: str = ""
    classroom_id: str = ""
    requirement: str = ""
    error: str = ""
